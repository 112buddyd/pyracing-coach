"""Settings UI — two-pane layout: category list on left, fields on right."""
import pyttsx3
import customtkinter as ctk
from config import Config, SCHEMA, Field


def _get_voices() -> list[str]:
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        names = [v.name for v in voices] if voices else []
        engine.stop()
        return names
    except Exception:
        return []


class SettingsDialog(ctk.CTkToplevel):
    """Two-pane settings: category list on left, scrollable fields on right."""

    def __init__(self, parent: ctk.CTk, cfg: Config) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.title("Options")
        self.geometry("740x520")
        self.resizable(True, True)
        self.grab_set()

        self._voice_names: list[str] = _get_voices()

        # All widgets across all categories, keyed by field.key
        self._all_vars: dict[str, tuple[Field, object]] = {}

        # Group fields by tab
        self._tabs: dict[str, list[Field]] = {}
        for field in SCHEMA:
            self._tabs.setdefault(field.tab, []).append(field)

        # Main horizontal split
        self._main = ctk.CTkFrame(self)
        self._main.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self._main.grid_columnconfigure(1, weight=1)
        self._main.grid_rowconfigure(0, weight=1)

        # Left: category list
        cat_frame = ctk.CTkScrollableFrame(self._main, width=160)
        cat_frame.grid(row=0, column=0, sticky="ns", padx=(0, 8))

        self._cat_buttons: dict[str, ctk.CTkButton] = {}
        for cat_name in self._tabs:
            btn = ctk.CTkButton(
                cat_frame, text=cat_name, width=150, height=30,
                anchor="w", fg_color="transparent", text_color="gray80",
                command=lambda n=cat_name: self._select_category(n),
            )
            btn.pack(pady=2)
            self._cat_buttons[cat_name] = btn

        # Right: placeholder — one scrollable frame per category, show/hide
        self._right_container = ctk.CTkFrame(self._main, fg_color="transparent")
        self._right_container.grid(row=0, column=1, sticky="nsew")

        self._panels: dict[str, ctk.CTkScrollableFrame] = {}
        self._active_cat: str = ""

        # Pre-build all panels (hidden)
        for cat_name, fields in self._tabs.items():
            panel = ctk.CTkScrollableFrame(self._right_container, fg_color="transparent")
            for field in fields:
                self._add_field(panel, field)
            self._panels[cat_name] = panel

        # Bottom save button
        ctk.CTkButton(self, text="Save", command=self._save, width=120,
                      fg_color="#2e7d32").pack(pady=8)

        # Show first
        if self._tabs:
            self._select_category(list(self._tabs.keys())[0])

    def _select_category(self, name: str) -> None:
        if name == self._active_cat:
            return

        # Hide current
        if self._active_cat and self._active_cat in self._panels:
            self._panels[self._active_cat].pack_forget()

        # Show new
        self._panels[name].pack(fill="both", expand=True)
        self._active_cat = name

        # Highlight
        for cat, btn in self._cat_buttons.items():
            if cat == name:
                btn.configure(fg_color="#1f538d", text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color="gray80")

    def _add_field(self, parent: ctk.CTkFrame, field: Field) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=4, pady=(6, 2))

        ctk.CTkLabel(frame, text=field.label, font=("", 12, "bold"),
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(frame, text=field.desc, font=("", 10), text_color="#888",
                     anchor="w", wraplength=480).pack(anchor="w", pady=(0, 4))

        current = self.cfg.get(field.key, field.default)

        if field.type == "bool":
            var = ctk.BooleanVar(value=bool(current))
            ctk.CTkCheckBox(frame, text="Enabled", variable=var).pack(anchor="w")
        elif field.type == "choice":
            choices = self._resolve_choices(field)
            var = ctk.StringVar(value=str(current) if current else (choices[0] if choices else ""))
            ctk.CTkOptionMenu(frame, values=choices, variable=var, width=260).pack(anchor="w")
        else:
            var = ctk.StringVar(value=str(current) if current is not None else "")
            ctk.CTkEntry(frame, textvariable=var, width=260).pack(anchor="w")

        self._all_vars[field.key] = (field, var)

    def _resolve_choices(self, field: Field) -> list[str]:
        if field.key == "audio.voice_name":
            return self._voice_names or ["(default)"]
        return field.choices or []

    def _save(self) -> None:
        for key, (field, var) in self._all_vars.items():
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
