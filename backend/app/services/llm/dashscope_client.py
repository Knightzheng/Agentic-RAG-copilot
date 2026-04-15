"""DashScope 的向量、重排与聊天能力封装。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import httpx
import orjson

from app.core.config import settings
from app.services.chat.stream_control import RunCancelledError


@dataclass(slots=True)
class RerankItem:
    """重排接口返回的一条结果。"""

    index: int
    relevance_score: float
    document: str | None = None


@dataclass(slots=True)
class ChatStreamEvent:
    """流式聊天过程中产生的一条事件。"""

    event: str
    text: str = ""
    usage: dict | None = None
    finish_reason: str | None = None


class DashScopeClient:
    """基于 OpenAI 兼容接口的最小 DashScope 客户端封装。"""

    def __init__(self, api_key: str | None = None, timeout: float = 120.0) -> None:
        self.api_key = api_key or settings.dashscope_api_key
        if not self.api_key:
            raise RuntimeError("缺少 ATLAS_DASHSCOPE_API_KEY，无法调用 DashScope。")
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Call `text-embedding-v4` to create embeddings."""

        embeddings: list[list[float]] = []
        with httpx.Client(timeout=self.timeout) as client:
            for start in range(0, len(texts), 10):
                batch = texts[start : start + 10]
                payload = {
                    "model": settings.embedding_model,
                    "input": batch,
                    "dimensions": settings.embedding_dimensions,
                    "encoding_format": "float",
                }
                response = client.post(
                    settings.dashscope_embeddings_url,
                    headers=self._headers,
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
                data = sorted(body.get("data", []), key=lambda item: item["index"])
                embeddings.extend(item["embedding"] for item in data)
        return embeddings

    def rerank(self, query: str, documents: list[str], top_n: int) -> tuple[list[RerankItem], dict]:
        """Call `qwen3-rerank` to rerank retrieved candidates."""

        payload = {
            "model": settings.rerank_model,
            "input": {
                "query": query,
                "documents": documents,
            },
            "parameters": {
                "top_n": top_n,
                "instruct": "Given a web search query, retrieve relevant passages that answer the query.",
            },
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(settings.dashscope_rerank_url, headers=self._headers, json=payload)
            response.raise_for_status()
            body = response.json()

        result_items = body.get("output", {}).get("results")
        if result_items is None:
            result_items = body.get("results", [])

        results = [
            RerankItem(
                index=item["index"],
                relevance_score=item["relevance_score"],
                document=(item.get("document") or {}).get("text") if item.get("document") else None,
            )
            for item in result_items
        ]
        return results, body.get("usage", {})

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.1, max_tokens: int = 1200) -> tuple[str, dict]:
        """Call `qwen3-max` and return the full answer."""

        payload = {
            "model": settings.main_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(settings.dashscope_chat_url, headers=self._headers, json=payload)
            response.raise_for_status()
            body = response.json()

        message = body["choices"][0]["message"]["content"]
        if isinstance(message, list):
            text_parts = [part.get("text", "") for part in message if isinstance(part, dict)]
            content = "\n".join(part for part in text_parts if part).strip()
        else:
            content = str(message)
        return content, body.get("usage", {})

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 1200,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> Iterator[ChatStreamEvent]:
        """Call `qwen3-max` with SSE streaming enabled."""

        payload = {
            "model": settings.main_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream(
                "POST",
                settings.dashscope_chat_url,
                headers=self._headers,
                json=payload,
            ) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if cancel_checker is not None and cancel_checker():
                        response.close()
                        raise RunCancelledError("Run cancelled by user.")
                    if not line:
                        continue

                    text_line = line if isinstance(line, str) else line.decode("utf-8")
                    if not text_line.startswith("data:"):
                        continue

                    data = text_line[5:].strip()
                    if not data:
                        continue
                    if data == "[DONE]":
                        yield ChatStreamEvent(event="done")
                        break

                    body = orjson.loads(data)
                    usage = body.get("usage")
                    if usage:
                        yield ChatStreamEvent(event="usage", usage=usage)

                    choices = body.get("choices", [])
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})
                    content = delta.get("content")
                    finish_reason = choice.get("finish_reason")

                    if isinstance(content, list):
                        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
                        delta_text = "\n".join(part for part in text_parts if part)
                    else:
                        delta_text = str(content or "")

                    if delta_text:
                        yield ChatStreamEvent(event="delta", text=delta_text)
                    if finish_reason:
                        yield ChatStreamEvent(event="finish", finish_reason=str(finish_reason))
