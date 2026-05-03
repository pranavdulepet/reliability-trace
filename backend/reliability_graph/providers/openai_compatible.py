import os
from typing import Any, Dict, List

from .base import GenerateRequest, GenerateResponse, ModelMessage, ModelProvider, ProviderError
from .async_utils import run_blocking
from .http import post_json


class OpenAICompatibleProvider(ModelProvider):
    def __init__(
        self,
        name: str,
        api_key: str,
        base_url: str,
        default_model: str,
        extra_headers: Dict[str, str] = None,
        use_completions: bool = False,
    ) -> None:
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.extra_headers = extra_headers or {}
        self.use_completions = use_completions

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        model = request.model or self.default_model
        if not model:
            raise ProviderError("%s requires a model" % self.name)
        if self.use_completions:
            return await self._generate_completion(request, model)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": self._messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format is not None:
            payload["response_format"] = request.response_format

        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)
        result = await run_blocking(
            post_json,
            self.base_url + "/chat/completions",
            headers,
            payload,
        )
        choices = result.get("choices") or []
        if not choices:
            raise ProviderError("%s returned no choices" % self.name)
        message = choices[0].get("message") or {}
        text = message.get("content") or choices[0].get("text") or ""
        return GenerateResponse(
            text=str(text),
            model=str(result.get("model") or model),
            provider=self.name,
            raw=result,
            usage=result.get("usage"),
        )

    def _messages(self, messages: List[ModelMessage]) -> List[Dict[str, str]]:
        return [{"role": message.role, "content": message.content} for message in messages]

    async def _generate_completion(self, request: GenerateRequest, model: str) -> GenerateResponse:
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": self._prompt(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)
        result = await run_blocking(
            post_json,
            self.base_url + "/completions",
            headers,
            payload,
        )
        choices = result.get("choices") or []
        if not choices:
            raise ProviderError("%s returned no choices" % self.name)
        return GenerateResponse(
            text=str(choices[0].get("text") or ""),
            model=str(result.get("model") or model),
            provider=self.name,
            raw=result,
            usage=result.get("usage"),
        )

    def _prompt(self, messages: List[ModelMessage]) -> str:
        system = [message.content for message in messages if message.role == "system"]
        turns = [message for message in messages if message.role != "system"]
        sections = []
        if system:
            sections.append("### Instructions\n" + "\n\n".join(system))
        if turns:
            conversation = []
            for message in turns[:-1]:
                role = "Assistant" if message.role == "assistant" else "User"
                conversation.append("%s: %s" % (role, message.content))
            if conversation:
                sections.append("### Conversation\n" + "\n\n".join(conversation))
            final = turns[-1]
            final_label = "Assistant" if final.role == "assistant" else "User"
            sections.append("### %s\n%s" % (final_label, final.content))
        sections.append("### Answer\n")
        return "\n\n".join(sections)


def openai_provider(api_key: str) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="openai",
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        default_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
    )


def openrouter_provider(api_key: str) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="openrouter",
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini"),
        extra_headers={
            "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "http://localhost:5173"),
            "X-OpenRouter-Title": "ReliabilityGraph",
        },
    )


def tinker_provider(api_key: str) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="tinker",
        api_key=api_key,
        base_url=os.getenv(
            "TINKER_BASE_URL",
            "https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1",
        ),
        default_model=os.getenv("TINKER_MODEL", "meta-llama/Llama-3.1-8B-Instruct"),
        use_completions=os.getenv("TINKER_ENDPOINT", "chat") == "completions",
    )
