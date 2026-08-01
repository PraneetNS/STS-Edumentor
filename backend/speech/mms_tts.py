"""
EduMentor Voice — Meta MMS-TTS Engine

Uses Meta's official Massively Multilingual Speech (MMS) checkpoints:
  - Hin: facebook/mms-tts-hin
  - Kan: facebook/mms-tts-kan
  - Mar: facebook/mms-tts-mar

These checkpoints are un-gated, extremely lightweight (~36M params each),
synthesize in <100ms on GPU, and require minimal VRAM (~150MB).
"""

import io
import logging
import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
import time
from typing import Optional, Dict

import numpy as np
import soundfile as sf
import torch
from transformers import VitsModel, AutoTokenizer

logger = logging.getLogger("edumentor.speech.mms_tts")


class MMSTTSEngine:
    """
    Genuine Meta MMS-TTS engine using open VITS checkpoints.
    """

    LANG_MODEL_MAP = {
        "hin": "facebook/mms-tts-hin",
        "kan": "facebook/mms-tts-kan",
        "mar": "facebook/mms-tts-mar",
    }

    def __init__(self) -> None:
        import threading
        self.device = os.getenv("MMS_TTS_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
        self._models: Dict[str, VitsModel] = {}
        # Separate CPU-resident models cached to prevent weight movement overhead during fallbacks
        self._models_cpu: Dict[str, VitsModel] = {}
        self._tokenizers: Dict[str, AutoTokenizer] = {}
        self._lock = threading.Lock()
        self.warmed_up = False
        logger.info(
            "[OK] Meta MMS-TTS engine initialized (lazy-load, device=%s).", self.device
        )
        # Background warmup task to load and synthesize dummy speech for all 3 languages
        threading.Thread(target=self._background_warmup, daemon=True).start()

    def _load_model(self, lang: str) -> None:
        """Lazy-load the tokenizer and VITS model for the given language."""
        if lang not in self.LANG_MODEL_MAP:
            raise ValueError(f"Unsupported language code: {lang}")

        with self._lock:
            if lang not in self._models:
                model_id = self.LANG_MODEL_MAP[lang]
                logger.info("Loading Meta MMS-TTS model (%s) on %s ...", model_id, self.device)
                t0 = time.time()

                if self.device == "cpu":
                    from config import Config
                    torch.set_num_threads(Config.TTS_CPU_THREADS)
                    logger.info("Set PyTorch CPU threads to: %d", Config.TTS_CPU_THREADS)

                tokenizer = AutoTokenizer.from_pretrained(model_id)
                model = VitsModel.from_pretrained(model_id).to(self.device)
                model.eval()

                self._tokenizers[lang] = tokenizer
                self._models[lang] = model
                logger.info(
                    "[OK] Meta MMS-TTS %s loaded in %.2fs on %s.", model_id, time.time() - t0, self.device
                )

    def _background_warmup(self) -> None:
        """Background warmup task to pre-load and cache the VITS checkpoints."""
        logger.info("Starting background warmup for Meta MMS-TTS...")
        try:
            warmup_words = {
                "hin": "नमस्ते",
                "kan": "ನಮಸ್ಕಾರ",
                "mar": "नमस्कार"
            }
            for lang_code in ["hin", "kan", "mar"]:
                logger.info("Warming up Meta MMS-TTS for lang '%s'...", lang_code)
                self._load_model(lang_code)
                self.synthesize(warmup_words[lang_code], lang_code)
            
            if self.device == "cuda":
                allocated = torch.cuda.memory_allocated(0) // (1024**2)
                reserved  = torch.cuda.memory_reserved(0)  // (1024**2)
                logger.info(
                    "[GPU] Meta MMS-TTS warmup complete. VRAM allocated=%dMiB reserved=%dMiB",
                    allocated, reserved
                )
            logger.info("Meta MMS-TTS background warmup complete.")
        except Exception as e:
            logger.warning("Meta MMS-TTS background warmup failed: %s", e)
        finally:
            self.warmed_up = True

    def synthesize(self, text: str, lang: str) -> bytes:
        """
        Synthesize text into WAV bytes using Meta VITS MMS-TTS.

        Args:
            text: Native script text (Devanagari/Kannada).
            lang: Language code — 'hin', 'kan', 'mar'.

        Returns:
            WAV audio bytes.
        """
        text = text.strip()
        if not text:
            return b""

        t_start = time.time()
        try:
            self._load_model(lang)
            tokenizer = self._tokenizers[lang]
            model = self._models[lang]

            inputs = tokenizer(text, return_tensors="pt").to(self.device)
            # Guard against zero-token outputs which cause a VITS forward pass pad crash.
            # Without this, modeling_vits raises ValueError: negative output size.
            if "input_ids" in inputs and inputs["input_ids"].shape[1] == 0:
                logger.warning(
                    "[MMS-TTS] Tokenizer returned 0 tokens for text %r (likely unsupported characters/script) — skipping model forward pass.",
                    text
                )
                return b""

            try:
                # Generate waveform waveform tensor is shape (1, num_samples)
                with torch.no_grad():
                    output = model(**inputs).waveform
            except (torch.cuda.OutOfMemoryError, RuntimeError) as oom_exc:
                if self.device == "cuda" and ("CUDA out of memory" in str(oom_exc) or isinstance(oom_exc, torch.cuda.OutOfMemoryError)):
                    logger.warning(
                        "[GPU OOM] Meta MMS-TTS CUDA OOM translating %d chars — falling back to CPU. Error: %s",
                        len(text), oom_exc
                    )
                    try:
                        torch.cuda.empty_cache()
                        # Lazy-load a separate CPU model instance if not already cached.
                        # This prevents the need to physically swap primary GPU model weights over PCIe.
                        with self._lock:
                            if self._models_cpu.get(lang) is None:
                                model_id = self.LANG_MODEL_MAP[lang]
                                logger.info("Lazy-loading separate Meta MMS-TTS CPU model instance for %s fallback (%s) ...", lang, model_id)
                                model_cpu = VitsModel.from_pretrained(model_id).to("cpu")
                                model_cpu.eval()
                                self._models_cpu[lang] = model_cpu
                            else:
                                model_cpu = self._models_cpu[lang]

                        inputs_cpu = tokenizer(text, return_tensors="pt").to("cpu")
                        with torch.no_grad():
                            output = model_cpu(**inputs_cpu).waveform
                    except Exception as fallback_exc:
                        logger.error(
                            "[GPU OOM] Failure during CPU fallback synthesis for text %r. Returning empty waveform. Error: %s",
                            text, fallback_exc
                        )
                        return b""
                else:
                    raise

            audio_arr = output[0].cpu().numpy()
            if audio_arr.ndim > 1:
                audio_arr = audio_arr.squeeze()
            if audio_arr.ndim == 0:
                audio_arr = np.array([0.0], dtype=np.float32)

            sampling_rate = model.config.sampling_rate

            # Encode to WAV bytes
            buf = io.BytesIO()
            sf.write(buf, audio_arr, sampling_rate, format="WAV", subtype="PCM_16")
            buf.seek(0)
            wav_bytes = buf.read()

            latency = time.time() - t_start
            logger.debug(
                "Meta MMS-TTS synthesized %d chars (%s) on %s → %d bytes WAV in %.2fs",
                len(text), lang, self.device, len(wav_bytes), latency,
            )
            return wav_bytes

        except Exception as e:
            logger.exception(
                "Meta MMS-TTS synthesis failed for %r (%s): %s", text[:60], lang, e
            )
            return b""


# Singleton
_mms_tts_engine: Optional[MMSTTSEngine] = None


def get_mms_tts_engine() -> MMSTTSEngine:
    """Get or initialize the global MMSTTSEngine singleton."""
    global _mms_tts_engine
    if _mms_tts_engine is None:
        _mms_tts_engine = MMSTTSEngine()
    return _mms_tts_engine
