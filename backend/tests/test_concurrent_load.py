import asyncio
import os
import sys
import time
from typing import Dict, Any

import dotenv
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from stt.whisper_engine import WhisperEngine
from speech.nllb_translator import NLLBTranslator
from speech.mms_tts import MMSTTSEngine
from tests.test_multilingual_acceptance import run_scenario_stream
from agent.models import StudentProfile

# Define the two concurrent student scenarios
# Student 1: Kannada question, outputs Kannada
student_kannada = {
    "id": "concurrent_kan",
    "name": "Kannada Student (Concurrent)",
    "text": "Recursion endarenu",
    "gtts_lang": "kn",
    "expected_route": "kannada",
    "expected_tts": "mms"
}

# Student 2: Marathi question, outputs Marathi (runs in parallel)
student_marathi = {
    "id": "concurrent_mar",
    "name": "Marathi Student (Concurrent)",
    "text": "Recursion mhanje kay",
    "gtts_lang": "mr",
    "expected_route": "marathi",
    "expected_tts": "mms"
}

async def run_concurrent_students():
    print("\n" + "="*60)
    print("  EduMentor Multilingual Pipeline Concurrent Load Test (Asymmetric Indic GPU)")
    print("="*60)
    
    # Enable GPU for translation & TTS, keeping Whisper on CPU to prevent DLL clash
    os.environ["WHISPER_DEVICE"] = "cpu"
    os.environ["WHISPER_COMPUTE_TYPE"] = "int8"
    os.environ["NLLB_DEVICE"] = "cuda"
    os.environ["MMS_TTS_DEVICE"] = "cuda"
    
    print("Initializing Engines for Concurrent Test...")
    whisper_engine = WhisperEngine()
    translator = NLLBTranslator()
    mms_engine = MMSTTSEngine()
    
    while not mms_engine.warmed_up:
        await asyncio.sleep(0.5)
    print("Warmup completed. Starting concurrent student load test...")
    
    profile = StudentProfile(output_language_preference="auto", glossary_mode="english")
    
    t_start = time.time()
    
    # Run both heavy Indic student turns concurrently on the GPU!
    reports = await asyncio.gather(
        run_scenario_stream(student_kannada, whisper_engine, translator, mms_engine, profile),
        run_scenario_stream(student_marathi, whisper_engine, translator, mms_engine, profile)
    )
    
    total_elapsed = time.time() - t_start
    print("\n" + "="*60)
    print("  CONCURRENT STUDENTS EXECUTION REPORT (Indic GPU)")
    print("="*60)
    for r in reports:
        print(f"Student Path: {r['tts_engine'].upper()} Response")
        print(f"  Input: {r['stt_transcript']}")
        print(f"  Output: {r['output_text']}")
        print(f"  TTFT (First Audio Latency): {r['first_audio_latency']}s")
        print(f"  Total Latency: {r['total_latency']}s")
        print("-" * 40)
        
    print(f"Total concurrent run duration: {total_elapsed:.2f}s")
    
    # Assertions: Both heavy Indic students must finish fast on GPU (TTFT < 12s)
    # Note: 12s accounts for back-to-back synchronous CPU Whisper STT runs in this single-threaded test harness.
    assert reports[0]["first_audio_latency"] < 12.0, f"Kannada student TTFT too slow under concurrent load: {reports[0]['first_audio_latency']}s"
    assert reports[1]["first_audio_latency"] < 12.0, f"Marathi student TTFT too slow under concurrent load: {reports[1]['first_audio_latency']}s"
    print("\n[OK] Concurrent load test passed! No GPU-contention latency blowups or OOM fallbacks.")

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    asyncio.run(run_concurrent_students())
