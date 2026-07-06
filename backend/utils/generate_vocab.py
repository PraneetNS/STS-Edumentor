import argparse
import asyncio
import io
import json
import logging
import os
import sys
import numpy as np
import soundfile as sf

# Add parent folder of backend/utils to sys.path so we can import from backend root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config
from stt.whisper_engine import WhisperEngine
from tts.kokoro_engine import KokoroEngine
from agent.database import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("generate_vocab")

VOICES = ["af_heart", "af_bella", "am_adam", "bf_emma"]
SPEEDS = [0.85, 1.0, 1.3]


def inject_noise(audio: np.ndarray, snr_db: float) -> np.ndarray:
    """Inject additive white noise at a target Signal-to-Noise Ratio (SNR)."""
    audio_power = np.mean(audio ** 2)
    if audio_power == 0:
        return audio
    snr_ratio = 10 ** (snr_db / 10)
    noise_power = audio_power / snr_ratio
    noise = np.random.normal(0, np.sqrt(noise_power), len(audio))
    return audio + noise


async def run_synthetic_generation(vocab_path: str):
    logger.info("Starting synthetic self-supervised vocabulary generation...")

    # Load existing vocab
    if os.path.exists(vocab_path):
        with open(vocab_path, "r", encoding="utf-8") as f:
            vocab = json.load(f)
    else:
        logger.error("Vocab file not found at %s. Please ensure it exists.", vocab_path)
        return

    logger.info("Initializing Kokoro TTS and Whisper STT models (this may take a moment)...")
    try:
        kokoro = KokoroEngine()
        whisper = WhisperEngine()
    except Exception as e:
        logger.error("Failed to initialize ML models: %s", e)
        return

    try:
        import librosa
        librosa_available = True
    except ImportError:
        librosa_available = False
        logger.warning("librosa is not installed. Pitch shifting will be skipped.")

    new_variants_count = 0
    terms_processed = 0

    for discipline, terms_dict in vocab.items():
        logger.info("Processing discipline: %s", discipline)
        for term, current_variants in list(terms_dict.items()):
            terms_processed += 1
            logger.info("Generating variants for term: %r", term)

            candidate_variants = set()

            for voice in VOICES:
                for speed in SPEEDS:
                    try:
                        # 1. Clean synthesis
                        wav_bytes = kokoro.synthesize(term, speed=speed, voice=voice)
                        if not wav_bytes:
                            continue

                        data, sr = sf.read(io.BytesIO(wav_bytes))

                        # Resample to 16000
                        if sr != 16000:
                            if librosa_available:
                                data = librosa.resample(data.astype(np.float32), orig_sr=sr, target_sr=16000)
                            else:
                                num_samples = int(len(data) * 16000 / sr)
                                data = np.interp(
                                    np.linspace(0, len(data) - 1, num_samples),
                                    np.arange(len(data)),
                                    data
                                ).astype(np.float32)

                        # Test clean transcription
                        trans = whisper.transcribe(data)
                        if trans:
                            trans_clean = trans.lower().strip(".,!?")
                            if trans_clean != term.lower():
                                candidate_variants.add(trans_clean)

                        # 2. Add noise
                        for snr in [20, 10]:
                            noisy_data = inject_noise(data.copy(), snr)
                            trans_noisy = whisper.transcribe(noisy_data)
                            if trans_noisy:
                                trans_clean = trans_noisy.lower().strip(".,!?")
                                if trans_clean != term.lower():
                                    candidate_variants.add(trans_clean)

                        # 3. Add pitch shift (if librosa is available)
                        if librosa_available:
                            for shift in [-2.0, 2.0]:
                                try:
                                    shifted_data = librosa.effects.pitch_shift(
                                        data.astype(np.float32), sr=16000, n_steps=shift
                                    )
                                    trans_shifted = whisper.transcribe(shifted_data)
                                    if trans_shifted:
                                        trans_clean = trans_shifted.lower().strip(".,!?")
                                        if trans_clean != term.lower():
                                            candidate_variants.add(trans_clean)
                                except Exception:
                                    pass

                    except Exception as e:
                        logger.warning("Error generating audio for %r (%s/%s): %s", term, voice, speed, e)

            # Filtering and merging candidate variants
            added_for_term = []
            for v in candidate_variants:
                dist = edit_distance(term.lower(), v)
                if dist <= len(term) * 0.6 and v not in current_variants:
                    current_variants.append(v)
                    added_for_term.append(v)
                    new_variants_count += 1

            if added_for_term:
                logger.info("Found new variants for %r: %s", term, added_for_term)

    # Save back
    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump(vocab, f, indent=2, ensure_ascii=False)

    logger.info("Synthetic generation completed! Processed %d terms, added %d new variants.",
                terms_processed, new_variants_count)


def edit_distance(s1: str, s2: str) -> int:
    """Standard Levenshtein distance."""
    if len(s1) < len(s2):
        return edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


async def run_session_feedback(vocab_path: str):
    logger.info("Starting real session feedback database extraction...")

    # Load existing vocab
    if os.path.exists(vocab_path):
        with open(vocab_path, "r", encoding="utf-8") as f:
            vocab = json.load(f)
    else:
        logger.error("Vocab file not found at %s. Ensure it exists.", vocab_path)
        return

    # Connect to PostgreSQL
    db = DatabaseManager()
    await db.initialize()
    if not db.enabled or not db.pool:
        logger.error("PostgreSQL is not enabled or not connected. Feedback loop skipped.")
        return

    query = """
        SELECT raw_text, corrected_text
        FROM speech_corrections
        WHERE source = 'session'
    """

    new_variants_count = 0
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query)
            logger.info("Fetched %d speech corrections from database.", len(rows))

            for r in rows:
                raw = r["raw_text"].lower().strip(".,!?")
                corrected = r["corrected_text"].lower().strip(".,!?")

                if not raw or not corrected or raw == corrected:
                    continue

                for discipline, terms_dict in vocab.items():
                    for term in terms_dict.keys():
                        if term.lower() == corrected:
                            if raw not in terms_dict[term]:
                                terms_dict[term].append(raw)
                                logger.info("Adding database correction to [%s] %r -> %r",
                                            discipline, term, raw)
                                new_variants_count += 1
                                break
    except Exception as e:
        logger.error("Failed to query speech corrections from DB: %s", e)
    finally:
        await db.close()

    # Save back
    if new_variants_count > 0:
        with open(vocab_path, "w", encoding="utf-8") as f:
            json.dump(vocab, f, indent=2, ensure_ascii=False)
        logger.info("Session feedback loop completed! Added %d new variants from DB logs.", new_variants_count)
    else:
        logger.info("Session feedback loop completed. No new variants added.")


async def main():
    parser = argparse.ArgumentParser(description="Bootstrap and personalize technical vocabulary variants.")
    parser.add_argument("--from-corrections", action="store_true", help="Extract raw-corrected variants from real PostgreSQL session data.")
    parser.add_argument("--vocab-path", default="../speech/data/engineering_vocab.json", help="Path to engineering_vocab.json.")
    args = parser.parse_args()

    vocab_path = os.path.abspath(args.vocab_path)

    if args.from_corrections:
        await run_session_feedback(vocab_path)
    else:
        await run_synthetic_generation(vocab_path)


if __name__ == "__main__":
    asyncio.run(main())
