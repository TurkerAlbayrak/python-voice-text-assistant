"""
Yazılı ve sesli komut ayrıştırma / yönlendirme.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

import speech_recognition as sr

from finance import FinanceError, format_rates_summary, get_all_rates, get_rate
from news import (
    NewsError,
    fetch_all_briefing,
    fetch_category,
    format_briefing_news,
    format_briefing_news_speech,
    format_category_block,
)
from ui_display import BriefingData, format_category_speech
from utils import FUTURE_FEATURES, AssistantError, load_config, normalize_text
from voice import speak
from weather import WeatherError, get_weather, parse_weather_query

logger = logging.getLogger("assistant.commands")

RecognizerFactory = Callable[[], sr.Recognizer]


@dataclass
class CommandResult:
    text: str
    speech: str = ""
    speak_aloud: bool = True
    briefing: Optional[BriefingData] = None
    speech_parts: list[str] = field(default_factory=list)

    @property
    def speech_text(self) -> str:
        if self.speech.strip():
            return self.speech.strip()
        if self.speech_parts:
            return ". ".join(self.speech_parts)
        return self.text


class CommandHandler:
    """Komutları ilgili modüllere yönlendirir."""

    EXIT_ALIASES = {"çıkış", "cikis", "exit", "quit", "kapat"}

    def __init__(self, recognizer_factory: Optional[RecognizerFactory] = None) -> None:
        self._recognizer_factory = recognizer_factory or sr.Recognizer

    def handle(self, raw_command: str, *, speak_output: bool = True) -> Optional[CommandResult]:
        """
        Komutu işler. Çıkış komutunda None döner.
        """
        command = normalize_text(raw_command)
        if not command:
            return CommandResult("Boş komut girdiniz.", speak_aloud=False)

        if command in self.EXIT_ALIASES:
            return None

        try:
            result = self._dispatch(command, raw_command)
        except (AssistantError, FinanceError, NewsError, WeatherError) as exc:
            result = CommandResult(str(exc), speak_aloud=speak_output)
        except Exception as exc:
            logger.exception("Beklenmeyen komut hatası")
            result = CommandResult(f"Bir hata oluştu: {exc}", speak_aloud=speak_output)

        if speak_output and result.speak_aloud:
            if result.speech_parts:
                for part in result.speech_parts:
                    speak(part)
            else:
                speak(result.speech_text)
        return result

    def _dispatch(self, command: str, raw: str) -> CommandResult:
        future = FUTURE_FEATURES.dispatch(command)
        if future:
            return CommandResult(future, speak_aloud=True)

        if self._matches(command, ("haberleri oku", "haberler", "gundem", "gündem")):
            return self._read_news_bundle()

        if self._matches(command, ("ekonomi haberlerini oku", "ekonomi haberleri", "ekonomi")):
            if command == "ekonomi" or "ekonomi haber" in command:
                return self._read_category("economy", "Ekonomi haberleri")

        if self._matches(command, ("turkiye haberleri", "türkiye haberleri", "turkiye gundemi")):
            return self._read_category("turkey", "Türkiye gündemi")

        if self._matches(command, ("dunya haberleri", "dünya haberleri", "dunya gundemi")):
            return self._read_category("world", "Dünya gündemi")

        if self._matches(command, ("dolar kac", "dolar kaç", "dolar ne kadar", "dolar")):
            if "dolar" in command and len(command.split()) <= 3:
                info = get_rate("dolar")
                return CommandResult(info.format_display() + "\n" + info.format_speech())

        if self._matches(command, ("euro kac", "euro kaç", "euro ne kadar", "euro")):
            if "euro" in command:
                info = get_rate("euro")
                return CommandResult(info.format_display() + "\n" + info.format_speech())

        if self._matches(
            command,
            ("altin ne kadar", "altın ne kadar", "altin ne durumda", "altın ne durumda", "altin", "altın"),
        ):
            if "alt" in command:
                info = get_rate("altın")
                return CommandResult(info.format_display() + "\n" + info.format_speech())

        if self._matches(command, ("sterlin kac", "sterlin kaç", "sterlin")):
            info = get_rate("sterlin")
            return CommandResult(info.format_display() + "\n" + info.format_speech())

        if self._matches(command, ("finans", "kur", "kurlar", "doviz", "döviz")):
            summary = format_rates_summary(get_all_rates())
            return CommandResult("Güncel kurlar:\n" + summary)

        if "hava" in command or self._matches(command, ("hava durumu",)):
            info = parse_weather_query(raw)
            return CommandResult(info.format_display() + "\n" + info.format_speech())

        if command in ("yardım", "yardim", "help", "komutlar"):
            return CommandResult(self.help_text(), speak_aloud=False)

        if command in ("sesli mod", "sesli komut", "dinle"):
            heard = self.listen_voice_command()
            if not heard:
                return CommandResult("Ses algılanamadı, lütfen tekrar deneyin.")
            return self.handle(heard, speak_output=True) or CommandResult("Çıkış yapılıyor.")

        raise AssistantError(
            f"Komut anlaşılamadı: {raw}\n"
            "Yardım için 'yardım' yazın veya 'sesli mod' deyin."
        )

    @staticmethod
    def _matches(command: str, phrases: tuple[str, ...]) -> bool:
        return any(command == p or command.startswith(p) for p in phrases)

    def _read_category(self, category: str, label: str) -> CommandResult:
        items = fetch_category(category)
        block = format_category_block(category, items)
        speech = format_category_speech(category, items, count=1)
        return CommandResult(block, speech=speech)

    def _read_news_bundle(self) -> CommandResult:
        turkey = fetch_category("turkey")
        world = fetch_category("world")
        economy = fetch_category("economy")
        text = "\n".join(
            [
                format_category_block("turkey", turkey),
                format_category_block("world", world),
                format_category_block("economy", economy),
            ]
        )
        briefing = {"turkey": turkey, "world": world, "economy": economy}
        speech = format_briefing_news_speech(briefing, one_per_category=True)
        return CommandResult(text, speech=speech)

    def listen_voice_command(
        self,
        timeout: int = 6,
        phrase_limit: int = 8,
        *,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> Optional[str]:
        """Mikrofondan tek seferlik sesli komut dinler."""

        def _status(msg: str) -> None:
            if status_callback:
                status_callback(msg)
            else:
                print(msg)

        recognizer = self._recognizer_factory()
        try:
            with sr.Microphone() as source:
                _status("Dinleniyor... Konusabilirsiniz.")
                recognizer.adjust_for_ambient_noise(source, duration=0.6)
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        except sr.WaitTimeoutError:
            logger.warning("Ses dinleme zaman aşımı")
            return None
        except OSError as exc:
            logger.error("Mikrofon hatası: %s", exc)
            raise AssistantError(
                "Mikrofon bulunamadı veya erişilemiyor. "
                "PyAudio kurulu olduğundan emin olun."
            ) from exc

        try:
            text = recognizer.recognize_google(audio, language="tr-TR")
            _status(f"Algilanan: {text}")
            return text
        except sr.UnknownValueError:
            return None
        except sr.RequestError as exc:
            raise AssistantError(f"Konuşma tanıma servisi kullanılamıyor: {exc}") from exc

    @staticmethod
    def help_text() -> str:
        return """
Kullanılabilir komutlar:
  haberleri oku          - Türkiye, dünya ve ekonomi haberleri
  ekonomi haberleri      - Ekonomi haberleri
  dolar kaç / euro kaç   - Döviz kuru
  altın ne durumda       - Altın fiyatı
  hava durumu [şehir]    - Hava durumu (ör: hava durumu muğla)
  finans                 - Tüm kurlar
  sesli mod              - Mikrofon ile komut ver
  yardım                 - Bu listeyi göster
  çıkış                  - Programdan çık
"""


def build_morning_briefing() -> CommandResult:
    """Sabah bilgilendirme metnini oluşturur."""
    from finance import format_rates_speech

    try:
        config_city = load_config().get("default_city", "Muğla")
    except Exception:
        config_city = "Muğla"

    view = BriefingData(city=config_city)
    speech_parts: list[str] = ["Günaydın."]

    try:
        view.weather = get_weather(config_city)
        w = view.weather
        speech_parts.append(
            f"Bugün {w.city}'da hava {w.temperature:.0f} derece "
            f"ve {w.description.lower()}."
        )
    except Exception as exc:
        view.weather_error = str(exc)
        speech_parts.append("Hava durumu bilgisi alınamadı.")

    try:
        view.rates = get_all_rates()
        speech_parts.append(format_rates_speech(view.rates))
    except Exception as exc:
        view.rates_error = str(exc)
        speech_parts.append("Finans verileri alınamadı.")

    view.news = fetch_all_briefing()
    for cat in ("turkey", "world", "economy"):
        speech_parts.append(
            format_category_speech(cat, view.news.get(cat, []), count=1)
        )

    # Konsol için düz metin yedek
    text_lines = ["Günaydın.", ""]
    if view.weather:
        w = view.weather
        text_lines.append(
            f"Bugün {w.city}'da hava {w.temperature:.0f} derece, {w.description.lower()}."
        )
    if view.rates:
        text_lines.extend(["", "Finans:", format_rates_summary(view.rates)])
    text_lines.extend(["", format_briefing_news(view.news)])

    return CommandResult(
        text="\n".join(text_lines),
        speech="",
        speak_aloud=True,
        briefing=view,
        speech_parts=speech_parts,
    )
