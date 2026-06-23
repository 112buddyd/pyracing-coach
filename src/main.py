"""pyracing-coach entry point."""
import os
import sys
import time
import shutil
import threading
import customtkinter as ctk
from tkinter import filedialog

from config import Config
from iracing_reader import IRacingReader
from ibt_reader import read_ibt, find_ibt_files, ibt_session_info, DEFAULT_IBT_DIR
from reference_lap import load_reference
from coach import Coach
from audio import AudioCoach
from session_log import SessionLog
from report import generate as generate_report, open_report
from settings_ui import SettingsDialog


APP_NAME    = "pyracing-coach"
CONFIG_DIR  = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.toml")
_BUNDLED_CONFIG = os.path.join(
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.dirname(__file__)),
    "config.toml",
)


def _ensure_config() -> str:
    """Copy bundled default config to APPDATA on first run."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH) and os.path.exists(_BUNDLED_CONFIG):
        shutil.copy(_BUNDLED_CONFIG, CONFIG_PATH)
    return CONFIG_PATH


class App(ctk.CTk):
    """Main application window."""

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.title("pyracing-coach")
        self.geometry("460x400")
        self.resizable(False, False)

        self._status   = ctk.StringVar(value="Waiting for iRacing…")
        self._ref_info = ctk.StringVar(value="No reference lap loaded")
        self._coaching = ctk.BooleanVar(value=False)

        ctk.CTkLabel(self, textvariable=self._status, font=("", 14)).pack(pady=(20, 4))
        ctk.CTkLabel(self, text="Reference lap:", font=("", 11)).pack()
        ctk.CTkLabel(self, textvariable=self._ref_info, font=("", 11),
                     text_color="gray").pack(pady=(0, 10))

        mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        mode_frame.pack(pady=(0, 8))
        ctk.CTkLabel(mode_frame, text="Mode:", font=("", 11)).pack(side="left", padx=(0, 6))
        self._mode_var = ctk.StringVar(value=cfg.get("critique.mode", "both"))
        for m in ("learning", "critique", "both"):
            ctk.CTkRadioButton(mode_frame, text=m, variable=self._mode_var,
                               value=m, font=("", 11)).pack(side="left", padx=4)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=4)
        self._toggle_btn = ctk.CTkButton(btn_frame, text="Start Coaching",
                                         command=self._toggle, width=150)
        self._toggle_btn.pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Load .ibt…", command=self._pick_ibt,
                      width=150).pack(side="left", padx=6)

        ctk.CTkButton(self, text="Auto-load from iRacing folder",
                      command=self._auto_load_ibt, width=310,
                      fg_color="gray").pack(pady=4)
        ctk.CTkButton(self, text="Generate Session Report…",
                      command=self._generate_report, width=310,
                      fg_color="#2e7d32").pack(pady=4)
        ctk.CTkButton(self, text="Options…",
                      command=self._open_settings, width=310,
                      fg_color="#555").pack(pady=4)

        self._ir:    IRacingReader = IRacingReader()
        self._coach: Coach | None  = None
        self._audio: AudioCoach    = AudioCoach(
            rate=cfg.get("audio.rate", 175),
            volume=cfg.get("audio.volume", 1.0),
            voice_name=cfg.get("audio.voice_name", ""),
            voice_index=cfg.get("audio.voice_index", 0),
        )

        threading.Thread(target=self._poll_loop, daemon=True).start()

    # ── UI callbacks ──────────────────────────────────────────────────────────

    def _toggle(self) -> None:
        if not self._coaching.get():
            if self._coach:
                self._coaching.set(True)
                self._toggle_btn.configure(text="Stop Coaching")
        else:
            self._coaching.set(False)
            self._toggle_btn.configure(text="Start Coaching")

    def _pick_ibt(self) -> None:
        path = filedialog.askopenfilename(
            title="Select reference lap (.ibt)",
            initialdir=DEFAULT_IBT_DIR if os.path.isdir(DEFAULT_IBT_DIR) else os.path.expanduser("~"),
            filetypes=[("iRacing telemetry", "*.ibt")],
        )
        if path:
            threading.Thread(target=self._load_ibt, args=(path,), daemon=True).start()

    def _auto_load_ibt(self) -> None:
        files = find_ibt_files()
        if not files:
            self._ref_info.set("No .ibt files found in iRacing telemetry folder")
            return
        threading.Thread(target=self._load_ibt, args=(files[0],), daemon=True).start()

    def _generate_report(self) -> None:
        log_dir = os.path.join(CONFIG_DIR, self.cfg.get("app.log_dir", "session_logs"))
        if not os.path.isdir(log_dir):
            self._ref_info.set("No session logs found")
            return
        logs = sorted(
            [os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith(".json")],
            key=os.path.getmtime, reverse=True,
        )
        if not logs:
            self._ref_info.set("No session logs found")
            return
        fmt = self.cfg.get("report.format", "html")
        path = generate_report(logs[0], output_format=fmt)
        open_report(path)
        self._ref_info.set(f"Report: {os.path.basename(path)}")

    def _open_settings(self) -> None:
        SettingsDialog(self, self.cfg)

    # ── Poll loop ─────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        interval: float = self.cfg.get("app.poll_interval", 0.05)

        while True:
            time.sleep(interval)
            if not self._ir.is_connected:
                if not self._ir.connect():
                    self._status.set("Waiting for iRacing…")
                    continue
                session = self._ir.get_session_info()
                self._status.set(
                    f"🏎  {session.get('car_name', '?')}  |  {session.get('track_name', '?')}"
                )

            if self._coaching.get() and self._coach:
                telem = self._ir.get_telemetry()
                self._coach.tick(telem)

    def _load_ibt(self, path: str) -> None:
        try:
            self._ref_info.set(f"Loading {os.path.basename(path)}…")
            self._coach = None
            self._coaching.set(False)
            self._toggle_btn.configure(text="Start Coaching")

            info    = ibt_session_info(path)
            samples = read_ibt(path)
            if not samples:
                self._ref_info.set("No complete lap found in selected .ibt file")
                return

            c = self.cfg.section("coaching")
            ref = load_reference(samples, c["brake_threshold"], c["brake_min_samples"],
                                 c.get("lift_threshold", 0.5), c.get("lift_min_samples", 8))

            ref_lap_time: float | None = None
            valid_times = [t for t in ref.get("time", []) if t is not None]
            if valid_times:
                ref_lap_time = max(valid_times)

            coach_cfg: dict = {
                **c,
                "alerts":  self.cfg.section("alerts"),
                "mode":    self._mode_var.get(),
                "assumed_track_length_m":   info.get("track_length_m", 3000),
                "reference_lap_time_s":     ref_lap_time,
                **{f"critique_{k}": v for k, v in self.cfg.section("critique").items()},
                **{f"smoothness_{k}": v for k, v in self.cfg.section("smoothness").items()},
                "delta_enabled":            self.cfg.get("delta.enabled", True),
                "delta_interval_s":         self.cfg.get("delta.interval_s", 20.0),
                "sectors_enabled":          self.cfg.get("sectors.enabled", True),
                "sector_splits":            self.cfg.get("sectors.splits", [0.33, 0.66]),
                "ous_enabled":              self.cfg.get("oversteer_understeer.enabled", True),
                "ous_threshold":            self.cfg.get("oversteer_understeer.threshold", 0.3),
                "ous_wheelbase_m":          self.cfg.get("oversteer_understeer.wheelbase_m", 2.7),
                "ous_cooldown_pct":         self.cfg.get("oversteer_understeer.cooldown_pct", 0.05),
                "oversteer_cue":            self.cfg.get("oversteer_understeer.oversteer_cue", "oversteer"),
                "understeer_cue":           self.cfg.get("oversteer_understeer.understeer_cue", "understeer"),
                "temps":                    self.cfg.section("temps"),
                "instinct":                 self.cfg.section("instinct"),
            }

            log: SessionLog | None = None
            if self.cfg.get("app.session_log_enabled", True):
                log = SessionLog(
                    os.path.join(CONFIG_DIR, self.cfg.get("app.log_dir", "session_logs")),
                    info.get("car_name", "unknown"), info.get("track_name", "unknown"),
                )
                log.start_lap(1)

            self._coach = Coach(ref, self._audio, coach_cfg, log=log)
            self._coach.set_track_length(info.get("track_length_m", 3000))

            label = (f"{info.get('car_name', '?')} @ {info.get('track_name', '?')} "
                     f"— {len(ref['zones'])} zones")
            if ref_lap_time:
                m, s = divmod(ref_lap_time, 60)
                label += f"  ({int(m)}:{s:05.2f})"
            self._ref_info.set(label)
        except Exception as e:
            self._ref_info.set(f"Error: {e}")


def main() -> None:
    _ensure_config()
    cfg = Config(CONFIG_PATH)
    ctk.set_appearance_mode("dark")
    App(cfg).mainloop()


if __name__ == "__main__":
    main()
