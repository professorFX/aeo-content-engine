"""LLM clients with structured (schema-validated) JSON output.

AnthropicClient calls the Messages API with retries; FixtureClient replays saved outputs so the
whole pipeline can run offline in tests and demos.
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

import jsonschema

from .skills import Skill


class LLMError(RuntimeError):
    pass


def extract_json(text: str) -> Any:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("No JSON object in model output")
    return json.loads(text[start:end + 1])


class LLMClient(Protocol):
    def run_skill(self, skill: Skill, variables: dict[str, Any], *, item: str = "", attempt: int = 0) -> dict: ...


class AnthropicClient:
    url = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str, max_retries: int = 4, schema_retries: int = 1, timeout_s: int = 120):
        self.api_key, self.model = api_key, model
        self.max_retries, self.schema_retries, self.timeout_s = max_retries, schema_retries, timeout_s
        self.usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0}

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload).encode()
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(self.url, data=body, method="POST", headers={
                "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                retryable = e.code in (408, 429, 500, 502, 503, 529)
                if not retryable or attempt == self.max_retries:
                    raise LLMError(f"Anthropic API {e.code}: {e.read()[:300]!r}") from e
            except urllib.error.URLError as e:
                if attempt == self.max_retries:
                    raise LLMError(f"Network error: {e}") from e
            time.sleep(min(30, 2 ** attempt + random.random()))
        raise LLMError("unreachable")

    def run_skill(self, skill: Skill, variables: dict[str, Any], *, item: str = "", attempt: int = 0) -> dict:
        system, prompt = skill.render(variables)
        messages = [{"role": "user", "content": prompt}]
        last_error = ""
        for _ in range(self.schema_retries + 1):
            if last_error:
                messages = messages + [{"role": "user", "content":
                    f"Your previous output was invalid: {last_error}. Return only the corrected JSON object."}]
            resp = self._post({"model": self.model, "max_tokens": skill.max_tokens, "system": system, "messages": messages})
            self.usage["calls"] += 1
            for k in ("input_tokens", "output_tokens"):
                self.usage[k] += resp.get("usage", {}).get(k, 0)
            text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
            try:
                data = extract_json(text)
                skill.validate_output(data)
                return data
            except (json.JSONDecodeError, LLMError, jsonschema.ValidationError) as e:
                last_error = getattr(e, "message", str(e))[:300]
                messages = messages + [{"role": "assistant", "content": text}]
        raise LLMError(f"Skill {skill.name} output failed validation: {last_error}")


class FixtureClient:
    """Replays fixtures/<skill>/<item>[.attemptN].json. Validates them like real output."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.calls: list[tuple[str, str, int]] = []

    def run_skill(self, skill: Skill, variables: dict[str, Any], *, item: str = "", attempt: int = 0) -> dict:
        skill.render(variables)  # proves every template variable is supplied
        self.calls.append((skill.name, item, attempt))
        base = self.folder / skill.name
        candidates = [base / f"{item}.attempt{attempt}.json", base / f"{item}.json", base / "default.json"]
        for path in candidates:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                skill.validate_output(data)
                return data
        raise LLMError(f"No fixture for {skill.name}/{item} (attempt {attempt})")
