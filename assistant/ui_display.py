"""
Arayüz için yapılandırılmış veri ve kart tabanlı görünüm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import customtkinter as ctk

    from finance import RateInfo
    from news import NewsItem
    from weather import WeatherInfo


@dataclass
class BriefingData:
    """Sabah brifingi ekran verisi."""

    city: str
    weather: Optional["WeatherInfo"] = None
    weather_error: Optional[str] = None
    rates: Optional[dict[str, "RateInfo"]] = None
    rates_error: Optional[str] = None
    news: dict[str, list["NewsItem"]] = field(default_factory=dict)


# Kategori -> sesli okuma giriş cümlesi
SPEECH_CATEGORY_INTRO = {
    "turkey": "Türkiye gündeminden",
    "world": "Dünya gündeminden",
    "economy": "Ekonomiden",
}


def format_news_speech(
    items: list["NewsItem"],
    *,
    max_items: Optional[int] = None,
) -> str:
    """Numarasız haber başlıkları; varsayılan hepsi."""
    if not items:
        return "haber bulunamadı"
    subset = items if max_items is None else items[:max_items]
    return ". ".join(item.title for item in subset)


def format_category_speech(
    category: str,
    items: list["NewsItem"],
    *,
    count: int = 1,
) -> str:
    """Kategoriden belirtilen sayıda haberi numarasız okur."""
    intro = SPEECH_CATEGORY_INTRO.get(category, "Haber")
    if not items:
        return f"{intro}, haber bulunamadı"
    if count == 1:
        return f"{intro}, {items[0].title}"
    titles = format_news_speech(items, max_items=count)
    return f"{intro}: {titles}"


def format_briefing_news_speech(
    briefing: dict[str, list["NewsItem"]],
    *,
    one_per_category: bool = True,
) -> str:
    """Brifing için ses metni: her kategoriden bir haber."""
    parts: list[str] = []
    for category in ("turkey", "world", "economy"):
        items = briefing.get(category, [])
        if one_per_category:
            parts.append(format_category_speech(category, items, count=1))
        else:
            from news import CATEGORY_LABELS

            label = CATEGORY_LABELS.get(category, category)
            if items:
                parts.append(f"{label}: {format_news_speech(items)}")
            else:
                parts.append(f"{label} haberi bulunamadı")
    return ". ".join(parts)


def format_category_display(category: str, items: list["NewsItem"]) -> str:
    """Düz metin yedek görünüm (kart kullanılamazsa)."""
    from news import CATEGORY_LABELS

    label = CATEGORY_LABELS.get(category, category)
    lines = [label.upper(), "─" * 40, ""]
    if not items:
        lines.append("Haber bulunamadı.")
        return "\n".join(lines)
    for item in items:
        lines.append(item.title)
        lines.append(f"   Kaynak: {item.source}")
        if item.summary:
            lines.append(f"   {item.summary}")
        lines.append("")
    return "\n".join(lines).strip()


def format_finance_display(
    rates: dict[str, "RateInfo"],
) -> list[tuple[str, str, str, str]]:
    """Finans kartı: (ad, fiyat, değişim metni, renk)."""
    order = [
        ("usd", "Dolar"),
        ("eur", "Euro"),
        ("gbp", "Sterlin"),
        ("gram_altin", "Gram Altın"),
        ("ons_altin", "Ons Altın"),
    ]
    rows: list[tuple[str, str, str, str]] = []
    for key, label in order:
        if key in rates:
            info = rates[key]
            badge = info.format_change_badge()
            if badge.startswith("+"):
                color = "#52b788"
            elif badge.startswith("-"):
                color = "#e63946"
            elif badge == "degismedi":
                color = "gray55"
            else:
                color = "gray45"
                badge = "—"
            rows.append((label, f"{info.value:,.2f} {info.unit}", badge, color))
    return rows


def clear_content_frame(frame: "ctk.CTkScrollableFrame") -> None:
    for child in frame.winfo_children():
        child.destroy()


def add_section_header(frame: "ctk.CTkScrollableFrame", title: str, subtitle: str = "") -> None:
    import customtkinter as ctk

    box = ctk.CTkFrame(frame, fg_color="transparent")
    box.pack(fill="x", padx=8, pady=(16, 4))
    ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=20, weight="bold"), anchor="w").pack(
        fill="x"
    )
    if subtitle:
        ctk.CTkLabel(
            box, text=subtitle, font=ctk.CTkFont(size=13), text_color="gray65", anchor="w"
        ).pack(fill="x", pady=(2, 0))


def add_info_card(
    frame: "ctk.CTkScrollableFrame",
    title: str,
    lines: list[str],
    *,
    accent: str = "#1f538d",
) -> None:
    import customtkinter as ctk

    card = ctk.CTkFrame(frame, corner_radius=12, border_width=1, border_color="#2a2d34")
    card.pack(fill="x", padx=8, pady=6)

    bar = ctk.CTkFrame(card, width=4, corner_radius=4, fg_color=accent)
    bar.pack(side="left", fill="y", padx=(12, 0), pady=12)

    body = ctk.CTkFrame(card, fg_color="transparent")
    body.pack(side="left", fill="both", expand=True, padx=14, pady=12)

    ctk.CTkLabel(
        body, text=title, font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
    ).pack(fill="x")
    for line in lines:
        ctk.CTkLabel(
            body,
            text=line,
            font=ctk.CTkFont(size=13),
            text_color="gray85",
            anchor="w",
            justify="left",
            wraplength=720,
        ).pack(fill="x", pady=(4, 0))


def add_finance_card(
    frame: "ctk.CTkScrollableFrame",
    rows: list[tuple[str, str, str, str]],
) -> None:
    import customtkinter as ctk

    card = ctk.CTkFrame(frame, corner_radius=12, border_width=1, border_color="#2a2d34")
    card.pack(fill="x", padx=8, pady=6)

    ctk.CTkLabel(
        card,
        text="Finans  ·  düne göre",
        font=ctk.CTkFont(size=15, weight="bold"),
        anchor="w",
    ).pack(fill="x", padx=16, pady=(12, 8))

    grid = ctk.CTkFrame(card, fg_color="transparent")
    grid.pack(fill="x", padx=12, pady=(0, 12))

    for col, (name, value, change, color) in enumerate(rows):
        cell = ctk.CTkFrame(grid, corner_radius=8, fg_color="#2b2d31")
        cell.grid(row=0, column=col, padx=4, pady=4, sticky="nsew")
        grid.grid_columnconfigure(col, weight=1)
        ctk.CTkLabel(cell, text=name, font=ctk.CTkFont(size=11), text_color="gray60").pack(
            pady=(8, 0)
        )
        ctk.CTkLabel(
            cell, text=value, font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(2, 0))
        ctk.CTkLabel(
            cell,
            text=change,
            font=ctk.CTkFont(size=11),
            text_color=color,
        ).pack(pady=(0, 8))


def add_news_card(
    frame: "ctk.CTkScrollableFrame",
    category: str,
    items: list["NewsItem"],
) -> None:
    import customtkinter as ctk
    from news import CATEGORY_LABELS

    label = CATEGORY_LABELS.get(category, category)
    accents = {"turkey": "#c1121f", "world": "#1d3557", "economy": "#2d6a4f"}
    accent = accents.get(category, "#1f538d")

    card = ctk.CTkFrame(frame, corner_radius=12, border_width=1, border_color="#2a2d34")
    card.pack(fill="x", padx=8, pady=6)

    head = ctk.CTkFrame(card, fg_color="transparent")
    head.pack(fill="x", padx=16, pady=(12, 8))
    ctk.CTkLabel(
        head,
        text=label,
        font=ctk.CTkFont(size=15, weight="bold"),
        text_color=accent,
        anchor="w",
    ).pack(side="left")

    if not items:
        ctk.CTkLabel(
            card, text="Haber bulunamadı.", text_color="gray60"
        ).pack(padx=16, pady=(0, 12))
        return

    for item in items:
        row = ctk.CTkFrame(card, fg_color="#2b2d31", corner_radius=8)
        row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(
            row,
            text=item.title,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=700,
        ).pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            row,
            text=item.source,
            font=ctk.CTkFont(size=11),
            text_color="gray55",
            anchor="w",
        ).pack(fill="x", padx=12)
        if item.summary:
            ctk.CTkLabel(
                row,
                text=item.summary,
                font=ctk.CTkFont(size=12),
                text_color="gray75",
                anchor="w",
                justify="left",
                wraplength=700,
            ).pack(fill="x", padx=12, pady=(4, 10))


def render_news_sections(frame: "ctk.CTkScrollableFrame", data: BriefingData) -> None:
    """Yalnızca haber kartları."""
    clear_content_frame(frame)
    add_section_header(frame, "Haber Özeti", "Türkiye · Dünya · Ekonomi")
    for category in ("turkey", "world", "economy"):
        add_news_card(frame, category, data.news.get(category, []))


def render_briefing(frame: "ctk.CTkScrollableFrame", data: BriefingData) -> None:
    """Sabah brifingini kartlarla çizer."""
    import customtkinter as ctk

    clear_content_frame(frame)
    add_section_header(frame, "Günaydın", f"Şehir: {data.city}")

    if data.weather:
        w = data.weather
        add_info_card(
            frame,
            f"Hava — {w.city}",
            [
                f"{w.description}  ·  {w.temperature:.0f}°C (hissedilen {w.feels_like:.0f}°C)",
                f"Nem %{w.humidity}  ·  Rüzgar {w.wind_speed:.1f} m/s",
            ],
            accent="#457b9d",
        )
    elif data.weather_error:
        add_info_card(frame, "Hava Durumu", [data.weather_error], accent="#6c757d")

    if data.rates:
        rows = format_finance_display(data.rates)
        if rows:
            add_finance_card(frame, rows)
        elif "gram_altin" not in data.rates:
            add_info_card(
                frame,
                "Finans",
                ["Gram altın verisi su an alinamiyor."],
                accent="#6c757d",
            )
    elif data.rates_error:
        add_info_card(frame, "Finans", [data.rates_error], accent="#6c757d")

    add_section_header(frame, "Gündem", "Öne çıkan haberler")
    for category in ("turkey", "world", "economy"):
        add_news_card(frame, category, data.news.get(category, []))


def render_plain_message(frame: "ctk.CTkScrollableFrame", title: str, body: str) -> None:
    """Komut sonuçları için basit kart."""
    clear_content_frame(frame)
    add_info_card(frame, title, body.split("\n"), accent="#495057")


def render_news_only(
    frame: "ctk.CTkScrollableFrame", category: str, items: list["NewsItem"]
) -> None:
    clear_content_frame(frame)
    add_news_card(frame, category, items)


def render_finance(frame: "ctk.CTkScrollableFrame", rates: dict[str, "RateInfo"]) -> None:
    clear_content_frame(frame)
    add_section_header(frame, "Güncel Kurlar")
    add_finance_card(frame, format_finance_display(rates))


def render_weather(frame: "ctk.CTkScrollableFrame", info: "WeatherInfo") -> None:
    clear_content_frame(frame)
    w = info
    add_info_card(
        frame,
        f"Hava — {w.city}",
        [
            f"{w.description}",
            f"Sıcaklık {w.temperature:.1f}°C  ·  Hissedilen {w.feels_like:.1f}°C",
            f"Nem %{w.humidity}  ·  Rüzgar {w.wind_speed:.1f} m/s",
        ],
        accent="#457b9d",
    )
