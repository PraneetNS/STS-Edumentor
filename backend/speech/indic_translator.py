"""
EduMentor Voice — AI4Bharat IndicTrans2 Translation Bridge

Replaces the fallback Meta NLLB-200 pipeline with AI4Bharat's purpose-built
IndicTrans2 (1B parameter) models for Indic ↔ English translation.

Requires:
  - pip install git+https://github.com/VarunGumma/IndicTransToolkit.git
  - HF_TOKEN env variable with access to ai4bharat gated repos
"""

import logging
import os
import time
from typing import Optional, Tuple

import torch

logger = logging.getLogger("edumentor.speech.indic_translator")


class IndicTranslator:
    """
    AI4Bharat IndicTrans2 translation engine.

    Uses two separate model checkpoints:
      - indictrans2-indic-en-1B  (Indic → English)
      - indictrans2-en-indic-1B  (English → Indic)

    Both are lazily loaded on first use to avoid loading unused directions.
    """

    INDIC_EN_MODEL = "ai4bharat/indictrans2-indic-en-1B"
    EN_INDIC_MODEL = "ai4bharat/indictrans2-en-indic-1B"

    # IndicTrans2 uses Flores-200 language codes (same as NLLB-200)
    LANG_MAP = {
        "hindi":   "hin_Deva",
        "kannada": "kan_Knda",
        "marathi": "mar_Deva",
        "english": "eng_Latn",
    }

    def __init__(self) -> None:
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._indic_en_model = None
        self._indic_en_tokenizer = None
        self._en_indic_model = None
        self._en_indic_tokenizer = None
        self._processor = None   # IndicProcessor (shared across directions)
        logger.info("[OK] IndicTranslator initialized (lazy-load, device=%s).", self.device)

    def _get_processor(self):
        if self._processor is None:
            from IndicTransToolkit import IndicProcessor
            self._processor = IndicProcessor(inference=True)
            logger.info("[OK] IndicProcessor loaded.")
        return self._processor

    def _load_indic_en(self):
        """Lazy-load the Indic→English model."""
        if self._indic_en_model is None:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            logger.info("Loading IndicTrans2 Indic→EN model (%s) ...", self.INDIC_EN_MODEL)
            t0 = time.time()
            self._indic_en_tokenizer = AutoTokenizer.from_pretrained(
                self.INDIC_EN_MODEL, trust_remote_code=True
            )
            self._indic_en_model = AutoModelForSeq2SeqLM.from_pretrained(
                self.INDIC_EN_MODEL,
                trust_remote_code=True,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            ).to(self.device)
            self._indic_en_model.eval()
            logger.info("[OK] IndicTrans2 Indic→EN loaded in %.2fs.", time.time() - t0)

    def _load_en_indic(self):
        """Lazy-load the English→Indic model."""
        if self._en_indic_model is None:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            logger.info("Loading IndicTrans2 EN→Indic model (%s) ...", self.EN_INDIC_MODEL)
            t0 = time.time()
            self._en_indic_tokenizer = AutoTokenizer.from_pretrained(
                self.EN_INDIC_MODEL, trust_remote_code=True
            )
            self._en_indic_model = AutoModelForSeq2SeqLM.from_pretrained(
                self.EN_INDIC_MODEL,
                trust_remote_code=True,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            ).to(self.device)
            self._en_indic_model.eval()
            logger.info("[OK] IndicTrans2 EN→Indic loaded in %.2fs.", time.time() - t0)

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> Tuple[str, float]:
        """
        Translate text from src_lang to tgt_lang.

        Language codes accept both canonical names ('hindi', 'kannada', 'marathi', 'english')
        and Flores-200 codes ('hin_Deva', 'kan_Knda', etc.).

        Returns: (translated_text, latency_seconds)
        """
        text = text.strip()
        if not text:
            return "", 0.0

        # Resolve canonical name → Flores code
        src = self.LANG_MAP.get(src_lang, src_lang)
        tgt = self.LANG_MAP.get(tgt_lang, tgt_lang)

        t_start = time.time()
        try:
            ip = self._get_processor()
            is_en_to_indic = (src == "eng_Latn")

            if is_en_to_indic:
                self._load_en_indic()
                model = self._en_indic_model
                tokenizer = self._en_indic_tokenizer
            else:
                self._load_indic_en()
                model = self._indic_en_model
                tokenizer = self._indic_en_tokenizer

            # Pre-process
            batch = ip.preprocess_batch([text], src_lang=src, tgt_lang=tgt)
            encoded = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt",
            ).to(self.device)

            # Translate
            with torch.inference_mode():
                generated_tokens = model.generate(
                    **encoded,
                    num_beams=4,
                    num_return_sequences=1,
                    max_new_tokens=256,
                )

            # Decode
            raw = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)
            translations = ip.postprocess_batch(raw, lang=tgt)
            translation = translations[0].strip() if translations else text

            latency = time.time() - t_start
            logger.debug(
                "IndicTrans2 [%s→%s] %.2fs: %r → %r",
                src, tgt, latency, text[:60], translation[:60]
            )
            return translation, latency

        except Exception as e:
            logger.exception("IndicTrans2 translation failed: %s", e)
            return text, time.time() - t_start


# Singleton
_indic_translator: Optional[IndicTranslator] = None


def get_translator() -> IndicTranslator:
    """Get or initialize the global IndicTranslator singleton."""
    global _indic_translator
    if _indic_translator is None:
        _indic_translator = IndicTranslator()
    return _indic_translator
