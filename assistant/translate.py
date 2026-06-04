"""
İngilizce haber metinlerini Türkçeye çevirir (LLM değil; çeviri API).
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

logger = logging.getLogger("assistant.translate")

_TURKISH_CHARS = set("çğıöşüÇĞİÖŞÜ")


def looks_non_turkish(text: str) -> bool:
    """Metnin büyük olasılıkla Türkçe olmadığını tahmin eder."""
    if not text or len(text.strip()) < 4:
        return False
    if any(ch in _TURKISH_CHARS for ch in text):
        return False
    letters = re.findall(r"[A-Za-z]", text)
    if len(letters) < 8:
        return False
    common_en = (
        " the ",
        " and ",
        " of ",
        " to ",
        " in ",
        " for ",
        " with ",
        " says ",
        " after ",
    )
    lower = f" {text.lower()} "
    return any(word in lower for word in common_en)


@lru_cache(maxsize=256)
def translate_to_turkish(text: str) -> str:
    """Kısa metni Türkçeye çevirir; hata olursa orijinali döndürür."""
    cleaned = text.strip()
    if not cleaned or not looks_non_turkish(cleaned):
        return cleaned

    try:
        from deep_translator import GoogleTranslator

        translated = GoogleTranslator(source="auto", target="tr").translate(cleaned)
        if translated:
            logger.debug("Çevrildi: %s -> %s", cleaned[:40], translated[:40])
            return translated
    except Exception as exc:
        logger.warning("Çeviri başarısız: %s", exc)
    return cleaned


def ensure_turkish(text: str) -> str:
    """Sesli okuma ve ekran için Türkçe metin sağlar."""
    return translate_to_turkish(text) if text else text
