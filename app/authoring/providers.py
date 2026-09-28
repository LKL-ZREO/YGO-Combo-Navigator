from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class DraftProvider(Protocol):
    def generate(self, prompt: str, schema: dict) -> object: ...


def parse_json_response(value: str) -> object:
    text = value.strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        lines = text.splitlines()
        if lines and lines[0].startswith(fence):
            lines = lines[1:]
        if lines and lines[-1].strip() == fence:
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"AI response is not valid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


@dataclass(slots=True)
class OpenAIResponsesProvider:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout: float = 180.0

    def generate(self, prompt: str, schema: dict) -> object:
        if not self.api_key.strip():
            raise ValueError("OpenAI API key is empty")
        endpoint = f"{self.base_url.rstrip('/')}/responses"
        body = {
            "model": self.model,
            "input": prompt,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "combo_draft",
                    "description": "A compilable Yu-Gi-Oh! ComboDraft object",
                    "schema": schema,
                    "strict": False,
                }
            },
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "YGOComboNavigator/0.2 (+deck-pack-authoring)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            raise ValueError(f"OpenAI API returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ValueError(f"OpenAI API request failed: {exc}") from exc
        return parse_json_response(self._output_text(payload))

    @staticmethod
    def _output_text(payload: dict) -> str:
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        parts: list[str] = []
        refusals: list[str] = []
        for item in payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "output_text" and content.get("text"):
                    parts.append(str(content["text"]))
                elif content.get("type") == "refusal" and content.get("refusal"):
                    refusals.append(str(content["refusal"]))
        if parts:
            return "".join(parts)
        if refusals:
            raise ValueError(f"AI refused to create the combo draft: {'; '.join(refusals)}")
        error = payload.get("error")
        if error:
            raise ValueError(f"OpenAI API response failed: {error}")
        raise ValueError("OpenAI API response contains no output text")
