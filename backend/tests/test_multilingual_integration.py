"""
EduMentor Voice — Multilingual End-to-End Integration Test

Runs one full turn per language (English, Hindi, Kannada, Marathi, Hinglish
code-mix) through the complete pipeline:

  multilingual STT → Language Router → NLLB translation bridge (if needed)
  → LLM stub → back-translation → TTS router (Kokoro / MMS-TTS)

Measures wall-clock latency per stage and produces a detailed latency report.
The LLM is *stubbed* so no live LLM server is required.

Usage:
    cd backend
    python -m pytest tests/test_multilingual_integration.py -v -s
    # or run directly:
    .venv310\\Scripts\\python tests/test_multilingual_integration.py
"""

import asyncio
import io
import json
import os
import sys
import time
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ─────────────────────────────────────────────────────────────────────────────
# Helpers — TTS audio generation for test input clips
# ─────────────────────────────────────────────────────────────────────────────

AUDIO_CACHE: Dict[str, np.ndarray] = {}


def _generate_tts_audio(text: str, lang: str, cache_key: str) -> np.ndarray:
    """Use gTTS / Google Translate TTS to generate a 16 kHz numpy audio array."""
    import urllib.parse
    import urllib.request
    import librosa

    cache_file = f"scratch/integ_test_{cache_key}.mp3"
    os.makedirs("scratch", exist_ok=True)

    if not os.path.exists(cache_file):
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
        }
        q = urllib.parse.quote(text)
        url = (
            f"http://translate.google.com/translate_tts?ie=UTF-8&total=1&idx=0"
            f"&textlen={len(text)}&client=tw-ob&q={q}&tl={lang}"
        )
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            with open(cache_file, "wb") as f:
                f.write(resp.read())

    audio, _ = librosa.load(cache_file, sr=16000)
    return audio


def _audio_to_int16_pcm(audio: np.ndarray) -> bytes:
    """Convert float32 numpy array to int16 bytes (raw PCM)."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    return pcm.tobytes()


# ─────────────────────────────────────────────────────────────────────────────
# Test cases definition
# ─────────────────────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "name": "English",
        "text": "What is recursion in programming?",
        "gtts_lang": "en",
        "expected_route": "hindi",   # Latin fallback → hindi path (English stays in Kokoro)
        "expected_tts_engine": "kokoro",
    },
    {
        "name": "Hindi",
        "text": "रिकर्सन क्या होता है और इसका उपयोग कहाँ किया जाता है?",
        "gtts_lang": "hi",
        "expected_route": "hindi",
        "expected_tts_engine": "mms",
    },
    {
        "name": "Kannada",
        "text": "ರಿಕರ್ಷನ್ ಎಂದರೆ ಏನು? ಒಂದು ಉದಾಹರಣೆ ಕೊಡಿ.",
        "gtts_lang": "kn",
        "expected_route": "kannada",
        "expected_tts_engine": "mms",
    },
    {
        "name": "Marathi",
        "text": "रिकर्सन म्हणजे काय आणि ते कसे काम करते?",
        "gtts_lang": "mr",
        "expected_route": "marathi",
        "expected_tts_engine": "mms",
    },
    {
        "name": "Hinglish (code-mixed)",
        "text": "Recursion kya hai aur Python mein kaise use karte hain?",
        "gtts_lang": "hi",
        "expected_route": "hindi",
        "expected_tts_engine": "mms",
    },
]

# Stub LLM response (avoids needing a live LLM server)
STUB_LLM_RESPONSE = (
    "Recursion is when a function calls itself to solve a smaller version "
    "of the same problem, with a base case to stop the recursion."
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_mock_agent_controller():
    """Create an async mock agent controller that yields the stub LLM response."""
    async def _stream(*args, **kwargs):
        for word in STUB_LLM_RESPONSE.split():
            yield {"raw": word + " ", "planned": word + " "}

    ctrl = MagicMock()
    ctrl.stream = _stream
    return ctrl


def _make_mock_llm_engine():
    async def _stream_tokens(*args, **kwargs):
        for word in STUB_LLM_RESPONSE.split():
            yield {"raw": word + " ", "planned": word + " "}
    engine = MagicMock()
    engine.stream_tokens = _stream_tokens
    return engine


# ─────────────────────────────────────────────────────────────────────────────
# Core runner
# ─────────────────────────────────────────────────────────────────────────────

async def run_one_turn(
    case: Dict[str, Any],
    whisper_engine,
    translator,
    mms_engine,
) -> Dict[str, Any]:
    """Run one full pipeline turn and collect per-stage latencies."""
    print(f"\n{'='*60}")
    print(f"  TEST CASE: {case['name']}")
    print(f"{'='*60}")

    # Build audio input
    t_audio = time.time()
    audio = _generate_tts_audio(case["text"], case["gtts_lang"], f"{case['name'].replace(' ', '_').lower()}")
    raw_pcm = _audio_to_int16_pcm(audio)
    print(f"  [audio] Generated in {time.time()-t_audio:.2f}s | {len(audio)} samples")

    timings: Dict[str, float] = {}
    report: Dict[str, Any] = {
        "case": case["name"],
        "input_text": case["text"],
        "timings": timings,
    }

    # Stage 1: STT
    t_stt = time.time()
    segments, info = whisper_engine.model.transcribe(
        audio,
        task="transcribe",
        vad_filter=False,
        beam_size=1,
        best_of=1,
        temperature=0.0,
        condition_on_previous_text=False,
    )
    transcript = " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
    timings["stt"] = round(time.time() - t_stt, 3)
    report["transcript"] = transcript
    report["whisper_lang"] = info.language
    print(f"  [STT]     {timings['stt']:.2f}s | transcript={transcript!r:.80} | lang={info.language}")

    # Stage 2: Language Router
    from speech.language_router import LanguageRouter
    t_route = time.time()
    route_lang, route_meta = LanguageRouter.route(transcript)
    timings["router"] = round(time.time() - t_route, 4)
    report["route_lang"] = route_lang
    print(f"  [Router]  {timings['router']*1000:.1f}ms | route={route_lang} | {route_meta.get('reason','')[:70]}")

    # Stage 3a: Input translation
    llm_input = transcript
    if route_lang in ("kannada", "marathi"):
        NLLB_LANG_MAP = {"kannada": "kan_Knda", "marathi": "mar_Deva", "hindi": "hin_Deva"}
        src_code = NLLB_LANG_MAP[route_lang]
        t_tin = time.time()
        en_input, _ = translator.translate(transcript, src_code, "eng_Latn")
        timings["translate_in"] = round(time.time() - t_tin, 3)
        report["translated_to_en"] = en_input
        llm_input = en_input
        print(f"  [Trans→EN] {timings['translate_in']:.2f}s | {en_input!r:.80}")

    # Stage 4: LLM (stub)
    t_llm = time.time()
    llm_response = STUB_LLM_RESPONSE
    timings["llm"] = round(time.time() - t_llm, 3)
    report["llm_english_response"] = llm_response
    print(f"  [LLM]     {timings['llm']:.3f}s (stubbed) | {llm_response[:60]}")

    # Stage 5: Back-translation
    tts_text = llm_response
    if route_lang in ("kannada", "marathi"):
        NLLB_LANG_MAP = {"kannada": "kan_Knda", "marathi": "mar_Deva"}
        tgt_code = NLLB_LANG_MAP[route_lang]
        t_tout = time.time()
        back_translated, _ = translator.translate(llm_response, "eng_Latn", tgt_code)
        timings["translate_out"] = round(time.time() - t_tout, 3)
        report["translated_from_en"] = back_translated
        tts_text = back_translated
        print(f"  [Trans←EN] {timings['translate_out']:.2f}s | {back_translated!r:.80}")
    elif route_lang == "hindi":
        NLLB_LANG_MAP = {"hindi": "hin_Deva"}
        t_tout = time.time()
        back_translated, _ = translator.translate(llm_response, "eng_Latn", "hin_Deva")
        timings["translate_out"] = round(time.time() - t_tout, 3)
        report["translated_from_en"] = back_translated
        tts_text = back_translated
        print(f"  [Trans←EN] {timings['translate_out']:.2f}s | {back_translated!r:.80}")

    # Stage 6: TTS routing
    MMS_LANG_MAP = {"hindi": "hin", "kannada": "kan", "marathi": "mar"}
    if route_lang in MMS_LANG_MAP:
        mms_lang = MMS_LANG_MAP[route_lang]
        t_tts = time.time()
        wav_bytes = mms_engine.synthesize(tts_text, mms_lang)
        timings["tts"] = round(time.time() - t_tts, 3)
        report["tts_engine"] = "mms"
        report["tts_wav_size_bytes"] = len(wav_bytes)
        print(f"  [TTS/MMS] {timings['tts']:.2f}s | {len(wav_bytes)} bytes WAV ({mms_lang})")
    else:
        # English → Kokoro (just time text prep, no actual Kokoro call in test)
        t_tts = time.time()
        timings["tts"] = round(time.time() - t_tts, 4)
        report["tts_engine"] = "kokoro"
        report["tts_wav_size_bytes"] = 0  # Would be generated by Kokoro in live system
        print(f"  [TTS/Kokoro] (English path — Kokoro handles in live system)")

    timings["total"] = round(sum(
        v for k, v in timings.items() if k != "total"
    ), 3)
    print(f"\n  ✓ TOTAL pipeline latency: {timings['total']:.2f}s")
    print(f"  Timings: {timings}")

    return report


def run_integration_test() -> None:
    """Load models once, then run all test cases synchronously."""
    print("\n" + "="*60)
    print("  EduMentor Multilingual Pipeline Integration Test")
    print("="*60)

    # --- Load shared model singletons ---
    print("\n[Setup] Loading WhisperEngine (small, int8 CPU)...")
    from stt.whisper_engine import WhisperEngine
    whisper_engine = WhisperEngine()

    print("[Setup] Loading NLLB CTranslate2 Translator...")
    from speech.nllb_translator import NLLBTranslator
    translator = NLLBTranslator()

    print("[Setup] Loading MMS-TTS Engine...")
    from speech.mms_tts import MMSTTSEngine
    mms_engine = MMSTTSEngine()

    print("\n[Setup] All models loaded. Starting test cases...\n")

    all_reports = []
    for case in TEST_CASES:
        report = asyncio.get_event_loop().run_until_complete(
            run_one_turn(case, whisper_engine, translator, mms_engine)
        )
        all_reports.append(report)

    # --- Print final latency summary table ---
    print("\n" + "="*60)
    print("  LATENCY SUMMARY PER LANGUAGE PATH")
    print("="*60)
    header = f"{'Case':<22} {'STT':>6} {'Router':>8} {'Trans→EN':>10} {'LLM':>6} {'Trans←EN':>10} {'TTS':>7} {'TOTAL':>8}"
    print(header)
    print("-" * len(header))

    for r in all_reports:
        t = r.get("timings", {})
        row = (
            f"{r['case']:<22} "
            f"{t.get('stt', 0):>6.2f} "
            f"{t.get('router', 0)*1000:>7.0f}ms "
            f"{t.get('translate_in', '-'):>10} "
            f"{t.get('llm', 0):>6.3f} "
            f"{t.get('translate_out', '-'):>10} "
            f"{t.get('tts', 0):>7.2f} "
            f"{t.get('total', 0):>8.2f}s"
        )
        print(row)

    print("\n[Notes]")
    print("  LLM latency is stubbed. In live system add ~2-8s depending on response length.")
    print("  TTS/Kokoro latency not shown (English path) — add ~0.5-2s per sentence chunk.")
    print("  STT uses Whisper 'small' (int8 CPU) with no forced language.")

    # Save JSON report
    out_path = "scratch/multilingual_integration_report.json"
    os.makedirs("scratch", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_reports, f, ensure_ascii=False, indent=2)
    print(f"\n  Full report saved: {out_path}")
    print("="*60)


# ─────────────────────────────────────────────────────────────────────────────
# pytest entry points
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def shared_engines():
    """Load all models once per test module to avoid redundant downloads."""
    from stt.whisper_engine import WhisperEngine
    from speech.nllb_translator import NLLBTranslator
    from speech.mms_tts import MMSTTSEngine

    return {
        "whisper": WhisperEngine(),
        "translator": NLLBTranslator(),
        "mms": MMSTTSEngine(),
    }


@pytest.mark.parametrize("case", TEST_CASES, ids=[c["name"] for c in TEST_CASES])
def test_multilingual_turn(case, shared_engines):
    """Integration test: one full turn per language path."""
    report = asyncio.get_event_loop().run_until_complete(
        run_one_turn(
            case,
            shared_engines["whisper"],
            shared_engines["translator"],
            shared_engines["mms"],
        )
    )

    # Assertions: pipeline must complete and produce non-empty output
    assert report.get("transcript") is not None, "STT should produce a transcript"
    assert report.get("route_lang") in ("hindi", "kannada", "marathi", "english"), \
        f"Unexpected route: {report.get('route_lang')}"
    assert report.get("tts_engine") in ("kokoro", "mms"), "TTS engine must be set"
    assert report["timings"].get("total", 0) < 120, "Total turn must complete under 120s"

    # Indic routes must produce translated output
    if report["route_lang"] in ("kannada", "marathi", "hindi"):
        assert report.get("translated_from_en"), \
            f"Back-translation required for {report['route_lang']} route"

    print(f"\n  [{case['name']}] PASS | Total latency: {report['timings'].get('total', '?')}s")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    run_integration_test()
