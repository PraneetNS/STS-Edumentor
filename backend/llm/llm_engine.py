"""
EduMentor Voice — LLM Streaming Engine

Communicates with a local llama.cpp server via its OpenAI-compatible
streaming API. Tokens are yielded one-by-one as they are generated —
no waiting for the full response.
"""

import json
import logging
from typing import AsyncIterator

import httpx

from config import Config

logger = logging.getLogger(__name__)


class LLMEngine:
    """
    Async LLM engine that streams tokens from a local llama.cpp server.

    The HTTP client is created once and reused for all requests,
    keeping the connection pool alive for lower per-request overhead.
    """

    def __init__(self) -> None:
        self.base_url = Config.LLM_BASE_URL
        # Long timeout because generation can take time; streaming keeps it alive
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=10.0, read=Config.LLM_TIMEOUT, write=10.0, pool=10.0),
            headers={"Content-Type": "application/json"},
        )
        logger.info("[OK] LLM engine ready -> %s", self.base_url)

    async def stream_tokens(self, user_text: str) -> AsyncIterator[str]:
        """
        Stream tokens from the LLM for a given user input.

        Backward-compatible method: builds a simple two-message conversation
        using the default system prompt from Config.

        NOTE: When the AgentController is active, stream_tokens_from_messages()
        is called instead, which uses a fully assembled agent prompt.

        Args:
            user_text: The user's transcribed speech.

        Yields:
            Individual token strings.
        """
        messages = [
            {"role": "system", "content": Config.LLM_SYSTEM_PROMPT},
            {"role": "user",   "content": user_text},
        ]
        async for token in self.stream_tokens_from_messages(messages):
            yield token

    async def stream_tokens_from_messages(
        self,
        messages: list,
    ) -> AsyncIterator[str]:
        """
        Stream tokens from the LLM using a pre-built messages list.

        This is the primary method used by AgentController, which constructs
        the full chat history, system prompt, and context via PromptBuilder.

        Parsing follows the OpenAI Server-Sent Events (SSE) format.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.

        Yields:
            Individual token strings.
        """
        payload = {
            "model":          Config.LLM_MODEL_NAME,
            "messages":       messages,
            "stream":         True,
            "max_tokens":     Config.LLM_MAX_TOKENS,
            "temperature":    Config.LLM_TEMPERATURE,
            "top_p":          Config.LLM_TOP_P,
            "repeat_penalty": Config.LLM_REPEAT_PENALTY,
            # Qwen ChatML stop tokens — prevent model bleeding past turn boundaries
            "stop": ["<|im_end|>", "<|im_start|>", "<|endoftext|>"],
        }

        logger.info(
            "LLM <- %d messages, first_user=%r",
            len(messages),
            next(
                (m["content"][:60] for m in messages if m["role"] == "user"),
                ""
            ),
        )

        try:
            async with self.client.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as response:
                response.raise_for_status()

                async for raw_line in response.aiter_lines():
                    # SSE lines look like:  data: {...}
                    if not raw_line.startswith("data: "):
                        continue

                    data_str = raw_line[6:].strip()
                    if data_str == "[DONE]":
                        logger.info("LLM generation complete.")
                        return

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        yield token

        except httpx.ConnectError:
            logger.error(
                "Cannot connect to llama.cpp server at %s. "
                "Make sure run_llm_server.bat is running.",
                self.base_url,
            )
            yield "[Error: LLM server not reachable]"
        except Exception as exc:
            logger.exception("LLM streaming error: %s", exc)
            yield f"[Error: {exc}]"

    async def aclose(self) -> None:
        """Gracefully close the HTTP client on shutdown."""
        await self.client.aclose()
