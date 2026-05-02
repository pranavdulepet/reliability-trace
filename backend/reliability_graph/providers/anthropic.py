import asyncio
import os
from typing import Any, Dict

from .base import GenerateRequest, GenerateResponse, ModelProvider, ProviderError
from .http import post_json


class AnthropicProvider(ModelProvider):
    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.default_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        model = request.model or self.default_model
        system = "\n\n".join([m.content for m in request.messages if m.role == "system"])
        messages = [{"role": m.role, "content": m.content} for m in request.messages if m.role != "system"]
        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        result = await asyncio.to_thread(
            post_json,
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload,
        )
        parts = result.get("content") or []
        text = "".join([str(part.get("text", "")) for part in parts if part.get("type") == "text"])
        if not text:
            raise ProviderError("anthropic returned no text")
        usage = result.get("usage")
        return GenerateResponse(text=text, model=str(result.get("model") or model), provider=self.name, raw=result, usage=usage)
