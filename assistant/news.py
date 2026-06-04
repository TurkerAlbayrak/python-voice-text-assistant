"""
RSS tabanlı haber sistemi: Türkiye, dünya ve ekonomi kategorileri.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import feedparser

from translate import ensure_turkish
from utils import AssistantError, NetworkError, load_config, safe_request

logger = logging.getLogger("assistant.news")


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    link: str = ""
    summary: str = ""


# Kategori -> (kaynak adı, RSS URL) listesi
# Not: Eski TRT/AA URL'leri 404/502 verebildiği için güncel kaynaklar kullanılır.
RSS_FEEDS: dict[str, list[tuple[str, str]]] = {
    "turkey": [
        ("TRT Haber", "https://www.trthaber.com/sondakika_articles.rss"),
        ("CNN Türk", "https://www.cnnturk.com/feed/rss/turkiye/news"),
        ("NTV", "https://www.ntv.com.tr/gundem.rss"),
        ("Anadolu Ajansı", "https://www.aa.com.tr/tr/rss/default?cat=gundem"),
    ],
    "world": [
        ("CNN Türk Dünya", "https://www.cnnturk.com/feed/rss/dunya/news"),
        ("NTV Dünya", "https://www.ntv.com.tr/dunya.rss"),
        ("TRT Haber", "https://www.trthaber.com/sondakika_articles.rss"),
        ("Anadolu Ajansı Dünya", "https://www.aa.com.tr/tr/rss/default?cat=dunya"),
    ],
    "economy": [
        ("CNN Türk Ekonomi", "https://www.cnnturk.com/feed/rss/ekonomi/news"),
        ("NTV Ekonomi", "https://www.ntv.com.tr/ekonomi.rss"),
        ("Anadolu Ekonomi", "https://www.aa.com.tr/tr/rss/default?cat=ekonomi"),
    ],
}

CATEGORY_LABELS = {
    "turkey": "Türkiye Gündemi",
    "world": "Dünya Gündemi",
    "economy": "Ekonomi",
}


class NewsError(AssistantError):
    """Haber modülü hataları."""


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _parse_entry(entry: Any, source: str, *, turkish_only: bool = True) -> Optional[NewsItem]:
    title = _clean_text(getattr(entry, "title", "") or "")
    if not title:
        return None
    if turkish_only:
        title = ensure_turkish(title)

    summary = _clean_text(getattr(entry, "summary", "") or getattr(entry, "description", "") or "")
    if turkish_only and summary:
        summary = ensure_turkish(summary)
    if len(summary) > 220:
        summary = summary[:217] + "..."
    link = getattr(entry, "link", "") or ""
    return NewsItem(title=title, source=source, link=link, summary=summary)


def _fetch_feed(source: str, url: str, limit: int) -> list[NewsItem]:
    items: list[NewsItem] = []
    config = load_config()
    timeout = config.get("request_timeout", 15)

    try:
        response = safe_request(url, timeout=timeout)
        parsed = feedparser.parse(response.content)
    except NetworkError as exc:
        logger.warning("%s RSS alınamadı: %s", source, exc)
        return items
    except Exception as exc:
        logger.warning("%s RSS okunamadı: %s", source, exc)
        return items

    if getattr(parsed, "bozo", False) and not parsed.entries:
        logger.warning(
            "%s RSS bozuk veya boş: %s",
            source,
            getattr(parsed, "bozo_exception", ""),
        )

    for entry in parsed.entries[:limit]:
        item = _parse_entry(entry, source)
        if item:
            items.append(item)
    return items


def fetch_category(category: str, limit: Optional[int] = None) -> list[NewsItem]:
    """Belirtilen kategoriden haberleri çeker."""
    if category not in RSS_FEEDS:
        raise NewsError(f"Bilinmeyen kategori: {category}")

    config = load_config()
    limits = config.get("news_limits", {})
    default_limit = limits.get(category, 5)
    per_feed = max(2, (limit or default_limit))

    collected: list[NewsItem] = []
    seen_titles: set[str] = set()

    for source, url in RSS_FEEDS[category]:
        try:
            batch = _fetch_feed(source, url, per_feed)
        except NetworkError as exc:
            logger.warning("Ağ hatası (%s): %s", source, exc)
            continue

        for item in batch:
            key = item.title.lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            collected.append(item)
            if len(collected) >= (limit or default_limit):
                return collected[: limit or default_limit]

    return collected[: limit or default_limit]


def fetch_all_briefing() -> dict[str, list[NewsItem]]:
    """Sabah brifingi için tüm kategorileri getirir."""
    config = load_config()
    limits = config.get("news_limits", {})
    return {
        "turkey": fetch_category("turkey", limits.get("turkey", 5)),
        "world": fetch_category("world", limits.get("world", 5)),
        "economy": fetch_category("economy", limits.get("economy", 5)),
    }


def format_news_list(items: list[NewsItem], numbered: bool = True) -> str:
    """Haber listesini ekran çıktısı için biçimlendirir."""
    if not items:
        return "  Haber bulunamadı."

    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        prefix = f"{index}. " if numbered else "- "
        line = f"{prefix}{item.title} ({item.source})"
        if item.summary:
            line += f"\n     {item.summary}"
        lines.append(line)
    return "\n".join(lines)


def format_news_speech(items: list[NewsItem], *, max_items: int | None = None) -> str:
    """Sesli okuma — numarasız başlıklar (ui_display ile uyumlu)."""
    from ui_display import format_news_speech as _speech

    return _speech(items, max_items=max_items)


def format_category_block(category: str, items: list[NewsItem]) -> str:
    """Tek kategori bloğunu metin olarak döndürür (konsol / yedek)."""
    from ui_display import format_category_display

    return format_category_display(category, items)


def format_briefing_news(briefing: dict[str, list[NewsItem]]) -> str:
    """Tüm haber brifingini birleştirir."""
    sections = []
    for category in ("turkey", "world", "economy"):
        sections.append(format_category_block(category, briefing.get(category, [])))
    return "\n".join(sections)


def format_briefing_news_speech(
    briefing: dict[str, list[NewsItem]],
    *,
    one_per_category: bool = True,
) -> str:
    """Sesli okuma: her kategoriden bir haber, numarasız."""
    from ui_display import format_briefing_news_speech as _brief_speech

    return _brief_speech(briefing, one_per_category=one_per_category)
