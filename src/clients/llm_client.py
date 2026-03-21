from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env")


@dataclass
class BaseLLMClient(ABC):
    model: str
    temperature: float = 0.2

    @abstractmethod
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        pass


@dataclass
class OpenAIClient(BaseLLMClient):
    client: OpenAI = None

    @classmethod
    def build(cls) -> "OpenAIClient":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = os.getenv("OPENAI_API_BASE", "").strip() or None
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2").strip() or "0.2")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        client = OpenAI(api_key=api_key, base_url=base_url)
        return cls(client=client, model=model, temperature=temperature)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            tools=tools,
            tool_choice="auto" if tools else None,
        )
        return response.choices[0].message.model_dump()

