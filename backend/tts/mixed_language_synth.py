import io
import logging
import numpy as np
import soundfile as sf
import re
from typing import Optional

logger = logging.getLogger("edumentor.speech.mixed_language_synth")

def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """
    Performs fast linear interpolation to resample audio between different sample rates.
    """
    if orig_sr == target_sr:
        return audio
    num_samples = int(len(audio) * target_sr / orig_sr)
    x_orig = np.linspace(0, len(audio) - 1, len(audio))
    x_new = np.linspace(0, len(audio) - 1, num_samples)
    return np.interp(x_new, x_orig, audio).astype(np.float32)

class MixedLanguageSynthesizer:
    """
    Splits text containing regional language sentences and English technical terms,
    synthesizes the English segments using Kokoro, the native segments using MMS-TTS,
    resamples them to a uniform 16 kHz mono format, and stitches them with a small pause.
    """
    def __init__(self, kokoro_engine=None) -> None:
        self.kokoro = kokoro_engine
        # Lazy-load the Meta MMS-TTS engine singleton
        self.mms_tts = None

    def get_mms_tts(self):
        if self.mms_tts is None:
            from speech.mms_tts import get_mms_tts_engine
            self.mms_tts = get_mms_tts_engine()
        return self.mms_tts

    def get_kokoro_engine(self):
        if self.kokoro is None:
            try:
                # Try importing/grabbing the global instance from main
                import main
                if hasattr(main, "kokoro_engine") and main.kokoro_engine is not None:
                    self.kokoro = main.kokoro_engine
            except Exception:
                pass
        
        if self.kokoro is None:
            from tts.kokoro_engine import KokoroEngine
            self.kokoro = KokoroEngine()
            
        return self.kokoro

    def synthesize_mixed(self, text: str, target_lang: str, mms_lang_code: str) -> bytes:
        """
        Synthesizes text containing a mix of regional language and English terms
        by segmenting the text and stitching audio clips from MMS-TTS and Kokoro.
        """
        if not text or not text.strip():
            return b""

        # Split text into segments based on English word sequences (Latin characters).
        # E.g. "machine learning", "recursion", etc.
        pattern = re.compile(r'([a-zA-Z0-9_\'-]+(?:\s+[a-zA-Z0-9_\'-]+)*)')
        parts = pattern.split(text)
        
        segments = []
        for part in parts:
            part_strip = part.strip()
            if not part_strip:
                continue
            # If the segment contains Latin alphabet, treat it as English
            if re.search(r'[a-zA-Z]', part):
                segments.append({"text": part_strip, "type": "english"})
            else:
                segments.append({"text": part_strip, "type": "native"})

        # Merge consecutive segments of the same type
        merged_segments = []
        for seg in segments:
            if not merged_segments:
                merged_segments.append(seg)
            elif merged_segments[-1]["type"] == seg["type"]:
                merged_segments[-1]["text"] += " " + seg["text"]
            else:
                merged_segments.append(seg)

        if not merged_segments:
            return b""

        audio_clips = []
        target_sr = 16000 # 16 kHz Mono target sample rate
        
        kokoro = self.get_kokoro_engine()
        mms = self.get_mms_tts()

        for seg in merged_segments:
            seg_text = seg["text"].strip()
            if not seg_text:
                continue

            try:
                if seg["type"] == "english":
                    logger.info("[MixedSynth] Synthesizing English term: %r using Kokoro", seg_text)
                    # We pass the default config speed and voice parameters if available
                    from config import Config
                    wav_bytes = kokoro.synthesize(
                        seg_text,
                        voice=Config.KOKORO_VOICE,
                        speed=Config.KOKORO_SPEED
                    )
                    if wav_bytes:
                        data, sr = sf.read(io.BytesIO(wav_bytes))
                        # If stereo, convert to mono
                        if data.ndim > 1:
                            data = np.mean(data, axis=1)
                        data_resampled = resample_audio(data, sr, target_sr)
                        audio_clips.append(data_resampled)
                else:
                    logger.info("[MixedSynth] Synthesizing native segment: %r using MMS-TTS", seg_text)
                    wav_bytes = mms.synthesize(seg_text, mms_lang_code)
                    if wav_bytes:
                        data, sr = sf.read(io.BytesIO(wav_bytes))
                        if data.ndim > 1:
                            data = np.mean(data, axis=1)
                        data_resampled = resample_audio(data, sr, target_sr)
                        audio_clips.append(data_resampled)
            except Exception as e:
                logger.error("[MixedSynth] Failed to synthesize segment %r: %s", seg_text, e)

        if not audio_clips:
            return b""

        # Stitch clips with an 80ms silence gap
        gap_samples = int(0.08 * target_sr)
        silence_gap = np.zeros(gap_samples, dtype=np.float32)

        stitched_audio = []
        for i, clip in enumerate(audio_clips):
            stitched_audio.append(clip)
            if i < len(audio_clips) - 1:
                stitched_audio.append(silence_gap)

        stitched_array = np.concatenate(stitched_audio)

        # Write to WAV bytes
        buf = io.BytesIO()
        sf.write(buf, stitched_array, target_sr, format="WAV", subtype="PCM_16")
        buf.seek(0)
        return buf.read()
