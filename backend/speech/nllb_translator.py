"""
EduMentor Voice — NLLB CTranslate2 Translation Bridge

Translates Indic languages (Kannada, Marathi) to English, and English responses
back to target Indic languages. Uses a quantized CTranslate2 NLLB-200 model.
"""

import os
import time
import logging
from typing import Optional, Tuple

import ctranslate2
import transformers

logger = logging.getLogger("edumentor.speech.nllb_translator")


class NLLBTranslator:
    """
    CTranslate2 NLLB-200 translator.
    Auto-converts the model from Hugging Face if not found locally.
    """

    def __init__(self) -> None:
        self.model_id = "facebook/nllb-200-distilled-600M"

        # Look for the pre-converted CTranslate2 model in known locations
        # (converted during feasibility study via ct2-transformers-converter)
        candidate_dirs = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nllb_ct2"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scratch", "nllb_ct2"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch", "nllb_ct2"),
        ]
        self.output_dir = None
        for d in candidate_dirs:
            if os.path.isdir(d) and os.path.exists(os.path.join(d, "model.bin")):
                self.output_dir = os.path.normpath(d)
                logger.info("Found pre-converted NLLB CTranslate2 model at: %s", self.output_dir)
                break

        if self.output_dir is None:
            # Fall back to speech/data/nllb_ct2 and trigger conversion
            self.output_dir = os.path.normpath(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nllb_ct2")
            )
            self._ensure_model_converted()

        
        logger.info("Loading NLLB CTranslate2 translator from %s ...", self.output_dir)
        # Use 4 threads for optimal parallel CPU performance
        self.translator = ctranslate2.Translator(
            self.output_dir,
            device="cpu",
            inter_threads=4,
            intra_threads=4
        )
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(self.model_id)
        logger.info("[OK] NLLB Translator ready on CPU.")

    def _ensure_model_converted(self) -> None:
        """Helper to convert HF transformers model to CTranslate2 format if missing."""
        if not os.path.exists(self.output_dir):
            os.makedirs(os.path.dirname(self.output_dir), exist_ok=True)
            logger.info("CTranslate2 NLLB model not found at %s. Converting on the fly...", self.output_dir)
            t0 = time.time()
            try:
                import ctranslate2.converters
                converter = ctranslate2.converters.TransformersConverter(self.model_id)
                converter.convert(self.output_dir, quantization="int8")
                logger.info("[OK] NLLB conversion completed in %.2fs", time.time() - t0)
            except Exception as e:
                logger.exception("Failed to convert NLLB model: %s", e)
                raise RuntimeError(f"NLLB conversion failed: {e}") from e

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> Tuple[str, float]:
        """
        Translate text from src_lang to tgt_lang.
        Language codes should be NLLB-200 format (e.g. 'eng_Latn', 'kan_Knda', 'mar_Deva').
        Returns (translation_text, latency_seconds).
        """
        text = text.strip()
        if not text:
            return "", 0.0

        t_start = time.time()
        try:
            source_tokens = self.tokenizer.tokenize(text)
            
            # Prepend source language token, append EOS
            input_tokens = [src_lang] + source_tokens + ["</s>"]
            
            # Translate
            results = self.translator.translate_batch(
                [input_tokens],
                target_prefix=[[tgt_lang]],
                beam_size=4,
                max_decoding_length=128
            )
            
            target_tokens = results[0].hypotheses[0]
            
            # Strip target language prefix token if it's there
            if target_tokens and target_tokens[0] == tgt_lang:
                target_tokens = target_tokens[1:]
                
            token_ids = self.tokenizer.convert_tokens_to_ids(target_tokens)
            translation = self.tokenizer.decode(token_ids, skip_special_tokens=True).strip()
            
            latency = time.time() - t_start
            logger.debug("NLLB Translated [%s -> %s] in %.2fs: %r -> %r", src_lang, tgt_lang, latency, text[:60], translation[:60])
            return translation, latency
        except Exception as e:
            logger.exception("NLLB Translation failed: %s", e)
            return text, time.time() - t_start


# Singleton
nllb_translator: Optional[NLLBTranslator] = None


def get_translator() -> NLLBTranslator:
    """Get or initialize the global NLLBTranslator singleton."""
    global nllb_translator
    if nllb_translator is None:
        nllb_translator = NLLBTranslator()
    return nllb_translator
