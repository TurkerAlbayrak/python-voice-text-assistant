"""
Metin okuma (TTS): Edge neural Türkçe ses + güvenilir MP3 çalma (pygame).
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from utils import load_config

logger = logging.getLogger("assistant.voice")

_engine = None
_lock = threading.Lock()
_event_loop: asyncio.AbstractEventLoop | None = None
_temp_dir = Path(tempfile.gettempdir()) / "assistant_tts"
_temp_dir.mkdir(exist_ok=True)

DEFAULT_EDGE_VOICE = "tr-TR-EmelNeural"
CHUNK_SIZE = 2500


def _voice_config() -> dict:
    return load_config().get("voice", {})


def _edge_installed() -> bool:
    return importlib.util.find_spec("edge_tts") is not None


def _get_event_loop() -> asyncio.AbstractEventLoop:
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
    return _event_loop


def _chunk_text(text: str, max_len: int = CHUNK_SIZE) -> list[str]:
    text = " ".join(text.split()).strip()
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current = ""
    for sentence in text.split(". "):
        part = sentence.strip()
        if not part:
            continue
        if not part.endswith("."):
            part += "."
        candidate = f"{current} {part}".strip() if current else part
        if len(candidate) <= max_len:
            current = candidate
        else:
            if current:
                chunks.append(current)
            while len(part) > max_len:
                chunks.append(part[:max_len])
                part = part[max_len:]
            current = part
    if current:
        chunks.append(current)
    return chunks or [text[:max_len]]


def _play_mp3_pygame(path: Path, volume: float) -> None:
    import pygame

    if not pygame.mixer.get_init():
        pygame.mixer.init()
    pygame.mixer.music.load(str(path))
    pygame.mixer.music.set_volume(volume)
    pygame.mixer.music.play()
    clock = pygame.time.Clock()
    while pygame.mixer.music.get_busy():
        clock.tick(10)


def _play_mp3_wmp(path: Path) -> None:
    """Windows Media Player COM — pygame yoksa yedek."""
    path_str = str(path.resolve()).replace("\\", "\\\\")
    ps = f"""
$wmp = New-Object -ComObject WMPlayer.OCX
$wmp.URL = '{path_str}'
$wmp.controls.play()
while ($wmp.playState -ne 1) {{
    Start-Sleep -Milliseconds 150
}}
$wmp.close()
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "bilinmeyen hata").strip()
        raise RuntimeError(f"WMP çalma hatası: {err}")


def _play_mp3(path: Path) -> None:
    if not path.exists():
        raise OSError(f"Ses dosyası yok: {path}")
    size = path.stat().st_size
    if size < 128:
        raise OSError(f"Ses dosyası boş veya hatalı ({size} bayt): {path}")

    volume = max(0.0, min(1.0, float(_voice_config().get("volume", 1.0))))
    errors: list[str] = []

    try:
        _play_mp3_pygame(path, volume)
        return
    except ImportError:
        errors.append("pygame kurulu değil (pip install pygame)")
    except Exception as exc:
        errors.append(f"pygame: {exc}")

    try:
        _play_mp3_wmp(path)
        return
    except Exception as exc:
        errors.append(f"WMP: {exc}")

    raise RuntimeError("Ses çalınamadı. " + " | ".join(errors))


async def _edge_save(text: str, voice: str, rate: str, out_path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out_path))


def _edge_save_sync(text: str, voice: str, rate: str, out_path: Path) -> None:
    loop = _get_event_loop()
    loop.run_until_complete(_edge_save(text, voice, rate, out_path))


def _speak_edge(text: str) -> bool:
    if not _edge_installed():
        logger.warning("edge-tts bu Python ortamında yok. Aktif venv ile: pip install edge-tts")
        return False

    cfg = _voice_config()
    voice = cfg.get("voice_name") or cfg.get("edge_voice") or DEFAULT_EDGE_VOICE
    rate = str(cfg.get("edge_rate", "+0%"))
    if not rate.startswith(("+", "-")):
        rate = "+0%"

    chunks = _chunk_text(text)
    total = len(chunks)
    print(f"\n[SES] Sesli okuma basliyor ({total} parca, ses: {voice})...")

    try:
        for index, chunk in enumerate(chunks, start=1):
            out_file = _temp_dir / f"speech_{index}_{int(time.time())}.mp3"
            print(f"   Parca {index}/{total} hazirlaniyor...", end="\r", flush=True)
            _edge_save_sync(chunk, voice, rate, out_file)
            print(f"   Parca {index}/{total} okunuyor...   ", flush=True)
            _play_mp3(out_file)
            try:
                out_file.unlink(missing_ok=True)
            except OSError:
                pass
        print("[SES] Sesli okuma tamamlandi.\n")
        logger.info("Edge TTS tamamlandı: %s", voice)
        return True
    except Exception as exc:
        print(f"\n[SES HATA] {exc}\n")
        logger.warning("Edge TTS başarısız: %s", exc, exc_info=True)
        return False


def _select_turkish_voice_pyttsx3(engine) -> None:
    voices = engine.getProperty("voices")
    if not voices:
        return
    for voice in voices:
        name = (voice.name or "").lower()
        lang_blob = " ".join(str(v) for v in (voice.languages or [])).lower()
        vid = (voice.id or "").lower()
        if "tr-tr" in lang_blob or "turkish" in name or "tolga" in name or "tur_" in vid:
            engine.setProperty("voice", voice.id)
            logger.info("pyttsx3 ses: %s", voice.name)
            return
    logger.warning("Türkçe pyttsx3 sesi yok; Edge TTS önerilir.")


def _get_pyttsx3_engine():
    global _engine
    if _engine is None:
        import pyttsx3

        _engine = pyttsx3.init()
        cfg = _voice_config()
        _engine.setProperty("rate", cfg.get("rate", 165))
        _engine.setProperty("volume", max(0.0, min(1.0, float(cfg.get("volume", 1.0)))))
        _select_turkish_voice_pyttsx3(_engine)
    return _engine


def _speak_pyttsx3(text: str) -> None:
    engine = _get_pyttsx3_engine()
    engine.say(text)
    engine.runAndWait()


def speak(text: str, *, block: bool = True) -> None:
    """Metni sesli okur."""
    if not text or not text.strip():
        return

    def _run() -> None:
        with _lock:
            engine = str(_voice_config().get("engine", "edge")).lower()
            if engine == "edge":
                if _speak_edge(text):
                    return
                logger.info("Edge başarısız; pyttsx3 deneniyor...")
            try:
                print("[SES] pyttsx3 ile okunuyor...")
                _speak_pyttsx3(text)
            except Exception as exc:
                print(f"[SES HATA] Ses cikmadi: {exc}")
                logger.error("Sesli okuma hatası: %s", exc)

    if block:
        _run()
    else:
        threading.Thread(target=_run, daemon=True).start()


def shutdown() -> None:
    global _engine, _event_loop
    if _engine is not None:
        try:
            _engine.stop()
        except Exception:
            pass
        _engine = None
    if _event_loop is not None and not _event_loop.is_closed():
        _event_loop.close()
        _event_loop = None
