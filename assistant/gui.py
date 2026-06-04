"""
Kişisel Asistan — grafik arayüz (CustomTkinter).
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None  # type: ignore

from commands import CommandHandler, build_morning_briefing
from finance import format_rates_speech, get_all_rates
from news import fetch_category
from ui_display import (
    BriefingData,
    format_category_speech,
    render_briefing,
    render_finance,
    render_news_only,
    render_news_sections,
    render_plain_message,
    render_weather,
)
from utils import ConfigError, load_config
from voice import shutdown, speak
from weather import get_weather


def _ui_config() -> dict:
    try:
        return load_config().get("ui", {})
    except ConfigError:
        return {}


class AssistantGUI:
    """Ana pencere ve etkileşimler."""

    def __init__(self) -> None:
        if ctk is None:
            raise ImportError(
                "customtkinter kurulu degil. Calistirin: pip install customtkinter"
            )

        ui = _ui_config()
        theme = ui.get("theme", "dark")
        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme(ui.get("color_theme", "blue"))

        self.root = ctk.CTk()
        self.root.title("Kişisel Haber ve Bilgi Asistanı")
        self.root.geometry("1180x760")
        self.root.minsize(960, 620)

        self.handler = CommandHandler()
        self.auto_speak = tk.BooleanVar(value=ui.get("auto_speak", True))
        self._busy = False
        self._speech_lock = threading.Lock()

        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if ui.get("auto_briefing_on_start", True):
            self.root.after(400, self.run_morning_briefing)

    def _build_layout(self) -> None:
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # Sol menü
        sidebar = ctk.CTkFrame(self.root, width=220, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(12, weight=1)

        ctk.CTkLabel(
            sidebar,
            text="Asistan",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(20, 4), sticky="w")

        try:
            city = load_config().get("default_city", "—")
        except ConfigError:
            city = "—"
        ctk.CTkLabel(sidebar, text=f"Sehir: {city}", text_color="gray70").grid(
            row=1, column=0, padx=16, pady=(0, 16), sticky="w"
        )

        buttons: list[tuple[str, Callable[[], None]]] = [
            ("Sabah Brifingi", self.run_morning_briefing),
            ("Hava Durumu", self.show_weather),
            ("Finans / Kurlar", self.show_finance),
            ("Turkiye Haberleri", lambda: self.show_news("turkey")),
            ("Dunya Haberleri", lambda: self.show_news("world")),
            ("Ekonomi Haberleri", lambda: self.show_news("economy")),
            ("Tum Haberler", self.show_all_news),
            ("Sesli Komut", self.run_voice_command),
        ]
        for row, (label, cmd) in enumerate(buttons, start=2):
            ctk.CTkButton(
                sidebar,
                text=label,
                command=cmd,
                anchor="w",
                height=36,
            ).grid(row=row, column=0, padx=12, pady=4, sticky="ew")

        ctk.CTkCheckBox(
            sidebar,
            text="Otomatik sesli oku",
            variable=self.auto_speak,
        ).grid(row=11, column=0, padx=16, pady=12, sticky="w")

        ctk.CTkButton(
            sidebar,
            text="Yeniden Oku",
            fg_color="#2d6a4f",
            hover_color="#1b4332",
            command=self._replay_speech,
        ).grid(row=12, column=0, padx=12, pady=4, sticky="ew")

        ctk.CTkButton(
            sidebar,
            text="Konsol Modu",
            fg_color="transparent",
            border_width=1,
            command=self._show_cli_hint,
        ).grid(row=13, column=0, padx=12, pady=(4, 16), sticky="ew")

        # Ana alan
        main = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(0, 8), pady=8)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Guncel Bilgiler",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self.status_label = ctk.CTkLabel(
            header, text="Hazir", text_color="gray60"
        )
        self.status_label.grid(row=0, column=1, sticky="e")

        self.content = ctk.CTkScrollableFrame(main, label_text="")
        self.content.grid(row=1, column=0, sticky="nsew")
        self._last_speech = ""

        # Komut satırı
        cmd_frame = ctk.CTkFrame(main, fg_color="transparent")
        cmd_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        cmd_frame.grid_columnconfigure(0, weight=1)

        self.cmd_entry = ctk.CTkEntry(
            cmd_frame,
            placeholder_text='Komut yazin: "dolar kac", "hava durumu ankara", "ekonomi haberleri"...',
            height=40,
        )
        self.cmd_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.cmd_entry.bind("<Return>", lambda _: self.run_command())

        ctk.CTkButton(
            cmd_frame, text="Gonder", width=90, height=40, command=self.run_command
        ).grid(row=0, column=1)

        quick = ctk.CTkFrame(main, fg_color="transparent")
        quick.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for text, command in (
            ("Dolar", lambda: self._quick_command("dolar kac")),
            ("Euro", lambda: self._quick_command("euro kac")),
            ("Altin", lambda: self._quick_command("altin ne durumda")),
            ("Yardim", lambda: self._quick_command("yardim")),
        ):
            ctk.CTkButton(
                quick,
                text=text,
                width=80,
                height=28,
                fg_color="#343a40",
                hover_color="#495057",
                command=command,
            ).pack(side="left", padx=(0, 6))

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.cmd_entry.configure(state=state)

    def _run_bg(
        self,
        task: Callable[[], None],
        status: str = "Yukleniyor...",
    ) -> None:
        if self._busy:
            messagebox.showinfo("Bekleyin", "Bir islem devam ediyor.")
            return

        self._set_busy(True)
        self._set_status(status)

        def worker() -> None:
            try:
                task()
            except Exception as exc:
                self.root.after(
                    0,
                    lambda: messagebox.showerror("Hata", str(exc)),
                )
            finally:
                self.root.after(0, lambda: (self._set_busy(False), self._set_status("Hazir")))

        threading.Thread(target=worker, daemon=True).start()

    def _maybe_speak(self, text: str = "", *, parts: list[str] | None = None) -> None:
        segments = [p for p in (parts or []) if p and p.strip()]
        if not segments and text and text.strip():
            segments = [text.strip()]
        if not segments or not self.auto_speak.get():
            return
        self._last_speech = ". ".join(segments)

        def _speak() -> None:
            with self._speech_lock:
                self.root.after(0, lambda: self._set_status("Sesli okunuyor..."))
                try:
                    for segment in segments:
                        speak(segment)
                finally:
                    self.root.after(0, lambda: self._set_status("Hazir"))

        threading.Thread(target=_speak, daemon=True).start()

    def _replay_speech(self) -> None:
        if self._last_speech:
            self._maybe_speak(self._last_speech)
        else:
            messagebox.showinfo("Bilgi", "Okunacak metin yok.")

    def _show_cards(
        self,
        render_fn: Callable[[], None],
        speech: str = "",
        *,
        speech_parts: list[str] | None = None,
    ) -> None:
        self.root.after(0, render_fn)
        if speech_parts:
            self._maybe_speak(parts=speech_parts)
        elif speech:
            self._maybe_speak(speech)

    def run_morning_briefing(self) -> None:
        def task() -> None:
            result = build_morning_briefing()
            if result.briefing:
                self._show_cards(
                    lambda: render_briefing(self.content, result.briefing),
                    speech_parts=result.speech_parts or None,
                    speech=result.speech_text if not result.speech_parts else "",
                )
            else:
                self._show_cards(
                    lambda: render_plain_message(
                        self.content, "Sabah Brifingi", result.text
                    ),
                    speech_parts=result.speech_parts or None,
                    speech=result.speech_text,
                )
            self._last_speech = result.speech_text

        self._run_bg(task, "Sabah brifingi hazirlaniyor...")

    def show_weather(self) -> None:
        def task() -> None:
            city = load_config().get("default_city", "Istanbul")
            info = get_weather(city)
            self._show_cards(
                lambda: render_weather(self.content, info),
                info.format_speech(),
            )

        self._run_bg(task, "Hava durumu aliniyor...")

    def show_finance(self) -> None:
        def task() -> None:
            rates = get_all_rates()
            self._show_cards(
                lambda: render_finance(self.content, rates),
                format_rates_speech(rates),
            )

        self._run_bg(task, "Finans verileri aliniyor...")

    def show_news(self, category: str) -> None:
        def task() -> None:
            items = fetch_category(category)
            speech = format_category_speech(category, items, count=1)
            self._show_cards(
                lambda: render_news_only(self.content, category, items),
                speech,
            )

        self._run_bg(task, "Haberler yukleniyor...")

    def show_all_news(self) -> None:
        def task() -> None:
            briefing: dict = {}
            for cat in ("turkey", "world", "economy"):
                briefing[cat] = fetch_category(cat)

            data = BriefingData(
                city=load_config().get("default_city", ""),
                news=briefing,
            )
            parts = [
                format_category_speech(cat, briefing[cat], count=1)
                for cat in ("turkey", "world", "economy")
            ]
            self._show_cards(
                lambda: render_news_sections(self.content, data),
                speech_parts=parts,
            )

        self._run_bg(task, "Tum haberler yukleniyor...")

    def _quick_command(self, cmd: str) -> None:
        self.cmd_entry.delete(0, "end")
        self.cmd_entry.insert(0, cmd)
        self.run_command()

    def run_command(self) -> None:
        raw = self.cmd_entry.get().strip()
        if not raw:
            return

        def task() -> None:
            result = self.handler.handle(raw, speak_output=False)
            if result is None:
                self.root.after(0, self._on_close)
                return
            self._show_cards(
                lambda: render_plain_message(self.content, "Komut", result.text),
                result.speech_text,
            )

        self._run_bg(task, f"Komut: {raw[:30]}...")

    def run_voice_command(self) -> None:
        def task() -> None:
            def status(msg: str) -> None:
                self.root.after(0, lambda: self._set_status(msg))

            heard = self.handler.listen_voice_command(status_callback=status)
            if not heard:
                self.root.after(
                    0,
                    lambda: messagebox.showwarning(
                        "Ses", "Komut anlasilamadi. Tekrar deneyin."
                    ),
                )
                return
            result = self.handler.handle(heard, speak_output=False)
            if result:
                self._show_cards(
                    lambda: render_plain_message(
                        self.content, "Sonuc", result.text
                    ),
                    result.speech_text,
                )

        self._run_bg(task, "Mikrofon acik...")

    def _show_cli_hint(self) -> None:
        messagebox.showinfo(
            "Konsol modu",
            "Terminalden calistirmak icin:\npython main.py --cli",
        )

    def _on_close(self) -> None:
        shutdown()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_gui() -> None:
    """GUI uygulamasini baslatir."""
    try:
        app = AssistantGUI()
    except ConfigError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Yapilandirma", str(exc))
        root.destroy()
        raise SystemExit(1) from exc
    except ImportError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Eksik paket",
            f"{exc}\n\npip install customtkinter",
        )
        root.destroy()
        raise SystemExit(1) from exc
    app.run()
