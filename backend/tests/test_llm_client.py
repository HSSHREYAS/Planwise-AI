"""
Unit tests for the hosted LLM client: provider chain, fallback,
rate-limit handling and structured output. No network access.
"""

import pytest
from pydantic import BaseModel

from app import config
from app.llm import client as llm_module
from app.llm.client import LLMClient, LLMUnavailableError, Provider, build_provider_chain


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)
        self.headers = headers or {}

    def json(self):
        return self._payload


def chat(content):
    return FakeResponse(200, {"choices": [{"message": {"content": content}}]})


def provider(name, json_mode=True):
    return Provider(name=name, url=f"https://{name}.test/chat", model=f"{name}-model",
                    api_key="k", json_mode=json_mode)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)


class TestProviderChain:
    def test_auto_without_keys_is_keyless_only(self, monkeypatch):
        for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "CUSTOM_LLM_API_KEY"):
            monkeypatch.setattr(config, key, "")
        chain = build_provider_chain("auto")
        assert [p.name for p in chain] == ["pollinations"]
        assert LLMClient(providers=chain).frugal is True

    def test_auto_orders_keyed_providers_before_keyless(self, monkeypatch):
        monkeypatch.setattr(config, "GROQ_API_KEY", "g")
        monkeypatch.setattr(config, "GEMINI_API_KEY", "m")
        monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(config, "CUSTOM_LLM_API_KEY", "")
        chain = build_provider_chain("auto")
        assert [p.name for p in chain] == ["groq", "gemini", "pollinations"]
        assert LLMClient(providers=chain).frugal is False

    def test_preferred_provider_goes_first(self, monkeypatch):
        monkeypatch.setattr(config, "GROQ_API_KEY", "g")
        monkeypatch.setattr(config, "GEMINI_API_KEY", "m")
        chain = build_provider_chain("gemini")
        assert chain[0].name == "gemini"
        assert "groq" in [p.name for p in chain]

    def test_preferred_provider_without_key_falls_back(self, monkeypatch):
        for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "CUSTOM_LLM_API_KEY"):
            monkeypatch.setattr(config, key, "")
        chain = build_provider_chain("groq")
        assert [p.name for p in chain] == ["pollinations"]

    def test_ollama_mode_stays_local(self, monkeypatch):
        for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "CUSTOM_LLM_API_KEY"):
            monkeypatch.setattr(config, key, "")
        chain = build_provider_chain("ollama")
        assert [p.name for p in chain] == ["ollama"]


class TestGenerate:
    def test_sends_openai_style_request(self, monkeypatch):
        calls = []

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append((url, headers, json))
            return chat("  hello  ")

        monkeypatch.setattr(llm_module.requests, "post", fake_post)
        llm = LLMClient(providers=[provider("groq")])
        assert llm.generate("hi", system="sys", json_mode=True) == "hello"

        url, headers, payload = calls[0]
        assert url == "https://groq.test/chat"
        assert headers["Authorization"] == "Bearer k"
        assert payload["model"] == "groq-model"
        assert payload["messages"][0] == {"role": "system", "content": "sys"}
        assert payload["messages"][-1] == {"role": "user", "content": "hi"}
        assert payload["response_format"] == {"type": "json_object"}
        assert llm.last_provider == "groq"

    def test_json_mode_not_sent_to_providers_without_support(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            llm_module.requests, "post",
            lambda url, headers=None, json=None, timeout=None: seen.update(json) or chat("{}"),
        )
        LLMClient(providers=[provider("openrouter", json_mode=False)]).generate("x", json_mode=True)
        assert "response_format" not in seen

    def test_falls_back_to_next_provider(self, monkeypatch):
        def fake_post(url, headers=None, json=None, timeout=None):
            if "groq" in url:
                return FakeResponse(500, text="boom")
            return chat("from gemini")

        monkeypatch.setattr(llm_module.requests, "post", fake_post)
        llm = LLMClient(providers=[provider("groq"), provider("gemini")])
        assert llm.generate("hi") == "from gemini"
        assert llm.last_provider == "gemini"

    def test_failed_provider_is_skipped_while_cooling_down(self, monkeypatch):
        hits = []

        def fake_post(url, headers=None, json=None, timeout=None):
            hits.append(url)
            if "groq" in url:
                return FakeResponse(429, text="rate limited, retry after 30s")
            return chat("ok")

        monkeypatch.setattr(llm_module.requests, "post", fake_post)
        llm = LLMClient(providers=[provider("groq"), provider("gemini")])
        llm.generate("one")
        hits.clear()
        llm.generate("two")
        assert all("gemini" in url for url in hits)  # groq not retried yet

    def test_all_providers_down_raises_connection_error(self, monkeypatch):
        def fake_post(*args, **kwargs):
            raise llm_module.requests.ConnectionError("offline")

        monkeypatch.setattr(llm_module.requests, "post", fake_post)
        llm = LLMClient(providers=[provider("groq")])
        with pytest.raises(LLMUnavailableError):
            llm.generate("hi")
        assert isinstance(LLMUnavailableError("x"), ConnectionError)

    def test_rate_limited_only_provider_fails_fast(self, monkeypatch):
        calls = []

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append(url)
            return FakeResponse(402, text='{"message": "Free limit reached. Retry after 30s"}')

        monkeypatch.setattr(llm_module.requests, "post", fake_post)
        llm = LLMClient(providers=[provider("pollinations")])
        with pytest.raises(LLMUnavailableError):
            llm.generate("one")
        calls.clear()
        with pytest.raises(LLMUnavailableError, match="rate limited"):
            llm.generate("two")
        assert calls == []  # no network call while the long cooldown is active

    def test_strips_reasoning_blocks(self, monkeypatch):
        monkeypatch.setattr(
            llm_module.requests, "post",
            lambda *a, **k: chat("<think>let me think</think>\nFinal answer"),
        )
        assert LLMClient(providers=[provider("groq")]).generate("x") == "Final answer"

    def test_no_providers_configured(self):
        with pytest.raises(LLMUnavailableError):
            LLMClient(providers=[]).generate("x")


class Answer(BaseModel):
    city: str
    days: int


class TestStructuredOutput:
    def test_extract_json_variants(self):
        llm = LLMClient(providers=[])
        assert llm._extract_json('{"a": 1}') == {"a": 1}
        assert llm._extract_json('```json\n{"a": 2}\n```') == {"a": 2}
        assert llm._extract_json('Sure! Here it is: {"a": 3} hope it helps') == {"a": 3}
        assert llm._extract_json("[1, 2]") == [1, 2]
        with pytest.raises(ValueError):
            llm._extract_json("no json here")

    def test_structured_success(self, monkeypatch):
        monkeypatch.setattr(llm_module.requests, "post",
                            lambda *a, **k: chat('```json\n{"city": "Goa", "days": 3}\n```'))
        result = LLMClient(providers=[provider("groq")]).generate_structured("p", Answer)
        assert result == Answer(city="Goa", days=3)

    def test_structured_retries_then_succeeds(self, monkeypatch):
        replies = iter(["not json at all", '{"city": "Goa", "days": 2}'])
        prompts = []

        def fake_post(url, headers=None, json=None, timeout=None):
            prompts.append(json["messages"][-1]["content"])
            return chat(next(replies))

        monkeypatch.setattr(llm_module.requests, "post", fake_post)
        result = LLMClient(providers=[provider("groq")], max_retries=2).generate_structured("p", Answer)
        assert result.days == 2
        assert "previous response was not valid JSON" in prompts[1]

    def test_structured_gives_up_with_runtime_error(self, monkeypatch):
        monkeypatch.setattr(llm_module.requests, "post", lambda *a, **k: chat('{"city": "Goa"}'))
        with pytest.raises(RuntimeError):
            LLMClient(providers=[provider("groq")], max_retries=1).generate_structured("p", Answer)

    def test_structured_rejects_json_arrays(self, monkeypatch):
        monkeypatch.setattr(llm_module.requests, "post", lambda *a, **k: chat("[1, 2, 3]"))
        with pytest.raises(RuntimeError):
            LLMClient(providers=[provider("groq")], max_retries=0).generate_structured("p", Answer)
