#!/usr/bin/env python3
"""
Kişisel Haber ve Bilgi Asistanı — ana giriş noktası.
Varsayılan: grafik arayüz. Konsol: python main.py --cli
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from commands import CommandHandler, build_morning_briefing
from utils import ConfigError, setup_logging
from voice import shutdown, speak


def run_morning_briefing_cli(*, silent: bool = False) -> None:
    print("\n" + "=" * 60)
    print("  SABAH BİLGİLENDİRME MODU")
    print("=" * 60 + "\n")

    result = build_morning_briefing()
    print(result.text)

    if not silent:
        if result.speech_parts:
            for part in result.speech_parts:
                speak(part)
        else:
            speak(result.speech_text)


def run_interactive(handler: CommandHandler) -> None:
    print("\n" + "-" * 60)
    print("Komut modu aktif. 'yardım' yazarak komutları görebilirsiniz.")
    print("'sesli mod' yazarak mikrofon ile komut verebilirsiniz.")
    print("-" * 60 + "\n")

    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nÇıkış yapılıyor...")
            break

        if not raw:
            continue

        result = handler.handle(raw, speak_output=True)
        if result is None:
            print("Görüşmek üzere!")
            break
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kişisel haber ve bilgi asistanı (Türkçe, sesli + yazılı)."
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Grafik arayüz yerine konsol modu.",
    )
    parser.add_argument(
        "--no-briefing",
        action="store_true",
        help="Açılışta sabah bilgilendirme modunu atla.",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Sesli okumayı devre dışı bırak.",
    )
    parser.add_argument(
        "--command",
        "-c",
        type=str,
        default="",
        help="Tek komut çalıştır ve çık (ör: -c \"dolar kaç\").",
    )
    return parser.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()

    # Tek komut her modda çalışır
    if args.command:
        handler = CommandHandler()
        try:
            result = handler.handle(args.command, speak_output=not args.silent)
            if result:
                print(result.text)
            return 0
        except ConfigError as exc:
            print(f"Yapılandırma hatası: {exc}", file=sys.stderr)
            return 1
        finally:
            shutdown()

    # Grafik arayüz (varsayılan)
    if not args.cli:
        try:
            from gui import run_gui

            run_gui()
            return 0
        except SystemExit as code:
            return int(code)
        except ConfigError as exc:
            print(f"Yapılandırma hatası: {exc}", file=sys.stderr)
            return 1
        finally:
            shutdown()

    # Konsol modu
    handler = CommandHandler()
    try:
        if not args.no_briefing:
            run_morning_briefing_cli(silent=args.silent)
        run_interactive(handler)
        return 0
    except ConfigError as exc:
        print(f"\nYapılandırma hatası: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nÇıkış yapılıyor...")
        return 0
    finally:
        shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
