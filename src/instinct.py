"""Reference-free coaching detectors.

Each detector is stateful and receives one telemetry tick at a time.
All speak via the shared AudioCoach instance when a condition is met.
Events are also recorded for the session log and report.
"""
import math
from collections import deque


# ── Helpers ───────────────────────────────────────────────────────────────────

def _wheel_speed_mps(rpm: float | None) -> float:
    """Convert wheel angular speed (RPM as reported by iRacing, actually rad/s) to m/s.

    iRacing's LFwheelSpdRPM is in rad/s despite the name. Tyre radius ~0.32 m.
    """
    if rpm is None:
        return 0.0
    return abs(rpm) * 0.32  # radius in metres


# ── Event record ─────────────────────────────────────────────────────────────

def _event(kind: str, pos: float, detail: str = "") -> dict:
    return {"kind": kind, "lap_dist_pct": round(pos, 4), "detail": detail}


# ── Instinct coach ────────────────────────────────────────────────────────────

class InstinctCoach:
    """Detects technique and car-state issues from raw telemetry with no reference lap.

    Covers: wheel lock, wheelspin, coasting, trail-brake quality, throttle snap,
    brake/throttle overlap, steering-while-braking, lateral G excess,
    fuel delta, and lap consistency.
    """

    def __init__(self, audio: object, cfg: dict) -> None:
        self.audio: object = audio
        self.cfg:   dict   = cfg

        # Per-lap event accumulator — flushed to log at lap end
        self._lap_events: list[dict] = []

        # Lap time history for consistency scoring
        self._lap_times: deque[float] = deque(maxlen=10)
        self._last_lap:  int | None   = None

        # Cooldown: track position of last callout per kind
        self._last_callout: dict[str, float] = {}

        # Throttle snap: track previous throttle value
        self._prev_throttle: float = 0.0

        # Coasting: consecutive ticks below threshold
        self._coast_ticks: int = 0

        # Trail brake quality: samples during corner entry
        self._trail_samples: list[tuple[float, float]] = []  # (brake, steering)
        self._in_trail:      bool = False

        # Fuel target (laps remaining calculation)
        self._fuel_laps_warned: bool = False

    # ── Public ────────────────────────────────────────────────────────────────

    def tick(self, telem: dict) -> None:
        """Process one telemetry sample. Call every coach tick."""
        if not telem or telem.get("speed", 0) < 5.0:
            return

        pos:   float = telem["lap_dist_pct"]
        lap:   int   = telem.get("lap", 0)
        speed: float = telem["speed"]

        # Lap boundary
        if self._last_lap is not None and lap != self._last_lap:
            self._on_lap_complete(telem)
        self._last_lap = lap

        self._check_wheel_lock(telem, pos, speed)
        self._check_wheelspin(telem, pos, speed)
        self._check_coasting(telem, pos)
        self._check_throttle_snap(telem, pos)
        self._check_overlap(telem, pos)
        self._check_steering_under_braking(telem, pos)
        self._check_lateral_g(telem, pos)
        self._check_fuel(telem)
        self._check_trail_brake(telem)

        self._prev_throttle = telem["throttle"]

    def pop_lap_events(self) -> list[dict]:
        """Return and clear accumulated events for the completed lap."""
        events = self._lap_events
        self._lap_events = []
        return events

    # ── Detectors ─────────────────────────────────────────────────────────────

    def _check_wheel_lock(self, telem: dict, pos: float, speed: float) -> None:
        """Detect individual wheel lockup under braking."""
        if telem["brake"] < self.cfg.get("lockup_brake_threshold", 0.3):
            return
        corners = [
            ("lf", "wheel_rpm_lf", "front left locked"),
            ("rf", "wheel_rpm_rf", "front right locked"),
            ("lr", "wheel_rpm_lr", "rear left locked"),
            ("rr", "wheel_rpm_rr", "rear right locked"),
        ]
        for key, ch, msg in corners:
            wheel_spd = _wheel_speed_mps(telem.get(ch))
            if wheel_spd < self.cfg.get("lockup_wheel_spd_threshold", 1.0) and speed > 10.0:
                if self._cooldown(f"lock_{key}", pos, 0.03):
                    self.audio.say(msg)  # type: ignore[attr-defined]
                    self._lap_events.append(_event("wheel_lock", pos, key))

    def _check_wheelspin(self, telem: dict, pos: float, speed: float) -> None:
        """Detect rear wheelspin on throttle application."""
        if telem["throttle"] < self.cfg.get("spin_throttle_threshold", 0.5):
            return
        rear_avg = (
            _wheel_speed_mps(telem.get("wheel_rpm_lr")) +
            _wheel_speed_mps(telem.get("wheel_rpm_rr"))
        ) / 2
        front_avg = (
            _wheel_speed_mps(telem.get("wheel_rpm_lf")) +
            _wheel_speed_mps(telem.get("wheel_rpm_rf"))
        ) / 2
        if front_avg < 1.0:
            return
        ratio = rear_avg / front_avg
        if ratio > self.cfg.get("spin_ratio_threshold", 1.15):
            if self._cooldown("spin", pos, 0.04):
                self.audio.say(self.cfg.get("spin_cue", "wheelspin"))  # type: ignore[attr-defined]
                self._lap_events.append(_event("wheelspin", pos))

    def _check_coasting(self, telem: dict, pos: float) -> None:
        """Detect sustained coasting (both pedals near zero at speed)."""
        if telem["throttle"] < 0.05 and telem["brake"] < 0.05:
            self._coast_ticks += 1
        else:
            self._coast_ticks = 0

        min_ticks = self.cfg.get("coast_min_ticks", 30)  # ~0.5s at 60Hz
        if self._coast_ticks == min_ticks:
            if self._cooldown("coast", pos, 0.05):
                self.audio.say(self.cfg.get("coast_cue", "coasting"))  # type: ignore[attr-defined]
                self._lap_events.append(_event("coasting", pos))

    def _check_throttle_snap(self, telem: dict, pos: float) -> None:
        """Detect a sharp throttle snap (high rate of change)."""
        delta = telem["throttle"] - self._prev_throttle
        threshold = self.cfg.get("snap_delta_threshold", 0.6)
        if delta > threshold and telem["throttle"] > 0.7:
            if self._cooldown("snap", pos, 0.04):
                self.audio.say(self.cfg.get("snap_cue", "smooth throttle"))  # type: ignore[attr-defined]
                self._lap_events.append(_event("throttle_snap", pos,
                                               f"delta={delta:.2f}"))

    def _check_overlap(self, telem: dict, pos: float) -> None:
        """Detect simultaneous brake and throttle (unless configured to allow it)."""
        if self.cfg.get("overlap_allowed", False):
            return
        if telem["brake"] > self.cfg.get("overlap_brake_min", 0.2) and \
           telem["throttle"] > self.cfg.get("overlap_throttle_min", 0.2):
            if self._cooldown("overlap", pos, 0.05):
                self.audio.say(self.cfg.get("overlap_cue", "brake throttle overlap"))  # type: ignore[attr-defined]
                self._lap_events.append(_event("overlap", pos))

    def _check_steering_under_braking(self, telem: dict, pos: float) -> None:
        """Detect high steering input at peak brake pressure."""
        sa = abs(telem.get("steering_angle") or 0.0)
        if telem["brake"] > self.cfg.get("steer_brake_threshold", 0.7) and \
           sa > self.cfg.get("steer_angle_threshold", 0.3):
            if self._cooldown("steer_brake", pos, 0.04):
                self.audio.say(self.cfg.get("steer_brake_cue", "trail in easier"))  # type: ignore[attr-defined]
                self._lap_events.append(_event("steering_under_braking", pos,
                                               f"angle={math.degrees(sa):.0f}deg"))

    def _check_lateral_g(self, telem: dict, pos: float) -> None:
        """Warn on excessive lateral G through a corner."""
        lat_g = abs(telem.get("lat_accel") or 0.0) / 9.81  # convert m/s² to G
        if lat_g > self.cfg.get("lat_g_threshold", 3.5):
            if self._cooldown("lat_g", pos, 0.05):
                self.audio.say(self.cfg.get("lat_g_cue", "too much lateral load"))  # type: ignore[attr-defined]
                self._lap_events.append(_event("lateral_g_excess", pos,
                                               f"{lat_g:.1f}G"))

    def _check_trail_brake(self, telem: dict) -> None:
        """Track trail-brake quality: brake should release smoothly as steering increases."""
        sa = abs(telem.get("steering_angle") or 0.0)
        if telem["brake"] > 0.1 and sa > 0.1:
            self._in_trail = True
            self._trail_samples.append((telem["brake"], sa))
        elif self._in_trail:
            self._in_trail = False
            self._evaluate_trail_brake()
            self._trail_samples = []

    def _evaluate_trail_brake(self) -> None:
        """After a trail-brake sequence, assess smoothness of release."""
        if len(self._trail_samples) < 5:
            return
        # Good trail braking: brake decreases as steering increases (negative correlation)
        brakes   = [s[0] for s in self._trail_samples]
        steers   = [s[1] for s in self._trail_samples]
        n        = len(brakes)
        mean_b   = sum(brakes) / n
        mean_s   = sum(steers) / n
        cov      = sum((b - mean_b) * (s - mean_s) for b, s in zip(brakes, steers)) / n
        std_b    = math.sqrt(sum((b - mean_b) ** 2 for b in brakes) / n) or 1e-9
        std_s    = math.sqrt(sum((s - mean_s) ** 2 for s in steers) / n) or 1e-9
        corr     = cov / (std_b * std_s)  # -1 = perfect trail, +1 = bad
        pos      = self._trail_samples[-1][1]  # use last steering as proxy for position

        if corr > self.cfg.get("trail_brake_corr_threshold", 0.3):
            self.audio.say(self.cfg.get("trail_brake_cue", "release brake as you turn in"))  # type: ignore[attr-defined]
            self._lap_events.append(_event("trail_brake_poor", 0.0,
                                           f"corr={corr:.2f}"))

    def _check_fuel(self, telem: dict) -> None:
        """Warn if fuel will run out before the session ends."""
        if self._fuel_laps_warned:
            return
        fuel        = telem.get("fuel_level") or 0.0
        use_per_hr  = telem.get("fuel_use_per_hour") or 0.0
        time_remain = telem.get("session_time_remain") or 0.0

        if use_per_hr < 0.1 or time_remain <= 0:
            return

        fuel_remain_time = (fuel / use_per_hr) * 3600  # seconds of fuel left
        buffer           = self.cfg.get("fuel_warn_buffer_s", 120)

        if fuel_remain_time < time_remain + buffer:
            laps_of_fuel = fuel_remain_time / max(telem.get("lap_time") or 90, 30)
            self.audio.say(  # type: ignore[attr-defined]
                self.cfg.get("fuel_cue", "fuel warning, {laps:.0f} laps remaining").format(
                    laps=laps_of_fuel
                )
            )
            self._fuel_laps_warned = True
            self._lap_events.append(_event("fuel_warning", 0.0,
                                           f"{laps_of_fuel:.1f} laps"))

    # ── Lap complete ──────────────────────────────────────────────────────────

    def _on_lap_complete(self, telem: dict) -> None:
        """Handle lap boundary: consistency check and fuel warning reset."""
        last_t = telem.get("last_lap_time") or 0.0
        if last_t > 10:
            self._lap_times.append(last_t)

        if len(self._lap_times) >= self.cfg.get("consistency_min_laps", 3):
            times = list(self._lap_times)
            mean  = sum(times) / len(times)
            std   = math.sqrt(sum((t - mean) ** 2 for t in times) / len(times))
            threshold = self.cfg.get("consistency_std_threshold", 1.5)
            if std > threshold:
                self.audio.say(  # type: ignore[attr-defined]
                    self.cfg.get("consistency_cue",
                                 "work on consistency, lap times varying by {std:.1f} seconds"
                                 ).format(std=std)
                )
                self._lap_events.append(_event("consistency", 0.0, f"std={std:.2f}"))

        self._fuel_laps_warned = False
        self._coast_ticks = 0

    # ── Utility ───────────────────────────────────────────────────────────────

    def _cooldown(self, kind: str, pos: float, min_gap: float) -> bool:
        """Return True and update position if enough track has passed since last callout."""
        last = self._last_callout.get(kind, -1.0)
        if abs(pos - last) < min_gap:
            return False
        self._last_callout[kind] = pos
        return True
