"""
Döviz ve altın fiyatları — TCMB, Finans API ve düne göre değişim.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Optional

from utils import BASE_DIR, AssistantError, NetworkError, load_config, safe_request

logger = logging.getLogger("assistant.finance")

TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"
FINANS_V3_URL = "https://finans.truncgil.com/v3/today.json"
FINANS_V4_URL = "https://finans.truncgil.com/v4/today.json"
GOLD_ONS_USD_URL = "https://api.metals.live/v1/spot/gold"
CACHE_PATH = BASE_DIR / "data" / "finance_cache.json"

DISPLAY_ORDER = ("usd", "eur", "gbp", "gram_altin", "ons_altin")


@dataclass(frozen=True)
class RateInfo:
    name: str
    value: float
    unit: str = "TL"
    source: str = "TCMB"
    previous_value: Optional[float] = None
    change_percent: Optional[float] = None

    def format_display(self) -> str:
        line = f"{self.name}: {self.value:,.2f} {self.unit}"
        badge = self.format_change_badge()
        return f"{line}  {badge}" if badge else line

    def format_change_badge(self) -> str:
        if self.change_percent is None:
            return ""
        pct = self.change_percent
        if abs(pct) < 0.02:
            return "degismedi"
        sign = "+" if pct > 0 else "-"
        return f"{sign} %{abs(pct):,.2f}"

    def format_change_speech(self) -> str:
        if self.change_percent is None:
            return ""
        pct = self.change_percent
        if abs(pct) < 0.02:
            return "düne göre değişmedi"
        if pct > 0:
            return f"düne göre yüzde {abs(pct):.2f} arttı"
        return f"düne göre yüzde {abs(pct):.2f} azaldı"

    def format_speech(self) -> str:
        if self.unit == "TL":
            base = f"{self.name} {self.value:,.2f} Türk Lirası"
        else:
            base = f"{self.name} {self.value:,.2f} {self.unit}"
        change = self.format_change_speech()
        return f"{base}, {change}" if change else base


class FinanceError(AssistantError):
    """Finans modülü hataları."""


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        text = str(value).strip().replace("%", "").replace(",", ".")
        return float(text)
    except (TypeError, ValueError):
        return None


def _parse_change_percent(value: Any) -> Optional[float]:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    return parsed


def _fetch_tcmb_rates() -> dict[str, float]:
    config = load_config()
    timeout = config.get("request_timeout", 15)
    response = safe_request(TCMB_URL, timeout=timeout)
    root = ET.fromstring(response.content)

    rates: dict[str, float] = {}
    for currency in root.findall("Currency"):
        code = currency.get("Kod") or currency.get("CurrencyCode") or ""
        selling = currency.findtext("ForexSelling") or currency.findtext("BanknoteSelling")
        value = _parse_float(selling)
        if code and value:
            rates[code.upper()] = value
    return rates


def _extract_selling_price(block: Any) -> Optional[float]:
    if not isinstance(block, dict):
        return _parse_float(block)
    for field in ("Selling", "satis", "Satış", "selling", "Alış", "Buying"):
        value = _parse_float(block.get(field))
        if value and value > 0:
            return value
    return None


def _parse_finans_raw(text: str) -> tuple[dict[str, float], dict[str, float]]:
    """Bozuk JSON yanıtından regex ile fiyat ve değişim çıkarır."""
    prices: dict[str, float] = {}
    changes: dict[str, float] = {}
    key_map = {
        "USD": "usd",
        "EUR": "eur",
        "GBP": "gbp",
        "GRA": "gram_altin",
        "HAS": "gram_altin",
    }
    for api_key, our_key in key_map.items():
        block = re.search(
            rf'"{api_key}"\s*:\s*\{{(.*?)}}\s*,',
            text,
            re.DOTALL,
        )
        if not block:
            continue
        fragment = block.group(1)
        selling = re.search(r'"Selling"\s*:\s*([\d.]+)', fragment)
        change = re.search(r'"Change"\s*:\s*(-?[\d.]+)', fragment)
        if selling and our_key not in prices:
            val = _parse_float(selling.group(1))
            if val and (our_key != "ons_altin" or val > 1500):
                prices[our_key] = val
        if change and our_key not in changes:
            ch = _parse_change_percent(change.group(1))
            if ch is not None:
                changes[our_key] = ch
    return prices, changes


def _fetch_truncgil_bundle() -> tuple[dict[str, float], dict[str, float]]:
    """
  Finans API: güncel fiyatlar ve düne göre değişim yüzdeleri.
  Dönüş: (fiyatlar, değişim_yüzdesi)
  """
    config = load_config()
    timeout = config.get("request_timeout", 15)
    prices: dict[str, float] = {}
    changes: dict[str, float] = {}

    key_map = {
        "USD": "usd",
        "EUR": "eur",
        "GBP": "gbp",
        "GRA": "gram_altin",
        "HAS": "gram_altin",
        "ONS": "ons_altin",
    }

    for url in (FINANS_V3_URL, FINANS_V4_URL):
        try:
            response = safe_request(url, timeout=timeout)
            raw = response.text
        except NetworkError as exc:
            logger.debug("Finans API (%s): %s", url, exc)
            continue

        data: dict[str, Any] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                data = parsed
        except ValueError:
            regex_prices, regex_changes = _parse_finans_raw(raw)
            prices.update(regex_prices)
            changes.update(regex_changes)
            logger.debug("Finans API regex ile ayrıştırıldı: %s", url)

        for api_key, our_key in key_map.items():
            if api_key not in data:
                continue
            block = data[api_key]
            if not isinstance(block, dict):
                continue
            price = _extract_selling_price(block)
            if price and our_key not in prices:
                if our_key == "ons_altin" and price < 1500:
                    continue
                prices[our_key] = price
            change = _parse_change_percent(block.get("Change"))
            if change is not None and our_key not in changes:
                changes[our_key] = change

        if "gram_altin" not in prices:
            regex_prices, regex_changes = _parse_finans_raw(raw)
            if "gram_altin" in regex_prices:
                prices["gram_altin"] = regex_prices["gram_altin"]
            if "gram_altin" in regex_changes:
                changes["gram_altin"] = regex_changes["gram_altin"]

        if prices and "gram_altin" in prices:
            break

    if "gram_altin" not in prices:
        try:
            raw = safe_request(FINANS_V4_URL, timeout=timeout).text
            extra_prices, extra_changes = _parse_finans_raw(raw)
            prices.update(extra_prices)
            changes.update(extra_changes)
        except NetworkError as exc:
            logger.debug("Gram altın ek çekimi: %s", exc)

    return prices, changes


def _fetch_ons_usd() -> Optional[float]:
    config = load_config()
    timeout = config.get("request_timeout", 15)
    try:
        metals = safe_request(GOLD_ONS_USD_URL, timeout=timeout).json()
        if isinstance(metals, list) and metals:
            return _parse_float(metals[0].get("price"))
        if isinstance(metals, dict):
            return _parse_float(metals.get("price") or metals.get("gold"))
    except NetworkError as exc:
        logger.debug("Ons altın USD: %s", exc)
    return None


def _load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        with CACHE_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Finans önbelleği okunamadı: %s", exc)
        return {}


def _save_cache(rates: dict[str, float]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": date.today().isoformat(),
        "rates": {key: round(val, 4) for key, val in rates.items()},
    }
    try:
        with CACHE_PATH.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning("Finans önbelleği yazılamadı: %s", exc)


def _change_from_cache(key: str, current: float, cached: dict[str, Any]) -> Optional[float]:
    cached_date = cached.get("date")
    if not cached_date:
        return None
    try:
        stored = date.fromisoformat(str(cached_date))
    except ValueError:
        return None
    if stored >= date.today():
        return None
    old_rates = cached.get("rates") or {}
    previous = _parse_float(old_rates.get(key))
    if not previous or previous <= 0:
        return None
    return ((current - previous) / previous) * 100.0


def _enrich_with_changes(
    rates: dict[str, RateInfo],
    api_changes: dict[str, float],
) -> dict[str, RateInfo]:
    cache = _load_cache()
    enriched: dict[str, RateInfo] = {}

    for key, info in rates.items():
        change_pct = api_changes.get(key)
        previous = None

        if change_pct is None:
            change_pct = _change_from_cache(key, info.value, cache)
            if change_pct is not None:
                previous = info.value / (1 + change_pct / 100.0)

        if change_pct is not None and previous is None and key in (cache.get("rates") or {}):
            previous = _parse_float(cache["rates"][key])

        enriched[key] = replace(
            info,
            change_percent=change_pct,
            previous_value=previous,
        )

    return enriched


def get_all_rates() -> dict[str, RateInfo]:
    """Tüm finans verilerini düne göre değişimle birlikte getirir."""
    rates: dict[str, RateInfo] = {}
    api_prices, api_changes = _fetch_truncgil_bundle()

    try:
        tcmb = _fetch_tcmb_rates()
        labels = {"USD": "Dolar", "EUR": "Euro", "GBP": "Sterlin"}
        for code, label in labels.items():
            if code in tcmb:
                rates[code.lower()] = RateInfo(name=label, value=tcmb[code], source="TCMB")
            elif code.lower() in api_prices:
                rates[code.lower()] = RateInfo(
                    name=label,
                    value=api_prices[code.lower()],
                    source="Finans API",
                )
    except (NetworkError, ET.ParseError) as exc:
        logger.error("TCMB kurları alınamadı: %s", exc)
        for key in ("usd", "eur", "gbp"):
            if key in api_prices:
                labels = {"usd": "Dolar", "eur": "Euro", "gbp": "Sterlin"}
                rates[key] = RateInfo(
                    name=labels[key],
                    value=api_prices[key],
                    source="Finans API",
                )
        if not rates:
            raise FinanceError("Döviz kurları şu an alınamıyor.") from exc

    if "gram_altin" in api_prices:
        rates["gram_altin"] = RateInfo(
            name="Gram Altın",
            value=api_prices["gram_altin"],
            source="Finans API",
        )

    if "ons_altin" in api_prices:
        rates["ons_altin"] = RateInfo(
            name="Ons Altın",
            value=api_prices["ons_altin"],
            unit="USD",
            source="Finans API",
        )
    else:
        ons = _fetch_ons_usd()
        if ons:
            rates["ons_altin"] = RateInfo(
                name="Ons Altın", value=ons, unit="USD", source="Metals API"
            )

    if not rates.get("gram_altin"):
        logger.warning("Gram altın fiyatı alınamadı.")

    if not rates:
        raise FinanceError("Finans verisi bulunamadı.")

    rates = _enrich_with_changes(rates, api_changes)
    _save_cache({key: info.value for key, info in rates.items()})
    return rates


def get_rate(query: str) -> RateInfo:
    from utils import normalize_text

    normalized = normalize_text(query)
    all_rates = get_all_rates()

    if any(k in normalized for k in ("dolar", "usd")):
        return all_rates.get("usd") or _find_by_name(all_rates, "Dolar")
    if any(k in normalized for k in ("euro", "eur")):
        return all_rates.get("eur") or _find_by_name(all_rates, "Euro")
    if any(k in normalized for k in ("sterlin", "gbp", "pound")):
        return all_rates.get("gbp") or _find_by_name(all_rates, "Sterlin")
    if any(k in normalized for k in ("altın", "altin", "gram")):
        if "gram_altin" in all_rates:
            return all_rates["gram_altin"]
        if "ons_altin" in all_rates:
            return all_rates["ons_altin"]
        raise FinanceError("Gram altın fiyatı şu an alınamıyor.")
    if "ons" in normalized:
        if "ons_altin" in all_rates:
            return all_rates["ons_altin"]
        raise FinanceError("Ons altın fiyatı şu an alınamıyor.")

    raise FinanceError(
        "Anlaşılamayan finans sorgusu. Örnek: dolar kaç, euro kaç, altın ne durumda"
    )


def _find_by_name(rates: dict[str, RateInfo], name: str) -> RateInfo:
    for info in rates.values():
        if info.name == name:
            return info
    raise FinanceError(f"{name} kuru bulunamadı.")


def format_rates_summary(rates: Optional[dict[str, RateInfo]] = None) -> str:
    rates = rates or get_all_rates()
    lines: list[str] = []
    for key in DISPLAY_ORDER:
        if key in rates:
            lines.append("  " + rates[key].format_display())
    for key, info in rates.items():
        if key not in DISPLAY_ORDER:
            lines.append("  " + info.format_display())
    return "\n".join(lines) if lines else "  Finans verisi yok."


def format_rates_speech(rates: Optional[dict[str, RateInfo]] = None) -> str:
    rates = rates or get_all_rates()
    parts: list[str] = []
    for key in ("usd", "eur", "gbp", "gram_altin"):
        if key in rates:
            parts.append(rates[key].format_speech())
    if "ons_altin" in rates:
        parts.append(rates["ons_altin"].format_speech())
    return ". ".join(parts)
