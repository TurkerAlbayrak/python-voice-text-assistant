"""
OpenWeatherMap tabanlı hava durumu sorguları.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from utils import AssistantError, ConfigError, NetworkError, load_config, normalize_text, safe_request, title_case_tr

logger = logging.getLogger("assistant.weather")

OWM_URL = "https://api.openweathermap.org/data/2.5/weather"

# Türkçe komutlardan şehir çıkarmak için kalıplar
CITY_PATTERNS = [
    re.compile(r"^(.+?)\s+hava\s+durumu", re.IGNORECASE),
    re.compile(r"^(.+?)\s+hava\s+nasil", re.IGNORECASE),
    re.compile(r"^(.+?)\s+hava\s+nasıl", re.IGNORECASE),
    re.compile(r"^(.+?)\s+bugün", re.IGNORECASE),
    re.compile(r"^(.+?)\s+bugun", re.IGNORECASE),
    re.compile(r"^hava\s+durumu\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+icin\s+hava", re.IGNORECASE),
    re.compile(r"^(.+?)\s+için\s+hava", re.IGNORECASE),
]

STRIP_WORDS = {
    "hava",
    "durumu",
    "nasil",
    "nasıl",
    "bugun",
    "bugün",
    "yagmurlu",
    "yağmurlu",
    "mu",
    "mi",
    "mı",
    "mü",
    "ve",
    "icin",
    "için",
    "nedir",
    "ne",
}


@dataclass(frozen=True)
class WeatherInfo:
    city: str
    temperature: float
    feels_like: float
    humidity: int
    wind_speed: float
    description: str

    def format_display(self) -> str:
        return (
            f"{self.city} Hava Durumu\n"
            f"  Durum      : {self.description}\n"
            f"  Sıcaklık   : {self.temperature:.1f} °C\n"
            f"  Hissedilen : {self.feels_like:.1f} °C\n"
            f"  Nem        : %{self.humidity}\n"
            f"  Rüzgar     : {self.wind_speed:.1f} m/s"
        )

    def format_speech(self) -> str:
        return (
            f"{self.city} için hava {self.description}. "
            f"Sıcaklık {self.temperature:.0f} derece, "
            f"hissedilen {self.feels_like:.0f} derece. "
            f"Nem yüzde {self.humidity}. "
            f"Rüzgar hızı {self.wind_speed:.1f} metre bölü saniye."
        )


class WeatherError(AssistantError):
    """Hava durumu modülü hataları."""


def _get_api_key() -> str:
    config = load_config()
    key = (config.get("openweather_api_key") or "").strip()
    if not key or key.startswith("BURAYA_"):
        raise ConfigError(
            "OpenWeatherMap API anahtarı config.json içinde tanımlı değil. "
            "https://openweathermap.org/api adresinden ücretsiz anahtar alabilirsiniz."
        )
    return key


def _translate_description(english: str) -> str:
    """Basit İngilizce -> Türkçe hava durumu çevirisi."""
    mapping = {
        "clear sky": "açık",
        "few clouds": "az bulutlu",
        "scattered clouds": "parçalı bulutlu",
        "broken clouds": "çok bulutlu",
        "overcast clouds": "kapalı",
        "shower rain": "sağanak yağışlı",
        "rain": "yağmurlu",
        "light rain": "hafif yağmurlu",
        "moderate rain": "orta şiddetli yağmurlu",
        "heavy rain": "şiddetli yağmurlu",
        "thunderstorm": "gök gürültülü fırtınalı",
        "snow": "karlı",
        "mist": "puslu",
        "fog": "sisli",
        "haze": "dumanlı",
        "dust": "tozlu",
        "smoke": "dumanlı",
    }
    key = english.lower().strip()
    return mapping.get(key, english)


def extract_city_from_query(query: str) -> Optional[str]:
    """Komut metninden şehir adını çıkarır."""
    raw = query.strip()
    normalized = normalize_text(raw)

    for pattern in CITY_PATTERNS:
        match = pattern.match(normalized)
        if match:
            city = match.group(1).strip()
            return _clean_city(city)

    if normalized.startswith("hava durumu"):
        remainder = normalized.replace("hava durumu", "", 1).strip()
        if remainder:
            return _clean_city(remainder)

    # Sadece şehir adı verilmiş olabilir
    if len(normalized.split()) <= 2 and "hava" not in normalized:
        return _clean_city(normalized)

    return None


def _clean_city(city: str) -> str:
    words = [w for w in city.split() if w not in STRIP_WORDS]
    cleaned = " ".join(words).strip()
    return title_case_tr(cleaned) if cleaned else ""


def get_weather(city: Optional[str] = None) -> WeatherInfo:
    """Belirtilen şehir için güncel hava durumunu getirir."""
    config = load_config()
    target = city or config.get("default_city", "Istanbul")
    if not target:
        raise WeatherError("Şehir belirtilmedi.")

    api_key = _get_api_key()
    timeout = config.get("request_timeout", 15)

    try:
        response = safe_request(
            OWM_URL,
            timeout=timeout,
            params={
                "q": f"{target},TR",
                "appid": api_key,
                "units": "metric",
                "lang": "tr",
            },
        )
    except NetworkError as exc:
        raise WeatherError(f"Hava durumu alınamadı: {exc}") from exc

    data = response.json()
    if str(data.get("cod")) != "200":
        message = data.get("message", "Bilinmeyen hata")
        raise WeatherError(f"Hava durumu sorgusu başarısız: {message}")

    main = data.get("main", {})
    wind = data.get("wind", {})
    weather_list = data.get("weather", [{}])
    description_en = weather_list[0].get("description", "")
    description_tr = weather_list[0].get("description", "") or _translate_description(description_en)

    resolved_city = data.get("name", target)

    return WeatherInfo(
        city=resolved_city,
        temperature=float(main.get("temp", 0)),
        feels_like=float(main.get("feels_like", 0)),
        humidity=int(main.get("humidity", 0)),
        wind_speed=float(wind.get("speed", 0)),
        description=description_tr.capitalize(),
    )


def parse_weather_query(query: str) -> WeatherInfo:
    """Komuttan şehir çıkarıp hava durumunu döndürür."""
    city = extract_city_from_query(query)
    if not city:
        config = load_config()
        city = config.get("default_city", "Istanbul")
    return get_weather(city)
