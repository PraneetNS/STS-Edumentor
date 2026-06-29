"""
EduMentor Voice -- Kokoro Text-to-Speech Engine

Wraps the Kokoro TTS pipeline for sentence-level synthesis.
The pipeline is loaded ONCE at startup -- Kokoro auto-downloads its
model weights from HuggingFace on the first run.
"""

import io
import logging
from typing import Optional

import numpy as np
import soundfile as sf
import torch

from config import Config

logger = logging.getLogger(__name__)


class KokoroEngine:
    """
    Kokoro TTS engine that synthesizes audio for a sentence at a time.

    Kokoro is initialised once and kept in memory. Synthesis is called
    from a thread-pool executor so it doesn't block the event loop.

    Usage:
        engine = KokoroEngine()                   # once at startup
        wav_bytes = engine.synthesize("Hello!")   # called per sentence
    """

    def __init__(self) -> None:
        # Silence noisy warnings from the phonemizer library
        logging.getLogger("phonemizer").setLevel(logging.ERROR)

        logger.info("Loading Kokoro TTS pipeline (lang='%s') ...", Config.KOKORO_LANG_CODE)
        try:
            from kokoro import KPipeline  # noqa: PLC0415

            # Detect device: use CUDA if available, otherwise CPU
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("Kokoro using device: %s", device)

            self.pipeline = KPipeline(
                lang_code=Config.KOKORO_LANG_CODE,
                device=device,
            )
            self.sample_rate = Config.KOKORO_SAMPLE_RATE
            self.greeting_cache = {}

            # warm up voice profiles in the background to avoid cold-start latencies later
            import threading
            def warmup_voices():
                logger.info("Warming up Kokoro voice profile in the background...")
                warmup_text = "Warm up."
                voice = Config.KOKORO_VOICE
                try:
                    # Call pipeline generator to load/cache the voice weights
                    list(self.pipeline(warmup_text, voice=voice, speed=1.0))
                    logger.info("Voice '%s' successfully warmed up.", voice)
                except Exception as e:
                    logger.warning("Failed to warm up voice '%s': %s", voice, e)
                logger.info("Kokoro voices warm up complete.")

            threading.Thread(target=warmup_voices, daemon=True).start()

            logger.info("[OK] Kokoro TTS engine ready (voice=%s).", Config.KOKORO_VOICE)
        except ImportError as exc:
            msg = (
                "Kokoro package is not installed or import failed. This usually means "
                "you are running in the wrong Python environment.\n"
                "To resolve this, activate the virtual environment and install dependencies:\n"
                "  cd backend\n"
                "  .venv310\\Scripts\\activate   # On Windows\n"
                "  source .venv310/bin/activate  # On Linux/macOS\n"
                "  pip install -r requirements.txt\n"
                "Or simply use the root launcher scripts: run_backend.bat or run_backend.sh"
            )
            logger.critical(msg)
            raise RuntimeError(msg) from exc

    def _preprocess_text(self, text: str) -> str:
        """
        Preprocesses text to improve Kokoro pronunciation of names, acronyms, and symbols.

        This map expands technical engineering abbreviations and formats the name 'Edi'
        for correct grapheme-to-phoneme translation inside the Kokoro model.
        """
        import re

        # Remove any lingering XML/HTML-style tags (safeguard against tag leakages)
        text = re.sub(r"</?[a-zA-Z]+(?:\s+[^>]*)?>", "", text)

        # Remove markdown characters that confuse the G2P phoneme engine
        text = re.sub(r"[*`_\[\]{}()#]", "", text)

        # Convert newlines in code-like content into spoken line breaks.
        # Each non-empty line becomes its own sentence so TTS reads them
        # one at a time instead of running everything together.
        # Detect multi-line content (2+ newlines or indented lines).
        if "\n" in text:
            lines = text.split("\n")
            spoken_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                # Add a period after lines that don't already end with punctuation
                # so the TTS engine treats each line as a complete spoken unit.
                if stripped and not re.search(r"[.!?,;:]$", stripped):
                    stripped += "."
                spoken_lines.append(stripped)
            text = "  ".join(spoken_lines)

        # Replace ellipses and dashes with commas/periods for natural pauses
        text = text.replace("...", ". ")
        text = text.replace("--", ", ")
        text = text.replace("—", ", ")

        # Ensure a space character always follows punctuation to help word boundaries
        text = re.sub(r"([.,!?;:])(?=[a-zA-Z])", r"\1 ", text)

        # Fix spelling/pronunciation of Edi
        text = re.sub(r"\bEdi\b", "Eddy", text)
        text = re.sub(r"\bedi\b", "eddy", text)

        # Expand engineering acronyms/abbreviations for natural pronunciation
        acronyms = {
            r"\bAI\b": "A I",
            r"\bcse\b": "C S E",
            r"\bCSE\b": "C S E",
            r"\bdsa\b": "D S A",
            r"\bDSA\b": "D S A",
            r"\boop\b": "O O P",
            r"\bOOP\b": "O O P",
            r"\bllm\b": "L L M",
            r"\bLLM\b": "L L M",
            r"\btts\b": "T T S",
            r"\bTTS\b": "T T S",
            r"\bstt\b": "S T T",
            r"\bSTT\b": "S T T",
            r"\bapi\b": "A P I",
            r"\bAPI\b": "A P I",
            r"\bcs\b": "C S",
            r"\bCS\b": "C S",
            r"\bIT\b": "I T",
            r"\bECE\b": "E C E",
            r"\bece\b": "E C E",
            r"\bEEE\b": "E E E",
            r"\beee\b": "E E E",
            r"\bCAD\b": "Cad",
            r"\bcad\b": "cad",
            r"\bDBMS\b": "D B M S",
            r"\bdbms\b": "d b m s",
            r"\bOS\b": "O S",
            r"\bos\b": "o s",
            r"\bSQL\b": "sequel",
            r"\bsql\b": "sequel",
            r"\bHTML\b": "H T M L",
            r"\bhtml\b": "h t m l",
            r"\bCSS\b": "C S S",
            r"\bcss\b": "c s s",
            r"\bJS\b": "J S",
            r"\bjs\b": "j s",
            r"\bJSON\b": "J S O N",
            r"\bjson\b": "J S O N",
            r"\bHTTP\b": "H T T P",
            r"\bhttp\b": "H T T P",
            r"\bTCP\b": "T C P",
            r"\btcp\b": "T C P",
            r"\bIP\b": "I P",
            r"\bRAM\b": "R A M",
            r"\bram\b": "R A M",
            r"\bCPU\b": "C P U",
            r"\bcpu\b": "C P U",
        }

        for pattern, replacement in acronyms.items():
            text = re.sub(pattern, replacement, text)

        # Replace common symbols
        text = text.replace("&", " and ")
        text = text.replace("%", " percent ")

        # Normalize spacing
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    def synthesize(self, text: str, speed: float = 1.0, voice: Optional[str] = None, student_id: Optional[str] = None) -> Optional[bytes]:
        """
        Synthesize a text string to WAV bytes with dynamic speed and voice.

        This is a synchronous method; call it via asyncio.run_in_executor
        from the async pipeline to avoid blocking the event loop.

        Args:
            text: The sentence or text fragment to speak.
            speed: Speed multiplier.
            voice: Optional custom voice name. Fallback to Config.KOKORO_VOICE if None.
            student_id: Optional student ID to check and record TTS character quota.

        Returns:
            Raw WAV file bytes (PCM 24 kHz mono), ready to send over WebSocket.
            Returns None if quota is exceeded. Returns empty bytes on failure or empty input.
        """
        text = text.strip()
        if not text:
            return b""

        if student_id is not None:
            from tts.tts_quota import tts_quota
            if not tts_quota.check_budget(student_id):
                logger.warning("TTS quota exceeded for student_id=%s. Skipping synthesis.", student_id)
                return None

        # Preprocess text to improve Kokoro pronunciation
        text = self._preprocess_text(text)

        selected_voice = voice if voice is not None else Config.KOKORO_VOICE
        try:
            audio_chunks: list[np.ndarray] = []

            # KPipeline is a generator that yields (graphemes, phonemes, audio)
            generator = self.pipeline(
                text,
                voice=selected_voice,
                speed=speed,
            )
            for _, _, audio in generator:
                if audio is not None and len(audio) > 0:
                    audio_chunks.append(audio)

            if not audio_chunks:
                logger.warning("Kokoro produced no audio for: %r using voice %s", text[:60], selected_voice)
                return b""

            # Combine all audio chunks into a single array
            combined = np.concatenate(audio_chunks)

            # Record usage
            if student_id is not None:
                from tts.tts_quota import tts_quota
                tts_quota.record_usage(student_id, len(text))

            # Encode to WAV in-memory (no disk I/O)
            buf = io.BytesIO()
            sf.write(buf, combined, self.sample_rate, format="WAV", subtype="PCM_16")
            buf.seek(0)
            wav_bytes = buf.read()

            logger.debug(
                "TTS synthesized %d chars -> %d bytes WAV using voice %s", len(text), len(wav_bytes), selected_voice
            )
            return wav_bytes

        except Exception as exc:
            logger.exception("Kokoro synthesis error for %r using voice %s: %s", text[:60], selected_voice, exc)
            return b""

