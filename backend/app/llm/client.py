"""
PlanWise AI - Hosted LLM Client

Single controlled interface to free, hosted LLM APIs. Every supported
provider speaks the OpenAI "chat completions" protocol, so one client
covers them all:

    groq         https://console.groq.com        (free API key)
    gemini       https://aistudio.google.com     (free API key)
    openrouter   https://openrouter.ai           (free API key, ":free" models)
    pollinations https://text.pollinations.ai    (no key required)
    ollama       local, optional
    custom       any other OpenAI-compatible endpoint

With LLM_PROVIDER=auto the client builds a fallback chain from every
provider that is configured and finishes with the keyless endpoint, so
the app answers from a live API even with zero setup.

No other module should make direct LLM calls.
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

import requests
from pydantic import BaseModel, ValidationError

from app import config

logger = logging.getLogger(__name__)


@dataclass
class Provider:
    """One OpenAI-compatible chat endpoint."""
    name: str
    url: str
    model: str
    api_key: str = ""
    json_mode: bool = True
    extra_headers: Optional[Dict[str, str]] = None
    extra_payload: Optional[Dict[str, Any]] = None
    timeout: Optional[int] = None


def _known_providers() -> Dict[str, Provider]:
    return {
        "groq": Provider(
            name="groq",
            url="https://api.groq.com/openai/v1/chat/completions",
            model=config.GROQ_MODEL,
            api_key=config.GROQ_API_KEY,
        ),
        "gemini": Provider(
            name="gemini",
            url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            model=config.GEMINI_MODEL,
            api_key=config.GEMINI_API_KEY,
        ),
        "openrouter": Provider(
            name="openrouter",
            url="https://openrouter.ai/api/v1/chat/completions",
            model=config.OPENROUTER_MODEL,
            api_key=config.OPENROUTER_API_KEY,
            json_mode=False,
            extra_headers={"X-Title": "PlanWise AI"},
        ),
        "custom": Provider(
            name="custom",
            url=config.CUSTOM_LLM_BASE_URL.rstrip("/") + "/chat/completions"
            if config.CUSTOM_LLM_BASE_URL else "",
            model=config.CUSTOM_LLM_MODEL,
            api_key=config.CUSTOM_LLM_API_KEY,
            json_mode=False,
        ),
        "pollinations": Provider(
            name="pollinations",
            url=config.POLLINATIONS_BASE_URL,
            model=config.POLLINATIONS_MODEL,
            json_mode=False,
            # The keyless model is a small reasoning model: keep its thinking
            # short so the answer fits, and give it time (it is slow).
            extra_payload={"reasoning_effort": "low"},
            timeout=max(config.LLM_TIMEOUT, 120),
        ),
        "ollama": Provider(
            name="ollama",
            url=config.OLLAMA_BASE_URL.rstrip("/") + "/v1/chat/completions",
            model=config.OLLAMA_MODEL,
            json_mode=False,
        ),
    }


def build_provider_chain(preferred: Optional[str] = None) -> List[Provider]:
    """Resolve LLM_PROVIDER into an ordered list of providers to try."""
    known = _known_providers()
    preferred = (preferred or config.LLM_PROVIDER or "auto").lower()

    chain: List[Provider] = []
    if preferred != "auto":
        chosen = known.get(preferred)
        if chosen is None:
            logger.warning(f"Unknown LLM_PROVIDER '{preferred}', using auto")
        elif not chosen.url or (preferred in ("groq", "gemini", "openrouter") and not chosen.api_key):
            logger.warning(f"LLM_PROVIDER '{preferred}' is not configured (missing key/URL), using auto")
        else:
            chain.append(chosen)

    # Every hosted provider that has a key, in priority order
    for name in ("groq", "gemini", "openrouter", "custom"):
        p = known[name]
        if p.api_key and p.url and p not in chain:
            chain.append(p)

    # Keyless endpoint is always the final fallback (unless running fully local)
    if preferred != "ollama" and known["pollinations"] not in chain:
        chain.append(known["pollinations"])

    return chain


class LLMUnavailableError(ConnectionError):
    """Raised when no LLM provider could be reached."""


class LLMClient:
    """Centralized LLM service with provider fallback."""

    # A provider that failed is skipped for this many seconds
    COOLDOWN_SECONDS = 45
    # Longest we are willing to sleep waiting for a rate-limited provider
    MAX_WAIT_SECONDS = 8

    def __init__(
        self,
        providers: Optional[List[Provider]] = None,
        timeout: int = config.LLM_TIMEOUT,
        max_retries: int = config.LLM_MAX_RETRIES,
    ):
        self.providers = providers if providers is not None else build_provider_chain()
        self.timeout = timeout
        self.max_retries = max_retries
        self._cooldown_until: Dict[str, float] = {}
        self.last_provider: Optional[str] = None
        self._availability: Optional[bool] = None
        self._availability_checked_at: float = 0.0

    # ── Introspection ────────────────────────────────────────────

    @property
    def provider_name(self) -> str:
        return self.last_provider or (self.providers[0].name if self.providers else "none")

    @property
    def model(self) -> str:
        for p in self.providers:
            if p.name == self.provider_name:
                return p.model
        return ""

    @property
    def frugal(self) -> bool:
        """
        True when only the keyless endpoint is configured. It allows roughly
        one reply every 45 seconds, so callers should spend their single LLM
        call on the answer itself and use rule-based logic for the rest.
        """
        return all(p.name == "pollinations" for p in self.providers)

    def describe(self) -> List[str]:
        return [f"{p.name}:{p.model}" for p in self.providers]

    def is_available(self, max_age: int = 300) -> bool:
        """Check (and cache) whether at least one provider answers."""
        now = time.time()
        if self._availability is not None and now - self._availability_checked_at < max_age:
            return self._availability
        try:
            self.generate("Reply with the single word: ok", temperature=0.0, max_tokens=64)
            self._availability = True
        except Exception as e:
            logger.warning(f"LLM availability check failed: {e}")
            self._availability = False
        self._availability_checked_at = now
        return self._availability

    # ── Generation ───────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        json_mode: bool = False,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Generate a text response, trying each provider in the chain.

        Raises:
            LLMUnavailableError (a ConnectionError): if every provider fails
        """
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        errors: List[str] = []
        if not self.providers:
            raise LLMUnavailableError("No LLM provider is configured.")

        now = time.time()
        candidates = [p for p in self.providers if self._cooldown_until.get(p.name, 0) <= now]
        if not candidates:
            # Everything is cooling down (rate limited). Wait briefly if the
            # soonest one is nearly ready, otherwise fail fast so the agent
            # can fall back to its deterministic logic.
            soonest = min(self.providers, key=lambda p: self._cooldown_until.get(p.name, 0))
            wait = self._cooldown_until.get(soonest.name, 0) - now
            if wait > self.MAX_WAIT_SECONDS:
                raise LLMUnavailableError(
                    f"LLM providers are rate limited (next slot in ~{int(wait)}s)."
                )
            time.sleep(max(wait, 0) + 0.2)
            candidates = [soonest]

        for provider in candidates:
            try:
                content = self._call(provider, messages, temperature, max_tokens, json_mode)
                if content:
                    self.last_provider = provider.name
                    self._availability = True
                    self._availability_checked_at = time.time()
                    return content
                errors.append(f"{provider.name}: empty response")
            except Exception as e:
                errors.append(f"{provider.name}: {e}")
                logger.warning(f"LLM provider {provider.name} failed: {str(e)[:160]}")
                cooldown = getattr(e, "retry_after", None) or self.COOLDOWN_SECONDS
                self._cooldown_until[provider.name] = time.time() + cooldown

        raise LLMUnavailableError(
            "No LLM provider is reachable right now. " + " | ".join(errors)
        )

    def _call(
        self,
        provider: Provider,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        if provider.extra_headers:
            headers.update(provider.extra_headers)

        payload: Dict[str, Any] = {
            "model": provider.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode and provider.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if provider.extra_payload:
            payload.update(provider.extra_payload)

        logger.debug(f"LLM request → {provider.name} ({provider.model})")

        resp = None
        for attempt in range(2):
            resp = requests.post(
                provider.url, headers=headers, json=payload,
                timeout=provider.timeout or self.timeout,
            )
            if resp.status_code in (402, 429, 500, 502, 503):
                retry_after = self._retry_after(resp)
                # One short in-place retry; longer waits become a cooldown
                if attempt == 0 and retry_after <= self.MAX_WAIT_SECONDS:
                    time.sleep(retry_after)
                    continue
                err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                err.retry_after = retry_after  # type: ignore[attr-defined]
                raise err
            break

        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

        # The keyless endpoint allows ~1 reply per 45s per IP: pace ourselves
        if provider.name == "pollinations":
            self._cooldown_until[provider.name] = time.time() + 45

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"No choices in response: {str(data)[:200]}")
        content = (choices[0].get("message") or {}).get("content") or ""
        return self._clean(content)

    @staticmethod
    def _retry_after(resp) -> float:
        """Seconds the provider asked us to wait (header or message body)."""
        header = resp.headers.get("Retry-After", "")
        if header.replace(".", "", 1).isdigit():
            return float(header)
        match = re.search(r"[Rr]etry after (\d+(?:\.\d+)?)\s*s", resp.text or "")
        if match:
            return float(match.group(1)) + 1
        match = re.search(r"try again in (\d+(?:\.\d+)?)\s*s", resp.text or "")
        if match:
            return float(match.group(1)) + 1
        return 3.0

    @staticmethod
    def _clean(text: str) -> str:
        """Strip reasoning blocks some open models prepend to their answer."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        return text.strip()

    def generate_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system: Optional[str] = None,
        temperature: float = 0.1,
    ) -> BaseModel:
        """
        Generate structured output matching a Pydantic schema.

        Retries with a correction prompt (up to max_retries) when the
        response is not valid JSON for the schema.

        Raises:
            RuntimeError: If structured output cannot be obtained after retries
            LLMUnavailableError: If no provider is reachable
        """
        last_error = None

        for attempt in range(1 + self.max_retries):
            if attempt == 0:
                current_prompt = prompt
            else:
                current_prompt = (
                    f"{prompt}\n\n"
                    f"IMPORTANT: Your previous response was not valid JSON. "
                    f"Error: {last_error}\n"
                    f"Please respond with ONLY valid JSON matching the schema. "
                    f"No markdown, no explanation, just the JSON object."
                )

            raw_response = self.generate(
                current_prompt,
                system=system,
                temperature=temperature,
                json_mode=True,
            )

            try:
                parsed = self._extract_json(raw_response)
                if not isinstance(parsed, dict):
                    raise ValueError("Expected a JSON object")
                result = schema.model_validate(parsed)
                logger.info(f"Structured output parsed successfully (attempt {attempt + 1})")
                return result
            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                last_error = str(e)[:200]
                logger.warning(
                    f"Structured output parse failed (attempt {attempt + 1}): {last_error}"
                )
                logger.debug(f"Raw LLM response was: {raw_response[:500]}")

        raise RuntimeError(
            f"Failed to get valid structured output after "
            f"{1 + self.max_retries} attempts. Last error: {last_error}"
        )

    def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Any:
        """Generate and parse free-form JSON (object or array)."""
        raw = self.generate(prompt, system=system, temperature=temperature, json_mode=True)
        return self._extract_json(raw)

    def _extract_json(self, text: str) -> Any:
        """
        Extract JSON from LLM response text.

        Handles pure JSON, JSON wrapped in markdown code blocks, and JSON
        with surrounding prose.
        """
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        code_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        for match in re.findall(code_block_pattern, text, re.DOTALL):
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            start = text.find(open_ch)
            end = text.rfind(close_ch)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass

        raise ValueError("Could not extract valid JSON from LLM response")


# Shared instance so provider cooldowns / availability are tracked once
_shared_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = LLMClient()
        logger.info(f"LLM provider chain: {_shared_client.describe()}")
    return _shared_client
