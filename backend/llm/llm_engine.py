"""
EduMentor Voice — LLM Streaming Engine

Communicates with a local llama.cpp server via its OpenAI-compatible
streaming API. Tokens are yielded one-by-one as they are generated —
no waiting for the full response.

Prompt Caching / KV Cache Notes
────────────────────────────────
llama-server implements KV cache reuse via prefix matching. When the
token prefix of a new request matches a previously cached prefix in a
slot, the server skips re-computing those tokens (prefill shortcut).

For caching to engage reliably across turns:
  1. The prompt must start with identical tokens every time (stable
     static system prompt — see PromptBuilder).
  2. With a single slot (-np 1) all sessions share the same KV cache.
     This is fine for a single-user dev setup: the system prompt prefix
     is cached after the first turn and reused every subsequent turn.
     If you need true multi-user concurrency, increase -np and NUM_SLOTS
     to match (e.g. -np 2 / NUM_SLOTS = 2).
"""

import asyncio
import hashlib
import json
import logging
from typing import AsyncIterator, Optional

import httpx

from config import Config

logger = logging.getLogger("edumentor.agent.llm")

# Slot affinity — must match the -np value on llama-server (run_llm_server.bat).
# With -np 1 (single slot) this is always 0. Increase to match -np if you
# scale up to multiple parallel sessions.
NUM_SLOTS: int = 1


def get_slot_for_session(session_id: str, num_slots: int = NUM_SLOTS) -> int:
    """Deterministic hash-based slot assignment.

    The same session always lands on the same slot so its KV cache
    accumulates across turns instead of being scattered across slots.

    With NUM_SLOTS=1 (-np 1) this always returns 0. Increase NUM_SLOTS
    and -np together when scaling to multiple concurrent users.

    Args:
        session_id: Unique session identifier (WebSocket session ID).
        num_slots:  Must match the -np value on llama-server.

    Returns:
        Slot index in [0, num_slots).
    """
    if not session_id or num_slots <= 1:
        return 0
    return int(hashlib.md5(session_id.encode()).hexdigest(), 16) % num_slots


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

    def _merge_consecutive_messages(self, messages: list) -> list:
        """Merge consecutive messages of the same role (especially system prompts) 
        to prevent templates from ignoring earlier instructions.
        """
        if not messages:
            return []
        
        merged = []
        current = None
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            if current is None:
                current = {"role": role, "content": content}
            elif current["role"] == role:
                current["content"] += "\n\n" + content
            else:
                merged.append(current)
                current = {"role": role, "content": content}
                
        if current is not None:
            merged.append(current)
            
        return merged

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
        session_id: str = "",
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Stream tokens from the LLM using a pre-built messages list.

        This is the primary method used by AgentController, which constructs
        the full chat history, system prompt, and context via PromptBuilder.

        Parsing follows the OpenAI Server-Sent Events (SSE) format.

        Args:
            messages:   List of {"role": ..., "content": ...} dicts.
            session_id: WebSocket session ID used to derive a deterministic
                        slot index via get_slot_for_session(). Same session
                        always maps to the same slot so its KV cache prefix
                        accumulates across turns rather than being evicted
                        by interleaved requests from other sessions.
            max_tokens: Optional token generation limit override.

        Yields:
            Individual token strings.
        """
        self.last_usage = None
        slot_id = get_slot_for_session(session_id)
        # Ensure a system prompt is always present. Some callers may supply
        # only a user message (legacy paths). Prepend the configured
        # system prompt if no system role is found so the model always sees
        # the system instructions on every request.
        has_system = any((m.get("role") == "system") for m in messages)
        if not has_system:
            messages = [{"role": "system", "content": Config.LLM_SYSTEM_PROMPT}] + list(messages)

        merged_messages = self._merge_consecutive_messages(messages)
        payload = {
            "model":          Config.LLM_MODEL_NAME,
            "messages":       merged_messages,
            "stream":         True,
            "max_tokens":     max_tokens if max_tokens is not None else Config.LLM_MAX_TOKENS,
            "temperature":    Config.LLM_TEMPERATURE,
            "top_p":          Config.LLM_TOP_P,
            "repeat_penalty": Config.LLM_REPEAT_PENALTY,
            "cache_prompt":   True,
            "slot_id":        slot_id,
            "stop": ["<|im_end|>", "<|im_start|>", "<|endoftext|>"],
            "stream_options": {"include_usage": True},
        }

        logger.info(
            "LLM <- %d messages (merged to %d), first_user=%r",
            len(messages),
            len(merged_messages),
            next(
                (m["content"][:60] for m in merged_messages if m["role"] == "user"),
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

        except (httpx.ConnectError, httpx.RemoteProtocolError, ConnectionRefusedError) as exc:
            # LLM server dropped mid-stream (e.g. restarting). Don't trip circuit breaker.
            logger.warning("[LLM] Connection lost during streaming: %s", exc)
            yield (
                "<speak>I'm currently offline, but the team is actively working to bring me "
                "back up. Thank you so much for your patience — I'll be with you very soon!</speak>"
            )
        except Exception as exc:
            # Track unexpected stream reading failures toward circuit breaker threshold
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
        timeout: float = 0.4,
        session_id: str = "",
     ) -> str:
        """
        Get a single non-streaming completion from the LLM with strict token limits and timeout.
        Used for the low-latency context-aware STT correction pass.
        """
        slot_id = get_slot_for_session(session_id)
        # Same safety: ensure a system message exists for non-streaming calls.
        has_system = any((m.get("role") == "system") for m in messages)
        if not has_system:
            messages = [{"role": "system", "content": Config.LLM_SYSTEM_PROMPT}] + list(messages)

        merged_messages = self._merge_consecutive_messages(messages)
        payload = {
            "model":          Config.LLM_MODEL_NAME,
            "messages":       merged_messages,
            "stream":         False,
            "max_tokens":     max_tokens,
            "temperature":    0.0,  # greedy decoding = faster & consistent
            "top_p":          Config.LLM_TOP_P,
            "repeat_penalty": Config.LLM_REPEAT_PENALTY,
            "cache_prompt":   True,
            "slot_id":        slot_id,
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

