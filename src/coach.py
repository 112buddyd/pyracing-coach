"""Coaching engine — all audio features.

Modes (set via cfg["mode"]):
  learning  : countdown cues before braking/lift zones
  critique  : post-zone debrief on brake pressure and throttle timing
  both      : countdown + debrief

Always active regardless of mode:
  lap delta, PB notification, oversteer/understeer detection,
  sector time deltas, tyre/brake temperature warnings, smoothness scoring,
  and all reference-free instinct coaching.
"""
from reference_lap import nearest_row
from smoothness import SmoothnessTracker, smoothness_score
from instinct import InstinctCoach


class Coach:
    """Processes telemetry ticks and dispatches audio cues via AudioCoach.

    Instantiate once per reference lap load; call tick() on every telemetry
    sample while coaching is active.
    """

    def __init__(self, ref: dict, audio: object, cfg: dict, log: object | None = None) -> None:
        self.ref:   dict         = ref
        self.audio: object       = audio
        self.cfg:   dict         = cfg
        self.log:   object | None = log
        self.mode:  str          = cfg.get("mode", "learning")

        # Zone / critique state
        self._active_zone_idx:          int | None   = None
        self._fired_steps:              set          = set()
        self._in_zone:                  bool         = False
        self._zone_brake_samples:       list[float]  = []
        self._post_zone:                bool         = False
        self._post_throttle_samples:    list[tuple]  = []
        self._post_throttle_dist_start: float | None = None
        self._zone_entry_idx:           int | None   = None

        # Lap state
        self._last_lap:       int | None   = None
        self._pb:             float | None = None
        self._lap_start_time: float | None = None

        # Sector state
        splits: list[float] = sorted(cfg.get("sector_splits", [0.33, 0.66]))
        self._sector_splits:     list[float] = splits
        self._sector_fired:      list[bool]  = [False] * len(splits)
        self._ref_sector_times:  list[float] = _build_ref_sector_times(ref, splits)

        # Delta state
        self._delta_interval:     float        = cfg.get("delta_interval_s", 20.0)
        self._last_delta_spoken:  float | None = None

        # Oversteer/understeer rolling window: (steering_angle, yaw_rate)
        self._ous_window: list[tuple[float, float]] = []

        # Cooldown positions for temp and OUS warnings
        self._temp_warned: dict[str, float] = {}

        self._smoothness: SmoothnessTracker = SmoothnessTracker(ref, audio, cfg)
        self._instinct:   InstinctCoach     = InstinctCoach(audio, cfg.get("instinct", {}))
        self._track_len:  float             = cfg.get("assumed_track_length_m", 3000)

    # ── Public ────────────────────────────────────────────────────────────────

    def set_track_length(self, metres: float) -> None:
        """Override the track length used for distance-to-time conversions."""
        self._track_len = metres

    def tick(self, telem: dict) -> None:
        """Process one telemetry sample. Call at the configured poll interval."""
        if not telem or telem["speed"] < 1.0:
            return

        pos:        float        = telem["lap_dist_pct"]
        speed:      float        = telem["speed"]
        lap:        int          = telem.get("lap", 0)
        lap_time:   float        = telem.get("lap_time", 0.0)
        last_lap_t: float | None = telem.get("last_lap_time")
        best_lap_t: float | None = telem.get("best_lap_time")

        # ── Lap boundary ──────────────────────────────────────────────────
        if self._last_lap is not None and lap != self._last_lap:
            self._on_lap_complete(last_lap_t, best_lap_t, lap)
        if self._last_lap != lap:
            self._last_lap       = lap
            self._lap_start_time = lap_time
            self._sector_fired   = [False] * len(self._sector_splits)

        # ── Zone lookup ───────────────────────────────────────────────────
        zone_idx, zone = self._next_zone(pos, self.ref["zones"])
        if zone is None:
            return

        dist_pct:     float = (zone["start_pct"] - pos) % 1.0
        time_to_zone: float = (dist_pct * self._track_len) / max(speed, 1.0)

        ref_row: dict = nearest_row(self.ref, pos)
        in_zone: bool = ref_row["brake"] >= self.cfg["brake_threshold"]

        self._smoothness.tick(telem, zone_idx, in_zone)
        self._instinct.tick(telem)

        # ── Learning mode ─────────────────────────────────────────────────
        if self.mode in ("learning", "both"):
            if zone_idx != self._active_zone_idx:
                self._active_zone_idx = zone_idx
                self._fired_steps     = set()

            for step in self.cfg["countdown_steps"]:
                if step not in self._fired_steps and time_to_zone <= step + 0.15:
                    self._fired_steps.add(step)
                    self.audio.say(str(step))  # type: ignore[attr-defined]

            cue: str = self.cfg["lift_cue"] if zone.get("type") == "lift" else self.cfg["brake_cue"]
            if cue not in self._fired_steps and time_to_zone <= 0.15:
                self._fired_steps.add(cue)
                self.audio.say(cue)  # type: ignore[attr-defined]

            alerts: dict = self.cfg.get("alerts", {})
            if alerts.get("throttle_still_on_warn") and in_zone:
                if telem["throttle"] > 0.1 and telem["brake"] < 0.1:
                    self.audio.say("lift")  # type: ignore[attr-defined]
            if alerts.get("gear_mismatch_warn") and abs(telem["gear"] - ref_row["gear"]) >= 1:
                if time_to_zone < 1.0:
                    self.audio.say(f"gear {ref_row['gear']}")  # type: ignore[attr-defined]

        # ── Critique mode ─────────────────────────────────────────────────
        if self.mode in ("critique", "both"):
            self._update_critique(telem, pos, zone_idx, time_to_zone)

        # ── Always-on features ────────────────────────────────────────────
        self._check_delta(pos, lap_time, best_lap_t)
        self._check_sectors(pos, lap_time)
        self._check_oversteer_understeer(pos, telem)
        self._check_temps(telem, pos)

    # ── Lap complete ──────────────────────────────────────────────────────────

    def _on_lap_complete(self, last_lap_t: float | None, best_lap_t: float | None,
                         new_lap: int) -> None:
        """Handle lap boundary: smoothness summary, PB check, lap delta, log flush."""
        self._smoothness.lap_summary()

        if not last_lap_t or last_lap_t <= 0:
            return

        is_pb: bool = False
        if self._pb is None or last_lap_t < self._pb:
            self._pb  = last_lap_t
            is_pb     = True
            m, s      = divmod(last_lap_t, 60)
            self.audio.say(f"personal best, {int(m)} {s:.2f}")  # type: ignore[attr-defined]

        ref_time: float | None = self.cfg.get("reference_lap_time_s")
        if ref_time and not is_pb:
            delta: float = last_lap_t - ref_time
            sign:  str   = "up" if delta < 0 else "down"
            self.audio.say(f"{abs(delta):.1f} seconds {sign}")  # type: ignore[attr-defined]

        if self.log:
            b_score: float = smoothness_score(self._smoothness._lap_brake)
            t_score: float = smoothness_score(self._smoothness._lap_throttle)
            ref_delta: float = last_lap_t - (self.cfg.get("reference_lap_time_s") or last_lap_t)
            instinct_events = self._instinct.pop_lap_events()
            self.log.finish_lap(last_lap_t, ref_delta, is_pb, b_score, t_score,  # type: ignore[attr-defined]
                                instinct_events)
            self.log.start_lap(new_lap)  # type: ignore[attr-defined]

        self._last_delta_spoken = None

    # ── Delta (mid-lap) ───────────────────────────────────────────────────────

    def _check_delta(self, pos: float, lap_time: float,
                     best_lap_t: float | None) -> None:
        """Speak mid-lap time delta vs reference at configured intervals."""
        if not self.cfg.get("delta_enabled", True):
            return
        ref_time: float | None = self.cfg.get("reference_lap_time_s")
        if not ref_time or not lap_time:
            return

        ref_at_pos: float | None = _ref_time_at_pos(self.ref, pos)
        if ref_at_pos is None:
            return

        delta: float = lap_time - ref_at_pos
        if (self._last_delta_spoken is None
                or (lap_time - self._last_delta_spoken) >= self._delta_interval):
            self._last_delta_spoken = lap_time
            sign: str = "up" if delta < 0 else "down"
            self.audio.say(f"{abs(delta):.1f} {sign}")  # type: ignore[attr-defined]

    # ── Sector times ──────────────────────────────────────────────────────────

    def _check_sectors(self, pos: float, lap_time: float) -> None:
        """Speak sector delta when the car crosses a configured sector split."""
        if not self.cfg.get("sectors_enabled", True):
            return
        for i, split in enumerate(self._sector_splits):
            if not self._sector_fired[i] and pos >= split:
                self._sector_fired[i] = True
                ref_t: float | None = (self._ref_sector_times[i]
                                       if i < len(self._ref_sector_times) else None)
                if ref_t is not None:
                    delta: float = lap_time - ref_t
                    sign:  str   = "up" if delta < 0 else "down"
                    self.audio.say(f"sector {i + 1}, {abs(delta):.1f} {sign}")  # type: ignore[attr-defined]
                else:
                    self.audio.say(f"sector {i + 1}")  # type: ignore[attr-defined]

    # ── Oversteer / Understeer ────────────────────────────────────────────────

    def _check_oversteer_understeer(self, pos: float, telem: dict) -> None:
        """Detect sustained oversteer/understeer via yaw rate vs steering angle heuristic."""
        if not self.cfg.get("ous_enabled", True):
            return

        sa:  float = telem.get("steering_angle", 0.0) or 0.0
        yr:  float = telem.get("yaw_rate", 0.0) or 0.0
        spd: float = telem.get("speed", 0.0)

        if spd < 10.0 or abs(sa) < 0.05:
            self._ous_window.clear()
            return

        self._ous_window.append((abs(sa), abs(yr)))
        if len(self._ous_window) > 60:
            self._ous_window.pop(0)
        if len(self._ous_window) < 20:
            return

        avg_sa: float = sum(x[0] for x in self._ous_window) / len(self._ous_window)
        avg_yr: float = sum(x[1] for x in self._ous_window) / len(self._ous_window)

        wheelbase:   float = self.cfg.get("ous_wheelbase_m", 2.7)
        expected_yr: float = (spd * avg_sa) / wheelbase
        ratio:       float = avg_yr / max(expected_yr, 0.01)

        threshold:    float = self.cfg.get("ous_threshold", 0.3)
        cooldown_pct: float = self.cfg.get("ous_cooldown_pct", 0.05)
        last_pos:     float = self._temp_warned.get("ous", -1.0)

        if abs(pos - last_pos) < cooldown_pct:
            return

        if ratio < (1.0 - threshold):
            self.audio.say(self.cfg.get("understeer_cue", "understeer"))  # type: ignore[attr-defined]
            self._temp_warned["ous"] = pos
        elif ratio > (1.0 + threshold):
            self.audio.say(self.cfg.get("oversteer_cue", "oversteer"))  # type: ignore[attr-defined]
            self._temp_warned["ous"] = pos

        self._ous_window.clear()

    # ── Tyre / Brake temp warnings ────────────────────────────────────────────

    def _check_temps(self, telem: dict, pos: float) -> None:
        """Warn on cold or overheated tyre/brake temperatures."""
        tc: dict = self.cfg.get("temps", {})
        if not tc.get("enabled", True):
            return

        cooldown: float = tc.get("cooldown_pct", 0.1)
        checks: list[tuple] = [
            ("tyre_lf",  telem.get("tyre_temp_lf"),  tc.get("tyre_cold_c"),  tc.get("tyre_hot_c"),  "front left tyre cold",   "front left tyre hot"),
            ("tyre_rf",  telem.get("tyre_temp_rf"),  tc.get("tyre_cold_c"),  tc.get("tyre_hot_c"),  "front right tyre cold",  "front right tyre hot"),
            ("tyre_lr",  telem.get("tyre_temp_lr"),  tc.get("tyre_cold_c"),  tc.get("tyre_hot_c"),  "rear left tyre cold",    "rear left tyre hot"),
            ("tyre_rr",  telem.get("tyre_temp_rr"),  tc.get("tyre_cold_c"),  tc.get("tyre_hot_c"),  "rear right tyre cold",   "rear right tyre hot"),
            ("brake_lf", telem.get("brake_temp_lf"), tc.get("brake_cold_c"), tc.get("brake_hot_c"), "front left brake cold",  "front left brake hot"),
            ("brake_rf", telem.get("brake_temp_rf"), tc.get("brake_cold_c"), tc.get("brake_hot_c"), "front right brake cold", "front right brake hot"),
        ]

        for key, temp, cold, hot, cold_msg, hot_msg in checks:
            if temp is None:
                continue
            if abs(pos - self._temp_warned.get(key, -1.0)) < cooldown:
                continue
            if cold is not None and temp < cold:
                self.audio.say(cold_msg)  # type: ignore[attr-defined]
                self._temp_warned[key] = pos
            elif hot is not None and temp > hot:
                self.audio.say(hot_msg)  # type: ignore[attr-defined]
                self._temp_warned[key] = pos

    # ── Critique helpers ──────────────────────────────────────────────────────

    def _update_critique(self, telem: dict, pos: float,
                         zone_idx: int | None, time_to_zone: float) -> None:
        """Track entry/exit of reference braking zones and trigger post-zone debrief."""
        threshold:   float = self.cfg["brake_threshold"]
        ref_row:     dict  = nearest_row(self.ref, pos)
        in_ref_zone: bool  = ref_row["brake"] >= threshold

        if not self._in_zone and in_ref_zone:
            self._in_zone                   = True
            self._zone_brake_samples        = []
            self._post_zone                 = False
            self._post_throttle_samples     = []
            self._post_throttle_dist_start  = None
            self._zone_entry_idx            = zone_idx

        if self._in_zone and in_ref_zone:
            self._zone_brake_samples.append(telem["brake"])

        if self._in_zone and not in_ref_zone:
            self._in_zone = False
            self._critique_brake(ref_row)
            self._post_zone                = True
            self._post_throttle_dist_start = pos
            if self.log and self._zone_entry_idx is not None:
                zone_type: str = self.ref["zones"][self._zone_entry_idx].get("type", "brake")
                self.log.record_zone(  # type: ignore[attr-defined]
                    self._zone_entry_idx, zone_type,
                    max(self._zone_brake_samples) if self._zone_brake_samples else 0.0,
                    ref_row["brake"], None,
                    smoothness_score(self._smoothness._zone_brake),
                    smoothness_score(self._smoothness._zone_throttle),
                )

        if self._post_zone and self._post_throttle_dist_start is not None:
            window_pct:  float = self.cfg.get("critique_throttle_window_m", 150) / self._track_len
            elapsed_pct: float = (pos - self._post_throttle_dist_start) % 1.0
            ref_row2:    dict  = nearest_row(self.ref, pos)
            if elapsed_pct <= window_pct:
                self._post_throttle_samples.append((elapsed_pct, telem["throttle"], ref_row2["throttle"]))
            else:
                self._post_zone = False
                self._critique_throttle()

    def _critique_brake(self, ref_row: dict) -> float:
        """Speak brake pressure critique and return the delta (target − actual)."""
        if not self._zone_brake_samples:
            return 0.0
        actual_peak: float = max(self._zone_brake_samples)
        target:      float = self.cfg.get("critique_brake_target_override") or ref_row["brake"]
        delta:       float = target - actual_peak
        if abs(delta) >= self.cfg.get("critique_brake_min_delta", 0.08):
            msg: str = self.cfg.get("critique_brake_template", "brake {actual}%, try for {target}%")
            self.audio.say(msg.format(actual=round(actual_peak * 100), target=round(target * 100)))  # type: ignore[attr-defined]
        return delta

    def _critique_throttle(self) -> None:
        """Speak throttle timing critique based on post-zone throttle samples."""
        if not self._post_throttle_samples:
            return
        full: float = self.cfg.get("critique_throttle_full_threshold", 0.95)
        ref_full:    float | None = next((p for p, _, r in self._post_throttle_samples if r >= full), None)
        actual_full: float | None = next((p for p, a, _ in self._post_throttle_samples if a >= full), None)
        if ref_full is None or actual_full is None:
            return
        delta_pct: float = actual_full - ref_full
        delta_m:   float = delta_pct * self._track_len
        if abs(delta_m) < self.cfg.get("critique_throttle_min_delta_m", 15):
            return
        delta_s: float = round(abs(delta_m) / max(20.0, 1.0), 1)
        if delta_m > 0:
            self.audio.say(  # type: ignore[attr-defined]
                self.cfg.get("critique_throttle_late_template", "full throttle {delta}s sooner").format(delta=delta_s)
            )
        else:
            self.audio.say(  # type: ignore[attr-defined]
                self.cfg.get("critique_throttle_early_template", "wait {delta}s before full throttle").format(delta=delta_s)
            )

    # ── Utility ───────────────────────────────────────────────────────────────

    def _next_zone(self, pos: float, zones: list[dict]) -> tuple[int, dict] | tuple[None, None]:
        """Return the (index, zone) of the next zone ahead of pos, wrapping if needed."""
        if not zones:
            return None, None
        ahead = [(i, z) for i, z in enumerate(zones) if z["start_pct"] > pos] or list(enumerate(zones))
        return min(ahead, key=lambda iz: (iz[1]["start_pct"] - pos) % 1.0)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _build_ref_sector_times(ref: dict, splits: list[float]) -> list[float]:
    """Return cumulative lap time at each sector split from the reference time column."""
    times: list | None = ref.get("time")
    if not times:
        return []
    result: list[float] = []
    for split in splits:
        idx = min(range(len(ref["dist"])), key=lambda i: abs(ref["dist"][i] - split))
        t   = times[idx]
        if t is not None:
            result.append(t)
    return result


def _ref_time_at_pos(ref: dict, pos: float) -> float | None:
    """Return the reference lap time at the closest LapDistPct to pos."""
    times: list | None = ref.get("time")
    if not times:
        return None
    idx = min(range(len(ref["dist"])), key=lambda i: abs(ref["dist"][i] - pos))
    return times[idx]
