"""Settings UI — auto-generated from config SCHEMA with descriptions and audio output selector."""
import pyttsx3
import customtkinter as ctk
from config import Config, SCHEMA, Field


def _get_voices() -> list[str]:
    """Return list of available system TTS voice names."""
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        names = [v.name for v in voices] if voices else []
        engine.stop()
        return names
    except Exception:
        return []


class SettingsDialog(ctk.CTkToplevel):
    """Tabbed settings dialog, auto-populated from SCHEMA with descriptions."""

    def __init__(self, parent: ctk.CTk, cfg: Config) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.title("Options")
        self.geometry("680x540")
        self.resizable(True, True)
        self.grab_set()

        self._widgets: list[tuple[Field, object]] = []
        self._voice_names: list[str] = _get_voices()

        tabview = ctk.CTkTabview(self, width=650, height=440)
        tabview.pack(padx=10, pady=(10, 4), fill="both", expand=True)

        # Group fields by tab, preserving order
        tabs: dict[str, list[Field]] = {}
        for field in SCHEMA:
            tabs.setdefault(field.tab, []).append(field)

        for tab_name, fields in tabs.items():
            tab = tabview.add(tab_name)
            scroll = ctk.CTkScrollableFrame(tab, width=630, height=400)
            scroll.pack(fill="both", expand=True)
            for i, field in enumerate(fields):
                self._add_field(scroll, i, field)

        ctk.CTkButton(self, text="Save", command=self._save, width=120,
                      fg_color="#2e7d32").pack(pady=(4, 10))

    def _add_field(self, parent: ctk.CTkFrame, row: int, field: Field) -> None:
        # Row with label + widget
        base_row = row * 2  # double rows: one for label+widget, one for description

        ctk.CTkLabel(parent, text=field.label, font=("", 12),
                     anchor="w").grid(row=base_row, column=0, sticky="w", padx=8, pady=(6, 0))

        current = self.cfg.get(field.key, field.default)

        if field.type == "bool":
            var = ctk.BooleanVar(value=bool(current))
            ctk.CTkCheckBox(parent, text="", variable=var, width=30).grid(
                row=base_row, column=1, sticky="w", padx=8, pady=(6, 0))

        elif field.type == "choice":
            choices = self._resolve_choices(field)
            var = ctk.StringVar(value=str(current) if current else (choices[0] if choices else ""))
            ctk.CTkOptionMenu(parent, values=choices, variable=var, width=220).grid(
                row=base_row, column=1, sticky="w", padx=8, pady=(6, 0))

        else:
            var = ctk.StringVar(value=str(current) if current is not None else "")
            ctk.CTkEntry(parent, textvariable=var, width=220).grid(
                row=base_row, column=1, sticky="w", padx=8, pady=(6, 0))

        # Description row
        ctk.CTkLabel(parent, text=field.desc, font=("", 10), text_color="#888",
                     anchor="w", wraplength=600).grid(
            row=base_row + 1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 4))

        self._widgets.append((field, var))

    def _resolve_choices(self, field: Field) -> list[str]:
        """Return choice list — static from schema or dynamic (e.g. voices)."""
        if field.key == "audio.voice_name":
            return self._voice_names or ["(default)"]
        return field.choices or []

    def _save(self) -> None:
        """Read all widgets, update Config, write to disk, close."""
        for field, var in self._widgets:
            raw = var.get()
            try:
                if field.type == "bool":
                    self.cfg.set(field.key, bool(raw))
                elif field.type == "int":
                    self.cfg.set(field.key, int(raw))
                elif field.type == "float":
                    self.cfg.set(field.key, float(raw))
                else:
                    self.cfg.set(field.key, str(raw))
            except (ValueError, TypeError):
                self.cfg.set(field.key, str(raw))

        self.cfg.save()
        self.destroy()
