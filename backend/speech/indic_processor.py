"""
Pure-Python shim for IndicProcessor used by AI4Bharat IndicTrans2.

This replaces the IndicTransToolkit Cython extension which requires MSVC.
It implements only preprocess_batch and postprocess_batch — the two methods
called during inference — using the same underlying indicnlp + sacremoses stack.

Reference implementation:
  https://github.com/VarunGumma/IndicTransToolkit/blob/main/IndicTransToolkit/processor.pyx
"""

import re
import unicodedata
from typing import List, Optional

# Flores-200 → ISO 639-1 codes (for indicnlp tools)
_FLORES_TO_ISO = {
    "asm_Beng": "as", "ben_Beng": "bn", "guj_Gujr": "gu",
    "hin_Deva": "hi", "kan_Knda": "kn", "mal_Mlym": "ml",
    "mar_Deva": "mr", "npi_Deva": "ne", "ory_Orya": "or",
    "pan_Guru": "pa", "san_Deva": "hi", "tam_Taml": "ta",
    "tel_Telu": "te", "urd_Arab": "ur", "eng_Latn": "en",
    "mni_Beng": "bn", "bho_Deva": "hi", "doi_Deva": "hi",
    "kas_Deva": "hi", "mai_Deva": "hi", "sat_Olck": "or",
    "snd_Deva": "hi",
}

# Indic digits → ASCII digits (from 0..9 across all Indic scripts)
_INDIC_DIGITS = str.maketrans(
    "".join(chr(base + d) for base in (0x0966, 0x09E6, 0x0A66, 0x0AE6, 0x0B66,
                                        0x0BE6, 0x0C66, 0x0CE6, 0x0D66, 0x0E50,
                                        0x06F0) for d in range(10)),
    "0123456789" * 11,
)

_MULTISPACE = re.compile(r" +")


class IndicProcessor:
    """
    Pure-Python inference-mode preprocessing/postprocessing for IndicTrans2.
    Matches the API of IndicTransToolkit.IndicProcessor.
    """

    def __init__(self, inference: bool = True) -> None:
        self.inference = inference
        self._en_normalizer = None
        self._en_tok = None
        self._en_detok = None
        self._indic_normalizers = {}

        try:
            from sacremoses import MosesPunctNormalizer, MosesTokenizer, MosesDetokenizer
            self._en_normalizer = MosesPunctNormalizer(lang="en")
            self._en_tok = MosesTokenizer(lang="en")
            self._en_detok = MosesDetokenizer(lang="en")
        except Exception:
            pass  # graceful degradation if sacremoses unavailable

    def _get_indic_normalizer(self, iso_lang: str):
        if iso_lang not in self._indic_normalizers:
            try:
                from indicnlp.normalize.indic_normalize import IndicNormalizerFactory
                factory = IndicNormalizerFactory()
                self._indic_normalizers[iso_lang] = factory.get_normalizer(iso_lang)
            except Exception:
                self._indic_normalizers[iso_lang] = None
        return self._indic_normalizers[iso_lang]

    def _normalize_text(self, text: str, lang: str) -> str:
        """Light normalization: collapse spaces, strip, translate Indic digits."""
        text = text.translate(_INDIC_DIGITS)
        text = unicodedata.normalize("NFC", text)
        text = _MULTISPACE.sub(" ", text).strip()
        return text

    def _preprocess_indic(self, text: str, lang: str) -> str:
        iso = _FLORES_TO_ISO.get(lang, "hi")
        text = self._normalize_text(text, iso)
        normalizer = self._get_indic_normalizer(iso)
        if normalizer:
            try:
                text = normalizer.normalize(text)
            except Exception:
                pass
        try:
            from indicnlp.tokenize import indic_tokenize
            tokens = indic_tokenize.trivial_tokenize(text, iso)
            text = " ".join(tokens)
        except Exception:
            pass
        return text.strip()

    def _preprocess_en(self, text: str) -> str:
        text = self._normalize_text(text, "en")
        if self._en_normalizer:
            try:
                text = self._en_normalizer.normalize(text)
            except Exception:
                pass
        if self._en_tok:
            try:
                text = " ".join(self._en_tok.tokenize(text, escape=False))
            except Exception:
                pass
        return text.strip()

    def preprocess_batch(
        self,
        batch: List[str],
        src_lang: str,
        tgt_lang: str,
        show_progress_bar: bool = False,
    ) -> List[str]:
        """Preprocess a list of sentences before feeding to IndicTrans2."""
        result = []
        for text in batch:
            if src_lang == "eng_Latn":
                processed = self._preprocess_en(text)
            else:
                processed = self._preprocess_indic(text, src_lang)
            result.append(processed)
        return result

    def _postprocess_en(self, text: str) -> str:
        if self._en_detok:
            try:
                text = self._en_detok.detokenize(text.split(), return_str=True)
            except Exception:
                pass
        return text.strip()

    def _postprocess_indic(self, text: str, lang: str) -> str:
        iso = _FLORES_TO_ISO.get(lang, "hi")
        try:
            from indicnlp.tokenize import indic_detokenize
            text = indic_detokenize.trivial_detokenize(text, iso)
        except Exception:
            pass
        return text.strip()

    def postprocess_batch(
        self,
        batch: List[str],
        lang: str,
        show_progress_bar: bool = False,
    ) -> List[str]:
        """Postprocess IndicTrans2 output back to natural text."""
        result = []
        for text in batch:
            if lang == "eng_Latn":
                processed = self._postprocess_en(text)
            else:
                processed = self._postprocess_indic(text, lang)
            result.append(processed)
        return result
