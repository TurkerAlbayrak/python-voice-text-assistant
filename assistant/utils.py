"""
Ortak yardımcı fonksiyonlar, yapılandırma ve genişletilebilirlik altyapısı.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Optional

import requests

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
DATA_DIR = BASE_DIR / "data"

logger = logging.getLogger("assistant")


class AssistantError(Exception):
    """Uygulama genelinde kullanılan temel hata sınıfı."""


class ConfigError(AssistantError):
    """Yapılandırma dosyası ile ilgili hatalar."""


class NetworkError(AssistantError):
    """Ağ istekleri sırasında oluşan hatalar."""


def setup_logging(level: int = logging.INFO) -> None:
    """Konsol günlüğünü yapılandırır."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # pyttsx3 / comtypes gürültüsünü azalt
    for noisy in ("comtypes", "comtypes.client", "comtypes.gen"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def load_config(path: Optional[Path] = None) -> dict[str, Any]:
    """config.json dosyasını okur ve sözlük olarak döndürür."""
    config_file = path or CONFIG_PATH
    if not config_file.exists():
        raise ConfigError(f"Yapılandırma dosyası bulunamadı: {config_file}")

    try:
        with config_file.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config.json geçersiz JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("config.json kök öğe bir nesne olmalıdır.")

    return data


def normalize_text(text: str) -> str:
    """Komut eşleştirmesi için metni küçük harfe ve sade forma çevirir."""
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text


def title_case_tr(text: str) -> str:
    """Şehir adları için basit başlık biçimi."""
    return " ".join(part.capitalize() for part in text.split())


def safe_request(
    url: str,
    *,
    timeout: float = 15,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
) -> requests.Response:
    """HTTP isteği yapar; hataları NetworkError olarak yükseltir."""
    default_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PersonalAssistant/1.0)",
        "Accept": "application/json, application/xml, text/xml, */*",
    }
    if headers:
        default_headers.update(headers)

    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers=default_headers,
            params=params,
        )
        response.raise_for_status()
        return response
    except requests.Timeout as exc:
        raise NetworkError(f"İstek zaman aşımına uğradı: {url}") from exc
    except requests.RequestException as exc:
        raise NetworkError(f"İstek başarısız ({url}): {exc}") from exc


class FeatureRegistry:
    """
    Gelecekte eklenecek modüller için komut kayıt altyapısı.

    Örnek kullanım:
        registry = FeatureRegistry()
        registry.register("kripto", crypto_handler, aliases=["bitcoin"])
    """

    def __init__(self) -> None:
        self._commands: dict[str, Callable[[str], str]] = {}
        self._aliases: dict[str, str] = {}

    def register(
        self,
        name: str,
        handler: Callable[[str], str],
        *,
        aliases: Optional[list[str]] = None,
    ) -> None:
        key = normalize_text(name)
        self._commands[key] = handler
        for alias in aliases or []:
            self._aliases[normalize_text(alias)] = key

    def dispatch(self, command: str) -> Optional[str]:
        normalized = normalize_text(command)
        if normalized in self._commands:
            return self._commands[normalized](command)
        if normalized in self._aliases:
            return self._commands[self._aliases[normalized]](command)
        return None

    def list_commands(self) -> list[str]:
        return sorted(set(self._commands) | set(self._aliases))


# Gelecek özellikler için hazır kayıt defteri
FUTURE_FEATURES = FeatureRegistry()


def register_future_feature(
    name: str,
    handler: Callable[[str], str],
    *,
    aliases: Optional[list[str]] = None,
) -> None:
    """Yeni modül eklerken kullanılacak yardımcı."""
    FUTURE_FEATURES.register(name, handler, aliases=aliases)


def placeholder_handler(feature_name: str) -> Callable[[str], str]:
    """Henüz uygulanmamış özellikler için geçici yanıt."""

    def _handler(_: str) -> str:
        return f"{feature_name} özelliği henüz etkin değil; yakında eklenecek."

    return _handler


# Gelecek modüller için yer tutucular
for _feature in (
    "kripto",
    "borsa",
    "takvim",
    "yapilacaklar",
    "eposta",
    "discord",
    "metar",
):
    register_future_feature(_feature, placeholder_handler(_feature.title()))
