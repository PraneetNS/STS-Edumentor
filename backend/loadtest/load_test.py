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
