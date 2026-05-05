import os
import json
import threading
import urllib.error
import urllib.request
from typing import Any, AsyncIterable, Dict, List

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

    async def stream_generate(self, request: GenerateRequest) -> AsyncIterable[str]:
        if request.response_format is not None:
            response = await self.generate(request)
            yield response.text
            return

        model = request.model or self.default_model
        if not model:
            raise ProviderError("%s requires a model" % self.name)
        endpoint = "/completions" if self.use_completions else "/chat/completions"
        payload: Dict[str, Any] = {
            "model": model,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        if self.use_completions:
            payload["prompt"] = self._prompt(request.messages)
        else:
            payload["messages"] = self._messages(request.messages)

        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)

        import asyncio

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        def worker() -> None:
            try:
                for chunk in self._stream_chunks(self.base_url + endpoint, headers, payload):
                    loop.call_soon_threadsafe(queue.put_nowait, ("chunk", chunk))
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))

        threading.Thread(target=worker, daemon=True).start()
        saw_text = False
        while True:
            kind, value = await queue.get()
            if kind == "done":
                break
            if kind == "error":
                if isinstance(value, ProviderError):
                    raise value
                raise ProviderError("provider streaming failed: %s" % value) from value
            saw_text = True
            yield str(value)
        if not saw_text:
            raise ProviderError("%s streaming returned no text" % self.name)

    def _stream_chunks(self, url: str, headers: Dict[str, str], payload: Dict[str, Any]):
        request_headers = {
            "Accept": "text/event-stream",
            "User-Agent": "ReliabilityGraph/0.1",
        }
        request_headers.update(headers)
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        parsed = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    for chunk in self._text_from_stream_payload(parsed):
                        if chunk:
                            yield chunk
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ProviderError("provider HTTP %s: %s" % (exc.code, body[:600])) from exc
        except urllib.error.URLError as exc:
            raise ProviderError("provider request failed: %s" % exc.reason) from exc
        except (TimeoutError, OSError) as exc:
            raise ProviderError("provider request failed: %s" % exc) from exc

    def _text_from_stream_payload(self, payload: Dict[str, Any]) -> List[str]:
        chunks: List[str] = []
        for choice in payload.get("choices") or []:
            delta = choice.get("delta") or {}
            text = delta.get("content") or delta.get("text") or choice.get("text") or ""
            if isinstance(text, list):
                text = "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in text)
            if text:
                chunks.append(str(text))
        return chunks

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
