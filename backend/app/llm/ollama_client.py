"""
PlanWise AI - Ollama LLM Client

Single controlled interface to Qwen2.5-3B-Instruct via Ollama.
No other module should make direct Ollama calls.
"""

import json
import logging
import re
from typing import Any, Dict, Optional, Type

import requests
from pydantic import BaseModel, ValidationError

from app.config import (
    LLM_MAX_RETRIES,
    LLM_TIMEOUT,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)

logger = logging.getLogger(__name__)


class OllamaClient:
    """Centralized LLM service for all Qwen2.5-3B-Instruct interactions."""

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        timeout: int = LLM_TIMEOUT,
        max_retries: int = LLM_MAX_RETRIES,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def is_available(self) -> bool:
        """Check if Ollama is reachable and the model is loaded."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code != 200:
                return False
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            # Check if our model (or a close match) is available
            for name in model_names:
                if self.model.split(":")[0] in name:
                    return True
            # If no models listed but server is up, still might work
            return resp.status_code == 200
        except (requests.ConnectionError, requests.Timeout):
            return False

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        """
        Generate a text response from the LLM.

        Args:
            prompt: The user/instruction prompt
            system: Optional system prompt
            temperature: Sampling temperature (lower = more deterministic)

        Returns:
            Generated text string

        Raises:
            ConnectionError: If Ollama is unreachable
            RuntimeError: If generation fails
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 4096,
            },
        }

        try:
            logger.debug(f"LLM request: model={self.model}, prompt_len={len(prompt)}")
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            result = resp.json()
            content = result.get("message", {}).get("content", "")
            logger.debug(f"LLM response: len={len(content)}")
            return content.strip()

        except requests.ConnectionError:
            logger.error("Ollama is not reachable")
            raise ConnectionError(
                "Cannot connect to Ollama. Please ensure Ollama is running "
                f"at {self.base_url}"
            )
        except requests.Timeout:
            logger.error(f"Ollama request timed out after {self.timeout}s")
            raise RuntimeError("LLM request timed out. The model may be loading.")
        except requests.HTTPError as e:
            logger.error(f"Ollama HTTP error: {e}")
            raise RuntimeError(f"LLM service error: {e}")

    def generate_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system: Optional[str] = None,
        temperature: float = 0.1,
    ) -> BaseModel:
        """
        Generate structured output matching a Pydantic schema.

        Attempts to parse the LLM response as JSON conforming to the schema.
        If parsing fails, retries with a correction prompt (up to max_retries).

        Args:
            prompt: The instruction prompt (should request JSON output)
            schema: Pydantic model class to validate against
            system: Optional system prompt
            temperature: Lower for more deterministic structured output

        Returns:
            Validated Pydantic model instance

        Raises:
            RuntimeError: If structured output cannot be obtained after retries
        """
        last_error = None

        for attempt in range(1 + self.max_retries):
            if attempt == 0:
                current_prompt = prompt
            else:
                # Retry with correction prompt
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
            )

            try:
                parsed = self._extract_json(raw_response)
                result = schema.model_validate(parsed)
                logger.info(
                    f"Structured output parsed successfully "
                    f"(attempt {attempt + 1})"
                )
                return result
            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                last_error = str(e)[:200]
                logger.warning(
                    f"Structured output parse failed (attempt {attempt + 1}): "
                    f"{last_error}"
                )
                logger.debug(f"Raw LLM response was: {raw_response[:500]}")

        raise RuntimeError(
            f"Failed to get valid structured output after "
            f"{1 + self.max_retries} attempts. Last error: {last_error}"
        )

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """
        Extract JSON from LLM response text.

        Handles common LLM output patterns:
        - Pure JSON
        - JSON wrapped in markdown code blocks
        - JSON with surrounding text
        """
        text = text.strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code blocks
        code_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        matches = re.findall(code_block_pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # Try finding JSON object in the text
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            candidate = text[brace_start : brace_end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # Try finding JSON array
        bracket_start = text.find("[")
        bracket_end = text.rfind("]")
        if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
            candidate = text[bracket_start : bracket_end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not extract valid JSON from LLM response")
