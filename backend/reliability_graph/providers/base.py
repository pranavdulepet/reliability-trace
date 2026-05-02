import json
from dataclasses import dataclass
from typing import Any, AsyncIterable, Dict, List, Optional


@dataclass
class ModelMessage:
    role: str
    content: str


@dataclass
class GenerateRequest:
    messages: List[ModelMessage]
    model: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 900
    response_format: Optional[Dict[str, Any]] = None


@dataclass
class GenerateResponse:
    text: str
    model: str
    provider: str
    raw: Dict[str, Any]
    usage: Optional[Dict[str, Any]] = None


class ProviderError(RuntimeError):
    pass


class ModelProvider:
    name = "provider"

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        raise NotImplementedError

    async def stream_generate(self, request: GenerateRequest) -> AsyncIterable[str]:
        response = await self.generate(request)
        yield response.text

    async def generate_structured(self, request: GenerateRequest) -> Dict[str, Any]:
        response = await self.generate(request)
        try:
            return json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise ProviderError("provider did not return valid JSON") from exc
