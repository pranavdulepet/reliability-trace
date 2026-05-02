import asyncio
import os
from typing import Any, Dict, List

from .base import GenerateRequest, GenerateResponse, ModelProvider, ProviderError
from .http import post_json


class GeminiProvider(ModelProvider):
    name = "gemini"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.default_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        model = request.model or self.default_model
        system_text = "\n\n".join([m.content for m in request.messages if m.role == "system"])
        user_text = "\n\n".join([m.content for m in request.messages if m.role != "system"])
        if system_text:
            user_text = system_text + "\n\n" + user_text
        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        result = await asyncio.to_thread(
            post_json,
            "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model,
            {
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            payload,
        )
        candidates: List[Dict[str, Any]] = result.get("candidates") or []
        if not candidates:
            raise ProviderError("gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join([str(part.get("text", "")) for part in parts])
        if not text:
            raise ProviderError("gemini returned no text")
        return GenerateResponse(text=text, model=model, provider=self.name, raw=result, usage=result.get("usageMetadata"))
