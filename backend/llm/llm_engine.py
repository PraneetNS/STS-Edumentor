"""
EduMentor Voice — LLM Streaming Engine

Communicates with a local llama.cpp server via its OpenAI-compatible
streaming API. Tokens are yielded one-by-one as they are generated —
no waiting for the full response.
"""

import asyncio
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
        self.last_usage = None
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

        from llm.circuit_breaker import llm_circuit, CircuitOpenError
        import time

        async def call_llama_server():
            req = self.client.build_request("POST", "/v1/chat/completions", json=payload)
            resp = await self.client.send(req, stream=True)
            resp.raise_for_status()
            return resp

        try:
            response = await llm_circuit.call(call_llama_server)
        except CircuitOpenError:
            from agent.security_logger import log_security_event
            asyncio.create_task(log_security_event(None, "unknown", "circuit_breaker_open", "LLM circuit breaker is open"))
            logger.warning("[LLM] Circuit breaker is open — returning offline message")
            yield (
                "<speak>I'm currently offline, but the team is actively working to bring me "
                "back up. Thank you so much for your patience — I'll be with you very soon!</speak>"
            )
            return
        except (asyncio.TimeoutError, httpx.TimeoutException):
            logger.warning("[LLM] Request timed out")
            yield (
                "<speak>I'm currently offline, but the team is actively working to bring me "
                "back up. Thank you so much for your patience — I'll be with you very soon!</speak>"
            )
            return
        except (httpx.ConnectError, httpx.RemoteProtocolError, ConnectionRefusedError):
            logger.warning("[LLM] Cannot reach LLM server — returning offline message")
            yield (
                "<speak>I'm currently offline, but the team is actively working to bring me "
                "back up. Thank you so much for your patience — I'll be with you very soon!</speak>"
            )
            return
        except Exception as exc:
            logger.exception("[LLM] Unexpected error before streaming: %s", exc)
            yield (
                "<speak>I'm currently offline, but the team is actively working to bring me "
                "back up. Thank you so much for your patience — I'll be with you very soon!</speak>"
            )
            return

        try:
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
                if choices:
                    delta = choices[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        yield token

                if "usage" in chunk and chunk["usage"]:
                    self.last_usage = chunk["usage"]

        except Exception as exc:
            # Track stream reading failures toward circuit breaker threshold
            llm_circuit.failure_count += 1
            llm_circuit.last_failure_time = time.time()
            if llm_circuit.failure_count >= llm_circuit.failure_threshold:
                llm_circuit.state = "open"
                logger.warning("[CIRCUIT BREAKER] Opened after %d failures", llm_circuit.failure_count)
            logger.exception("[LLM] Streaming error: %s", exc)
            yield (
                "<speak>I'm currently offline, but the team is actively working to bring me "
                "back up. Thank you so much for your patience — I'll be with you very soon!</speak>"
            )
        finally:
            # Always close the streaming connection (httpx Response from send(stream=True)
            # does NOT support async-with; close it manually here instead)
            await response.aclose()

    async def get_completion(
        self,
        messages: list,
        max_tokens: int = 20,
        timeout: float = 0.4
    ) -> str:
        """
        Get a single non-streaming completion from the LLM with strict token limits and timeout.
        Used for the low-latency context-aware STT correction pass.
        """
        payload = {
            "model":          Config.LLM_MODEL_NAME,
            "messages":       messages,
            "stream":         False,
            "max_tokens":     max_tokens,
            "temperature":    0.0,  # greedy decoding = faster & consistent
            "top_p":          Config.LLM_TOP_P,
            "repeat_penalty": Config.LLM_REPEAT_PENALTY,
            "stop": ["<|im_end|>", "<|im_start|>", "<|endoftext|>"],
        }

        from llm.circuit_breaker import llm_circuit

        async def call_llama_server_non_stream():
            resp = await asyncio.wait_for(
                self.client.post(
                    "/v1/chat/completions",
                    json=payload,
                    timeout=httpx.Timeout(connect=2.0, read=timeout, write=2.0, pool=2.0)
                ),
                timeout=timeout
            )
            resp.raise_for_status()
            return resp.json()

        try:
            res_data = await llm_circuit.call(call_llama_server_non_stream)
            choices = res_data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return ""
        except Exception as exc:
            logger.warning("LLM non-streaming correction pass failed or timed out: %s", exc)
            return ""

    async def aclose(self) -> None:
        """Gracefully close the HTTP client on shutdown."""
        await self.client.aclose()


