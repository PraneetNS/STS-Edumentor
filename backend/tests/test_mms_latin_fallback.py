import asyncio
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from speech.mms_tts import MMSTTSEngine
from i18n.term_glossary import transliterate_latin_words, normalize_lang


def has_native_script_characters(text: str, response_lang: str) -> bool:
    norm_lang = normalize_lang(response_lang)
    if norm_lang in ("hindi", "marathi"):
        return any('\u0900' <= char <= '\u097f' for char in text)
    elif norm_lang == "kannada":
        return any('\u0c80' <= char <= '\u0cff' for char in text)
    return True


@pytest.mark.asyncio
async def test_pure_latin_chunk_merging_and_fallback():
    """
    Asserts that feeding a sequence of chunks containing a pure-Latin chunk
    does not raise exceptions, and successfully yields audio for all components.
    """
    engine = MMSTTSEngine()
    
    # Wait for engine warmup (warmup runs in a background thread)
    t_start = asyncio.get_event_loop().time()
    while not engine.warmed_up and asyncio.get_event_loop().time() - t_start < 25:
        await asyncio.sleep(0.5)

    # Scenarios for Hindi and Kannada verifying leading, trailing, and standalone
    # pure-Latin chunks (representing glossary-restored English technical terms).
    test_cases = [
        {
            "lang": "hindi",
            "mms_lang": "hin",
            "chunks": ["Recursion", "यह एक प्रोग्रामिंग तकनीक है।"],
            "expected_count": 1,  # Merged into 1 chunk: "Recursion यह एक प्रोग्रामिंग तकनीक है।"
        },
        {
            "lang": "kannada",
            "mms_lang": "kan",
            "chunks": ["Encapsulation", "ಒಂದು ಪ್ರೋಗ್ರಾಮಿಂಗ್ ಪರಿಕಲ್ಪನೆ."],
            "expected_count": 1,
        },
        {
            "lang": "hindi",
            "mms_lang": "hin",
            "chunks": ["यह एक उदाहरण है।", "Recursion", "जो एक फ़ंक्शन है।"],
            "expected_count": 2,  # "यह एक उदाहरण है।" (synthesized) + "Recursion" (buffered) merged into "Recursion जो एक फ़ंक्शन है।"
        },
        {
            "lang": "hindi",
            "mms_lang": "hin",
            "chunks": ["Recursion"],
            "expected_count": 1,  # Standalone chunk gets force-transliterated to "रिकर्शन"
        }
    ]

    for case in test_cases:
        tts_queue = asyncio.Queue()
        audio_queue = asyncio.Queue()

        # Enqueue chunks
        for c in case["chunks"]:
            await tts_queue.put(c)
        await tts_queue.put(None)  # Sentinel

        # Run simulated tts_worker identical to main.py
        sentence_buffer = ""
        tts_idx = 0
        wavs_produced = []

        async def simulate_synthesize_and_enqueue(text: str):
            nonlocal tts_idx
            # Check VITS synthesizer directly
            wav_bytes = engine.synthesize(text, case["mms_lang"])
            # Even if it contains Latin terms, it must NOT crash
            assert isinstance(wav_bytes, bytes)
            # The synthesized text contains native characters, so wav_bytes should not be empty
            assert len(wav_bytes) > 0
            wavs_produced.append(wav_bytes)
            await audio_queue.put(wav_bytes)
            tts_idx += 1

        while True:
            sentence = await tts_queue.get()
            if sentence is None:
                if sentence_buffer.strip():
                    final_sentence = sentence_buffer.strip()
                    if not has_native_script_characters(final_sentence, case["lang"]):
                        final_sentence = transliterate_latin_words(final_sentence, case["lang"])
                    await simulate_synthesize_and_enqueue(final_sentence)
                break

            if not has_native_script_characters(sentence, case["lang"]):
                sentence_buffer = (sentence_buffer + " " + sentence).strip()
                tts_queue.task_done()
                continue

            if sentence_buffer:
                sentence = (sentence_buffer + " " + sentence).strip()
                sentence_buffer = ""

            await simulate_synthesize_and_enqueue(sentence)
            tts_queue.task_done()

        # Assert that all chunks (merged or transliterated) produced audio
        assert len(wavs_produced) == case["expected_count"]
        # Empty the audio queue
        while not audio_queue.empty():
            await audio_queue.get()
            audio_queue.task_done()

    # End of test suite: successfully verified that pure-Latin chunks
    # are gracefully processed and do not interrupt subsequent native chunks.
