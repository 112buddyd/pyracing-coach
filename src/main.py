"""pyracing-coach entry point."""
import os
import sys
import time
import shutil
import threading
import tomllib
import customtkinter as ctk

from iracing_reader import IRacingReader
from garage61 import Garage61Fetcher
from reference_lap import load_reference
from coach import Coach
from audio import AudioCoach
from session_log import SessionLog
from oauth import run_oauth_flow


APP_NAME   = "pyracing-coach"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.toml")
# Bundled default config sits next to the exe / script
_DEFAULT_CONFIG = os.path.join(os.path.dirname(sys.executable)
                               if getattr(sys, "frozen", False)
                               else os.path.dirname(os.path.dirname(__file__)),
                               "config.toml")


def _ensure_config() -> str:
    """Copy the default config to APPDATA on first run. Returns the config path."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH) and os.path.exists(_DEFAULT_CONFIG):
        shutil.copy(_DEFAULT_CONFIG, CONFIG_PATH)
    return CONFIG_PATH


def load_config() -> dict:
    path = _ensure_config()
    with open(path, "rb") as f:
        return tomllib.load(f)


class App(ctk.CTk):
    """Main application window.

    Manages the iRacing connection, Garage61 reference lap loading,
    and the background telemetry poll loop that drives the Coach.
    """

    def __init__(self, cfg: dict) -> None:
        super().__init__()
        self.cfg = cfg
        self.title("pyracing-coach")
        self.geometry("420x340")
        self.resizable(False, False)

        self._status   = ctk.StringVar(value="Waiting for iRacing…")
        self._ref_info = ctk.StringVar(value="—")
        self._coaching = ctk.BooleanVar(value=False)

        ctk.CTkLabel(self, textvariable=self._status, font=("", 14)).pack(pady=(20, 4))
        ctk.CTkLabel(self, text="Reference lap:", font=("", 11)).pack()
        ctk.CTkLabel(self, textvariable=self._ref_info, font=("", 11), text_color="gray").pack(pady=(0, 12))

        mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        mode_frame.pack(pady=(0, 8))
        ctk.CTkLabel(mode_frame, text="Mode:", font=("", 11)).pack(side="left", padx=(0, 6))
        self._mode_var = ctk.StringVar(value=cfg.get("critique", {}).get("mode", "both"))
        for m in ("learning", "critique", "both"):
            ctk.CTkRadioButton(mode_frame, text=m, variable=self._mode_var,
                               value=m, font=("", 11)).pack(side="left", padx=4)

        self._toggle_btn = ctk.CTkButton(self, text="Start Coaching",
                                         command=self._toggle, width=160)
        self._toggle_btn.pack(pady=4)
        ctk.CTkButton(self, text="Clear Cache", command=self._clear_cache,
                      width=160, fg_color="gray").pack(pady=4)
        ctk.CTkButton(self, text="Connect Garage61…", command=self._open_oauth_dialog,
                      width=160, fg_color="#1f538d").pack(pady=4)

        self._ir:    IRacingReader = IRacingReader()
        self._coach: Coach | None  = None

        threading.Thread(target=self._poll_loop, daemon=True).start()

    # ── UI callbacks ──────────────────────────────────────────────────────────

    def _toggle(self) -> None:
        """Start or stop coaching. Coaching requires a loaded reference lap."""
        if not self._coaching.get():
            if self._coach:
                self._coaching.set(True)
                self._toggle_btn.configure(text="Stop Coaching")
        else:
            self._coaching.set(False)
            self._toggle_btn.configure(text="Start Coaching")

    def _clear_cache(self) -> None:
        """Delete cached reference lap CSVs and reset coaching state."""
        cache = self.cfg["app"]["cache_dir"]
        if os.path.isdir(cache):
            shutil.rmtree(cache)
        self._ref_info.set("Cache cleared")
        self._coach = None
        self._coaching.set(False)
        self._toggle_btn.configure(text="Start Coaching")

    def _open_oauth_dialog(self) -> None:
        """Open the Garage61 OAuth setup dialog."""
        _OAuthDialog(self, self.cfg)

    # ── Background poll loop ──────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        """Background thread: connects to iRacing, detects session changes, drives coach ticks."""
        audio = AudioCoach(
            rate=self.cfg["audio"]["rate"],
            volume=self.cfg["audio"]["volume"],
            voice_index=self.cfg["audio"]["voice_index"],
        )
        interval:     float        = self.cfg["app"]["poll_interval"]
        last_session: tuple | None = None

        while True:
            time.sleep(interval)
            if not self._ir.is_connected:
                if not self._ir.connect():
                    self._status.set("Waiting for iRacing…")
                    last_session = None
                    self._coach  = None
                    continue

            session:     dict  = self._ir.get_session_info()
            session_key: tuple = (session.get("car_name"), session.get("track_name"),
                                  session.get("track_config"))

            if session_key != last_session:
                last_session = session_key
                self._status.set(f"🏎  {session['car_name']}  |  {session['track_name']}")
                self._ref_info.set("Loading reference lap…")
                self._coach = None
                self._coaching.set(False)
                self._toggle_btn.configure(text="Start Coaching")
                threading.Thread(target=self._load_reference,
                                 args=(session, audio), daemon=True).start()

            if self._coaching.get() and self._coach:
                telem = self._ir.get_telemetry()
                self._coach.tick(telem)

    def _load_reference(self, session: dict, audio: AudioCoach) -> None:
        """Background thread: fetch reference lap from Garage61, build Coach, update UI."""
        try:
            g61     = self.cfg["garage61"]
            fetcher = Garage61Fetcher(
                token=g61["token"],
                source=g61["source"],
                cache_dir=os.path.join(CONFIG_DIR, self.cfg["app"].get("cache_dir", "lap_cache")),
                cache_max_age_hours=g61.get("cache_max_age_hours", 24.0),
            )
            rows = fetcher.get_fastest_lap_csv(
                session["car_name"], session["track_name"], session["track_config"]
            )
            if not rows:
                self._ref_info.set("No reference lap found on Garage61")
                return

            c   = self.cfg["coaching"]
            crit = self.cfg.get("critique", {})
            smo  = self.cfg.get("smoothness", {})
            ous  = self.cfg.get("oversteer_understeer", {})
            tmp  = self.cfg.get("temps", {})
            sec  = self.cfg.get("sectors", {})
            app  = self.cfg["app"]

            ref = load_reference(rows, c["brake_threshold"], c["brake_min_samples"],
                                 c.get("lift_threshold", 0.5), c.get("lift_min_samples", 8))

            ref_lap_time: float | None = None
            if ref.get("time"):
                valid = [t for t in ref["time"] if t is not None]
                if valid:
                    ref_lap_time = max(valid)

            coach_cfg: dict = {
                **c,
                "alerts":  self.cfg["alerts"],
                "mode":    self._mode_var.get(),
                "assumed_track_length_m":            session.get("track_length_m", 3000),
                "reference_lap_time_s":              ref_lap_time,
                "critique_brake_min_delta":          crit.get("brake_min_delta", 0.08),
                "critique_brake_target_override":    crit.get("brake_target_override"),
                "critique_brake_template":           crit.get("brake_template", "brake {actual}%, try for {target}%"),
                "critique_throttle_window_m":        crit.get("throttle_window_m", 150),
                "critique_throttle_full_threshold":  crit.get("throttle_full_threshold", 0.95),
                "critique_throttle_min_delta_m":     crit.get("throttle_min_delta_m", 15),
                "critique_throttle_late_template":   crit.get("throttle_late_template", "full throttle {delta}s sooner"),
                "critique_throttle_early_template":  crit.get("throttle_early_template", "wait {delta}s before full throttle"),
                "smoothness_lap_report":             smo.get("lap_report", True),
                "smoothness_zone_report":            smo.get("zone_report", True),
                "smoothness_min_delta":              smo.get("min_delta", 0.10),
                "smoothness_zone_window_pct":        smo.get("zone_window_pct", 0.03),
                "smoothness_brake_template":         smo.get("brake_template", "smoother on the brakes, you scored {score} versus {ref}"),
                "smoothness_throttle_template":      smo.get("throttle_template", "smoother on the throttle, you scored {score} versus {ref}"),
                "smoothness_zone_brake_template":    smo.get("zone_brake_template", "smoother brake in that zone"),
                "smoothness_zone_throttle_template": smo.get("zone_throttle_template", "smoother throttle out of that zone"),
                "delta_enabled":                     self.cfg.get("delta", {}).get("enabled", True),
                "delta_interval_s":                  self.cfg.get("delta", {}).get("interval_s", 20.0),
                "sectors_enabled":                   sec.get("enabled", True),
                "sector_splits":                     sec.get("splits", [0.33, 0.66]),
                "ous_enabled":                       ous.get("enabled", True),
                "ous_threshold":                     ous.get("threshold", 0.3),
                "ous_wheelbase_m":                   ous.get("wheelbase_m", 2.7),
                "ous_cooldown_pct":                  ous.get("cooldown_pct", 0.05),
                "oversteer_cue":                     ous.get("oversteer_cue", "oversteer"),
                "understeer_cue":                    ous.get("understeer_cue", "understeer"),
                "temps":                             tmp,
            }

            log: SessionLog | None = None
            if app.get("session_log_enabled", True):
                log = SessionLog(
                    os.path.join(CONFIG_DIR, app.get("log_dir", "session_logs")),
                    session["car_name"], session["track_name"],
                )
                log.start_lap(1)

            self._coach = Coach(ref, audio, coach_cfg, log=log)
            self._coach.set_track_length(session.get("track_length_m", 3000))
            self._ref_info.set(f"{session['car_name']} — {len(ref['zones'])} zones detected")
        except Exception as e:
            self._ref_info.set(f"Error: {e}")


class _OAuthDialog(ctk.CTkToplevel):
    """Modal dialog that walks the user through Garage61 OAuth2 setup.

    Collects client_id and client_secret, opens the browser for user consent,
    exchanges the authorisation code for tokens, and writes the access token
    into config.toml automatically.
    """

    def __init__(self, parent: ctk.CTk, cfg: dict) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.title("Connect Garage61")
        self.geometry("400x280")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(self, text="Garage61 OAuth Setup",
                     font=("", 14, "bold")).pack(pady=(16, 4))
        ctk.CTkLabel(
            self,
            text="Create an app at garage61.net/developer,\nthen enter your credentials below.",
            font=("", 11), text_color="gray", justify="center",
        ).pack(pady=(0, 12))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(padx=24, fill="x")

        ctk.CTkLabel(form, text="Client ID",
                     font=("", 11), anchor="w").grid(row=0, column=0, sticky="w", pady=4)
        self._client_id = ctk.CTkEntry(form, width=240)
        self._client_id.grid(row=0, column=1, padx=(8, 0))

        ctk.CTkLabel(form, text="Client Secret",
                     font=("", 11), anchor="w").grid(row=1, column=0, sticky="w", pady=4)
        self._client_secret = ctk.CTkEntry(form, width=240, show="•")
        self._client_secret.grid(row=1, column=1, padx=(8, 0))

        self._status_var = ctk.StringVar(value="")
        ctk.CTkLabel(self, textvariable=self._status_var,
                     font=("", 11), text_color="gray").pack(pady=8)

        ctk.CTkButton(self, text="Authorise in Browser",
                      command=self._start_flow, width=180).pack(pady=4)

    def _start_flow(self) -> None:
        """Validate inputs then run the OAuth flow on a background thread."""
        client_id     = self._client_id.get().strip()
        client_secret = self._client_secret.get().strip()
        if not client_id or not client_secret:
            self._status_var.set("Please enter both fields.")
            return
        self._status_var.set("Opening browser… waiting for callback…")
        threading.Thread(target=self._run_flow,
                         args=(client_id, client_secret), daemon=True).start()

    def _run_flow(self, client_id: str, client_secret: str) -> None:
        """Exchange the authorisation code for tokens and persist the access token."""
        try:
            tokens:       dict = run_oauth_flow(client_id, client_secret)
            access_token: str  = tokens.get("access_token", "")
            if not access_token:
                raise ValueError(f"Unexpected response: {tokens}")
            _save_token_to_config(access_token)
            self.cfg["garage61"]["token"] = access_token
            self._status_var.set("✓ Connected! Token saved to config.toml")
        except Exception as e:
            self._status_var.set(f"Error: {e}")


def _save_token_to_config(token: str) -> None:
    """Patch the token = "..." line inside [garage61] in the user config file."""
    path = _ensure_config()
    try:
        with open(path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return

    in_section = False
    with open(path, "w") as f:
        for line in lines:
            stripped = line.strip()
            if stripped == "[garage61]":
                in_section = True
            elif stripped.startswith("["):
                in_section = False
            if in_section and stripped.startswith("token"):
                line = f'token = "{token}"\n'
            f.write(line)


def main() -> None:
    try:
        cfg = load_config()
    except FileNotFoundError:
        print(f"config.toml not found. Expected at: {CONFIG_PATH}")
        sys.exit(1)

    ctk.set_appearance_mode("dark")
    App(cfg).mainloop()


if __name__ == "__main__":
    main()
