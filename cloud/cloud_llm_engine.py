"""
cloud_llm_engine.py — ZeroGPU-backed LLM inference engine for EduMentor Cloud.

Uses Hugging Face Transformers with the @spaces.GPU decorator so inference
runs on a GPU slice allocated dynamically by the ZeroGPU runtime.

Configuration (env vars):
  CLOUD_MODEL_ID    HF model repo to load  (default: Qwen/Qwen2.5-1.5B-Instruct)
  CLOUD_MAX_TOKENS  Default token budget    (default: 250)
"""

import asyncio
import os
from typing import AsyncIterator, Optional

import spaces
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM


MODEL_ID   = os.getenv("CLOUD_MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
_MAX_TOKENS = int(os.getenv("CLOUD_MAX_TOKENS", "250"))


@spaces.GPU(duration=120)
def _generate_sync(
    messages: list,
    max_tokens: int,
) -> str:

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float16,
        device_map="cuda",
    )

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
    ).to("cuda")

    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=0.6,
            top_p=0.9,
            do_sample=True,
        )

    generated = outputs[0][inputs.input_ids.shape[1]:]

    response = tokenizer.decode(
        generated,
        skip_special_tokens=True,
    )

    del outputs
    del inputs
    del model
    del tokenizer

    torch.cuda.empty_cache()

    return response


class CloudLLMEngine:

    def __init__(self):
        self.last_usage = None

    async def stream_tokens(
        self,
        user_text: str,
    ) -> AsyncIterator[str]:

        messages = [
            {
                "role": "system",
                "content": (
                    "You are Edi, an AI engineering mentor."
                ),
            },
            {
                "role": "user",
                "content": user_text,
            },
        ]

        async for token in self.stream_tokens_from_messages(messages):
            yield token

    async def stream_tokens_from_messages(
        self,
        messages: list,
        session_id: str = "",
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:

        response = await asyncio.to_thread(
            _generate_sync,
            messages,
            max_tokens or _MAX_TOKENS,
        )

        # Compatibility streaming.
        #
        # ZeroGPU generation completes before this adapter receives
        # the result. We emit small text chunks afterward so the
        # existing AgentController can consume an AsyncIterator.

        chunk_size = 12

        for index in range(0, len(response), chunk_size):
            yield response[index:index + chunk_size]
            await asyncio.sleep(0)

    async def aclose(self):
        return