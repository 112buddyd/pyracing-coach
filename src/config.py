"""Centralised configuration with schema definition.

The SCHEMA defines every config key, its type, default, display label, description,
and tab group. Config loads from TOML, provides typed access via dotted keys,
drives the settings UI field generation, and serialises back to TOML on save.
"""
import os
import tomllib
from dataclasses import dataclass, field as dc_field
from typing import Any


@dataclass(frozen=True)
class Field:
    """One configurable setting."""
    key:     str                      # dotted key: "coaching.brake_cue"
    label:   str                      # short label for UI
    desc:    str                      # longer description shown under the field
    type:    str                      # "float", "int", "bool", "str", "choice"
    default: Any                      # default value
    tab:     str                      # settings UI tab name
    choices: list | None = None       # for type="choice" — static list, or None if dynamic


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA: list[Field] = [
    # Coaching
    Field("coaching.lookahead_seconds", "Lookahead",
          "How many seconds ahead of a zone to start the countdown.", "float", 4.0, "Coaching"),
    Field("coaching.brake_cue", "Brake cue",
          "Word spoken at the exact braking point.", "str", "now", "Coaching"),
    Field("coaching.lift_cue", "Lift cue",
          "Word spoken at a lift-only zone (no heavy braking).", "str", "lift", "Coaching"),
    Field("coaching.brake_threshold", "Brake threshold",
          "Min brake pressure (0–1) in reference to classify as a braking zone.", "float", 0.5, "Coaching"),
    Field("coaching.brake_min_samples", "Brake min samples",
          "Min sustained braking frames to count as a zone (~60 Hz).", "int", 10, "Coaching"),
    Field("coaching.lift_threshold", "Lift threshold",
          "Throttle must drop by this much (0–1) to count as a lift zone.", "float", 0.5, "Coaching"),
    Field("coaching.lift_min_samples", "Lift min samples",
          "Min sustained lift frames to count as a zone.", "int", 8, "Coaching"),

    # Critique
    Field("critique.mode", "Mode",
          "learning = countdown only, critique = post-zone debrief, both = all.", "choice", "both", "Critique",
          ["learning", "critique", "both"]),
    Field("critique.brake_min_delta", "Brake min delta",
          "Min gap between your brake and reference before critique fires.", "float", 0.08, "Critique"),
    Field("critique.brake_template", "Brake template",
          "Template spoken after a zone. {actual} and {target} are percentages.", "str",
          "brake {actual}%, try for {target}%", "Critique"),
    Field("critique.throttle_window_m", "Throttle window (m)",
          "Metres after zone exit to collect throttle data.", "float", 150.0, "Critique"),
    Field("critique.throttle_full_threshold", "Full throttle threshold",
          "Throttle level (0–1) considered 'full'.", "float", 0.95, "Critique"),
    Field("critique.throttle_min_delta_m", "Throttle min delta (m)",
          "Min distance gap before throttle critique fires.", "float", 15.0, "Critique"),
    Field("critique.throttle_late_template", "Throttle late template",
          "Spoken when you reach full throttle too late. {delta} = seconds.", "str",
          "full throttle {delta}s sooner", "Critique"),
    Field("critique.throttle_early_template", "Throttle early template",
          "Spoken when you go full throttle too early. {delta} = seconds.", "str",
          "wait {delta}s before full throttle", "Critique"),

    # Alerts
    Field("alerts.brake_delta_warn", "Brake delta warn",
          "Warn if your brake is this much lighter than reference.", "float", 0.15, "Alerts"),
    Field("alerts.throttle_still_on_warn", "Warn throttle still on",
          "Warn if you're on throttle when reference is braking.", "bool", True, "Alerts"),
    Field("alerts.gear_mismatch_warn", "Warn gear mismatch",
          "Warn if your gear differs from reference at a zone.", "bool", True, "Alerts"),

    # Smoothness
    Field("smoothness.lap_report", "Lap report",
          "Speak smoothness score at the end of each lap.", "bool", True, "Smoothness"),
    Field("smoothness.zone_report", "Zone report",
          "Speak smoothness score after each braking zone.", "bool", True, "Smoothness"),
    Field("smoothness.min_delta", "Min delta",
          "Minimum smoothness gap (0–1) before a critique fires.", "float", 0.10, "Smoothness"),

    # Delta / Sectors
    Field("delta.enabled", "Lap delta enabled",
          "Speak mid-lap time delta vs reference.", "bool", True, "Delta / Sectors"),
    Field("delta.interval_s", "Delta interval (s)",
          "How often (in lap-time seconds) to call out delta.", "float", 20.0, "Delta / Sectors"),
    Field("sectors.enabled", "Sectors enabled",
          "Speak sector delta at each split point.", "bool", True, "Delta / Sectors"),
    Field("sectors.splits", "Sector splits",
          "Comma-separated LapDistPct positions (0–1) of sector boundaries.", "str", "0.33, 0.66", "Delta / Sectors"),

    # Handling
    Field("oversteer_understeer.enabled", "Enabled",
          "Detect and call out oversteer/understeer mid-corner.", "bool", True, "Handling"),
    Field("oversteer_understeer.threshold", "Threshold",
          "Yaw ratio deviation (0–1) required to trigger.", "float", 0.3, "Handling"),
    Field("oversteer_understeer.wheelbase_m", "Wheelbase (m)",
          "Your car's wheelbase — affects expected yaw rate calculation.", "float", 2.7, "Handling"),
    Field("oversteer_understeer.oversteer_cue", "Oversteer cue",
          "Word spoken when oversteer is detected.", "str", "oversteer", "Handling"),
    Field("oversteer_understeer.understeer_cue", "Understeer cue",
          "Word spoken when understeer is detected.", "str", "understeer", "Handling"),

    # Temps
    Field("temps.enabled", "Enabled",
          "Enable tyre and brake temperature warnings.", "bool", True, "Temps"),
    Field("temps.tyre_cold_c", "Tyre cold (°C)",
          "Warn below this tyre temperature.", "float", 70.0, "Temps"),
    Field("temps.tyre_hot_c", "Tyre hot (°C)",
          "Warn above this tyre temperature.", "float", 110.0, "Temps"),
    Field("temps.brake_cold_c", "Brake cold (°C)",
          "Warn below this brake temperature.", "float", 150.0, "Temps"),
    Field("temps.brake_hot_c", "Brake hot (°C)",
          "Warn above this brake temperature.", "float", 900.0, "Temps"),

    # Instinct
    Field("instinct.lockup_brake_threshold", "Lockup brake threshold",
          "Min brake input before checking for wheel lock.", "float", 0.3, "Instinct"),
    Field("instinct.lockup_wheel_spd_threshold", "Lockup wheel speed threshold",
          "Wheel speed (m/s) below which a lockup is flagged.", "float", 1.0, "Instinct"),
    Field("instinct.spin_ratio_threshold", "Wheelspin ratio threshold",
          "Rear/front wheel speed ratio above which wheelspin is flagged.", "float", 1.15, "Instinct"),
    Field("instinct.spin_cue", "Wheelspin cue",
          "Word spoken when wheelspin is detected.", "str", "wheelspin", "Instinct"),
    Field("instinct.coast_min_ticks", "Coast min ticks",
          "Ticks (~60Hz) with both pedals released before warning.", "int", 30, "Instinct"),
    Field("instinct.coast_cue", "Coast cue",
          "Word spoken when coasting is detected.", "str", "coasting", "Instinct"),
    Field("instinct.snap_delta_threshold", "Throttle snap threshold",
          "Per-tick throttle change (0–1) to flag a snap.", "float", 0.6, "Instinct"),
    Field("instinct.snap_cue", "Throttle snap cue",
          "Word spoken on harsh throttle application.", "str", "smooth throttle", "Instinct"),
    Field("instinct.overlap_allowed", "Allow pedal overlap",
          "If true, simultaneous brake+throttle won't trigger a warning.", "bool", False, "Instinct"),
    Field("instinct.overlap_cue", "Overlap cue",
          "Word spoken on brake/throttle overlap.", "str", "brake throttle overlap", "Instinct"),
    Field("instinct.steer_brake_cue", "Steer-under-brake cue",
          "Spoken when steering angle is high at peak brake pressure.", "str", "trail in easier", "Instinct"),
    Field("instinct.trail_brake_cue", "Trail brake cue",
          "Spoken when trail-brake release quality is poor.", "str", "release brake as you turn in", "Instinct"),
    Field("instinct.lat_g_threshold", "Lateral G threshold",
          "G-force above which a warning fires.", "float", 3.5, "Instinct"),
    Field("instinct.lat_g_cue", "Lateral G cue",
          "Spoken when lateral G is exceeded.", "str", "too much lateral load", "Instinct"),
    Field("instinct.fuel_warn_buffer_s", "Fuel warning buffer (s)",
          "Seconds of fuel buffer below which to warn.", "float", 120.0, "Instinct"),
    Field("instinct.consistency_min_laps", "Consistency min laps",
          "Laps of history needed before consistency is assessed.", "int", 3, "Instinct"),
    Field("instinct.consistency_std_threshold", "Consistency std (s)",
          "Lap time std (seconds) above which a consistency warning fires.", "float", 1.5, "Instinct"),

    # Audio
    Field("audio.rate", "Speech rate (WPM)",
          "Words per minute for the TTS voice.", "int", 175, "Audio"),
    Field("audio.volume", "Volume",
          "TTS volume from 0.0 (silent) to 1.0 (maximum).", "float", 1.0, "Audio"),
    Field("audio.voice_name", "Voice",
          "Select the TTS voice / audio output.", "choice", "", "Audio"),

    # Report
    Field("report.format", "Report format",
          "Output format for session reports.", "choice", "html", "Report", ["html", "pdf"]),

    # App
    Field("app.poll_interval", "Poll interval (s)",
          "How often telemetry is sampled (lower = more responsive but more CPU).", "float", 0.05, "App"),
    Field("app.session_log_enabled", "Session log enabled",
          "Write a JSON log file for each session.", "bool", True, "App"),
]


# ── Config class ──────────────────────────────────────────────────────────────

class Config:
    """Load, access, and save the application configuration.

    Provides get/set by dotted key (e.g. "coaching.brake_cue"),
    defaults from SCHEMA, and serialisation to TOML.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        defaults = _build_defaults()
        if os.path.exists(self._path):
            with open(self._path, "rb") as f:
                file_data = tomllib.load(f)
            self._data = _deep_merge(defaults, file_data)
        else:
            self._data = defaults

    def get(self, dotted_key: str, fallback: Any = None) -> Any:
        parts = dotted_key.split(".")
        d = self._data
        for p in parts:
            if isinstance(d, dict):
                d = d.get(p)
            else:
                return fallback
        return d if d is not None else fallback

    def set(self, dotted_key: str, value: Any) -> None:
        parts = dotted_key.split(".")
        d = self._data
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = value

    def section(self, name: str) -> dict:
        return self._data.get(name, {})

    @property
    def raw(self) -> dict:
        return self._data

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        lines: list[str] = ["# pyracing-coach configuration\n"]
        for section, values in self._data.items():
            if not isinstance(values, dict):
                continue
            lines.append(f"\n[{section}]")
            for k, v in values.items():
                if isinstance(v, bool):
                    lines.append(f"{k} = {'true' if v else 'false'}")
                elif isinstance(v, (int, float)):
                    lines.append(f"{k} = {v}")
                elif isinstance(v, list):
                    items = ", ".join(str(i) for i in v)
                    lines.append(f"{k} = [{items}]")
                elif isinstance(v, str):
                    lines.append(f'{k} = "{v}"')
        with open(self._path, "w") as f:
            f.write("\n".join(lines) + "\n")

    @property
    def path(self) -> str:
        return self._path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_defaults() -> dict:
    d: dict = {}
    for f in SCHEMA:
        parts = f.key.split(".")
        sub = d
        for p in parts[:-1]:
            sub = sub.setdefault(p, {})
        sub[parts[-1]] = f.default
    return d


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    result = dict(defaults)
    for k, v in overrides.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
