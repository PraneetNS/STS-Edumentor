# -*- coding: utf-8 -*-
"""
EduMentor Voice - Multilingual Pipeline Timing Benchmark
=========================================================
Measures REAL latencies for:
  1. Language Router  (script + lexical detection)
  2. NLLB Translate -> English  (per language)
  3. NLLB Translate <- English  (per language)
  4. Round-trip translation (to EN and back)

No mocked models -- hits the actual loaded NLLB singleton.
"""

import time
import sys
import os

import pytest

# Force UTF-8 output so Indic characters don't crash on Windows cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Make sure the backend package root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def safe(text, max_len=50):
    """Safely encode text for printing -- replaces unencodable chars."""
    return text[:max_len].encode("ascii", errors="replace").decode("ascii")


# -- Test sentences per language -----------------------------------------------
SENTENCES = {
    "Hindi": {
        "text": "\u092e\u0941\u091d\u0947 Python \u0915\u0947 \u092c\u093e\u0930\u0947 \u092e\u0947\u0902 \u092c\u0924\u093e\u0093",
        "nllb_src": "hin_Deva",
        "route_expects": "hindi",
    },
    "Kannada": {
        "text": "\u0ca8\u0ca8\u0c97\u0cc6 recursion \u0cac\u0c97\u0ccd\u0c97\u0cc6 \u0cb5\u0cbf\u0cb5\u0cb0\u0cbf\u0cb8\u0cbf",
        "nllb_src": "kan_Knda",
        "route_expects": "kannada",
    },
    "Marathi": {
        "text": "\u092e\u0932\u093e dynamic programming \u0938\u092e\u091c\u093e\u0935\u0942\u0928 \u0938\u093e\u0902\u0917\u093e",
        "nllb_src": "mar_Deva",
        "route_expects": "marathi",
    },
    "English": {
        "text": "Explain how neural networks work",
        "nllb_src": "eng_Latn",
        "route_expects": "english",
    },
    "Hinglish (code-mixed)": {
        "text": "Mujhe GPU aur CPU ka difference samjhao",
        "nllb_src": "hin_Deva",
        "route_expects": "hinglish",
    },
}

# Short LLM-style English response to benchmark back-translation
ENGLISH_RESPONSE = (
    "Recursion is a technique where a function calls itself to solve smaller "
    "sub-problems. It requires a base case to stop the recursion."
)

NLLB_TARGETS = {
    "Hindi":   "hin_Deva",
    "Kannada": "kan_Knda",
    "Marathi": "mar_Deva",
}


# -- Fixtures ------------------------------------------------------------------

@pytest.fixture(scope="module")
def router():
    from speech.language_router import LanguageRouter
    return LanguageRouter()


@pytest.fixture(scope="module")
def translator():
    from speech.nllb_translator import get_translator
    return get_translator()


# -- Router timing tests -------------------------------------------------------

@pytest.mark.parametrize("lang_name,info", list(SENTENCES.items()))
def test_router_latency(router, lang_name, info):
    """Measure how fast the language router classifies each language."""
    text = info["text"]

    t0 = time.perf_counter()
    route_lang, meta = router.route(text, whisper_detected_lang=None)
    elapsed = time.perf_counter() - t0

    print(
        f"\n[ROUTER] {lang_name:<28} -> {route_lang:<12} "
        f"| reason={meta.get('reason','?'):<20} "
        f"| latency={elapsed*1000:.2f} ms"
    )

    assert elapsed < 1.0, f"Router too slow for {lang_name}: {elapsed:.3f}s"


# -- NLLB translate-to-English tests ------------------------------------------

@pytest.mark.parametrize("lang_name,info", [
    (k, v) for k, v in SENTENCES.items()
    if k in ("Hindi", "Kannada", "Marathi")
])
def test_translate_to_english_latency(translator, lang_name, info):
    """Measure NLLB translation latency from Indic -> English."""
    text = info["text"]
    src_code = info["nllb_src"]

    translated, latency = translator.translate(text, src_code, "eng_Latn")

    print(
        f"\n[TRANSLATE -> EN] {lang_name:<12} "
        f"| input={repr(safe(text)):<42} "
        f"-> output={repr(safe(translated)):<42} "
        f"| latency={latency:.3f}s"
    )

    assert translated, f"Got empty translation for {lang_name}"
    assert latency < 10.0, f"Translation too slow for {lang_name}: {latency:.3f}s"


# -- NLLB translate-from-English tests ----------------------------------------

@pytest.mark.parametrize("lang_name,tgt_code", list(NLLB_TARGETS.items()))
def test_translate_from_english_latency(translator, lang_name, tgt_code):
    """Measure NLLB translation latency from English -> Indic."""
    translated, latency = translator.translate(ENGLISH_RESPONSE, "eng_Latn", tgt_code)

    print(
        f"\n[TRANSLATE <- EN] {lang_name:<12} "
        f"| output={repr(safe(translated)):<52} "
        f"| latency={latency:.3f}s"
    )

    assert translated, f"Got empty back-translation for {lang_name}"
    assert latency < 10.0, f"Back-translation too slow for {lang_name}: {latency:.3f}s"


# -- Round-trip timing ---------------------------------------------------------

@pytest.mark.parametrize("lang_name,info", [
    (k, v) for k, v in SENTENCES.items()
    if k in ("Hindi", "Kannada", "Marathi")
])
def test_round_trip_latency(translator, lang_name, info):
    """
    Full translation round-trip:
      Indic input -> English -> (simulated LLM response) -> back to Indic
    Reports total translation overhead added by the multilingual pipeline.
    """
    src_code = info["nllb_src"]
    tgt_code = NLLB_TARGETS[lang_name]
    text = info["text"]

    t_total = time.perf_counter()

    # Step 1: Indic -> English
    en_text, lat_in = translator.translate(text, src_code, "eng_Latn")

    # Step 2: Simulated LLM (fixed English response)
    en_response = ENGLISH_RESPONSE

    # Step 3: English -> Indic
    back_text, lat_out = translator.translate(en_response, "eng_Latn", tgt_code)

    total = time.perf_counter() - t_total

    print(
        f"\n[ROUND-TRIP] {lang_name}"
        f"\n  Translate IN  (Indic -> EN):  {lat_in:.3f}s"
        f"\n  Translate OUT (EN -> Indic):  {lat_out:.3f}s"
        f"\n  Total translation overhead:   {total:.3f}s"
        f"\n  Input  : {repr(safe(text))}"
        f"\n  EN     : {repr(safe(en_text))}"
        f"\n  Output : {repr(safe(back_text))}"
    )

    assert total < 20.0, f"Round-trip too slow for {lang_name}: {total:.3f}s"
