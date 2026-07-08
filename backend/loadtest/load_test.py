from __future__ import annotations

import argparse
import asyncio
import csv
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, List, Optional

import redis.asyncio as redis

from request_queue.llm_queue import (
    LLMRequestQueue,
    LLMWorker,
    QueueConfig,
    QueueFullError,
)

@dataclass
class MockGenerationProfile:
    ttft_mean_s: float = 0.30     # mimics prefill + first-token latency
    ttft_std_s: float = 0.08
    token_interval_mean_s: float = 0.03   # ~33 tok/s decode pace
    token_interval_std_s: float = 0.01
    min_tokens: int = 20
    max_tokens: int = 150
    failure_rate: float = 0.0     # fraction of generations that raise

def make_mock_generate_fn(profile: MockGenerationProfile):
    async def generate(prompt: str) -> AsyncIterator[str]:
        if random.random() < profile.failure_rate:
            raise RuntimeError("simulated generation failure")

        ttft = max(0.02, random.gauss(profile.ttft_mean_s, profile.ttft_std_s))
        await asyncio.sleep(ttft)

        n_tokens = random.randint(profile.min_tokens, profile.max_tokens)
        for i in range(n_tokens):
            yield f"tok_{i}"
            if i < n_tokens - 1:
                gap = max(0.005, random.gauss(
                    profile.token_interval_mean_s, profile.token_interval_std_s
                ))
                await asyncio.sleep(gap)

    return generate
