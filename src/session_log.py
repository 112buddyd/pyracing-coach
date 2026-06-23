"""Per-session JSON log: records lap times, delta, smoothness, and zone critiques."""
import json
import os
import time


class SessionLog:
    """Writes a JSON file per session capturing per-lap and per-zone performance data.

    The file is flushed to disk after every completed lap so data is preserved
    even if the session ends unexpectedly.
    """

    def __init__(self, log_dir: str, car: str, track: str) -> None:
        os.makedirs(log_dir, exist_ok=True)
        ts: str = time.strftime("%Y%m%d_%H%M%S")
        safe = lambda s: s.replace(" ", "_").replace("/", "-")
        self._path: str = os.path.join(log_dir, f"{ts}_{safe(car)}_{safe(track)}.json")
        self._data: dict = {"car": car, "track": track, "session_start": ts, "laps": []}
        self._current: dict | None = None

    def start_lap(self, lap_num: int) -> None:
        """Begin recording a new lap. Call at the lap boundary."""
        self._current = {"lap": lap_num, "zones": []}

    def record_zone(self, zone_idx: int, zone_type: str, brake_actual: float,
                    brake_ref: float, throttle_delta_s: float | None,
                    smoothness_brake: float, smoothness_throttle: float) -> None:
        """Append a zone entry to the current lap. Safe to call before start_lap."""
        if self._current is None:
            return
        self._current["zones"].append({
            "zone":               zone_idx,
            "type":               zone_type,
            "brake_actual_pct":   round(brake_actual * 100),
            "brake_ref_pct":      round(brake_ref * 100),
            "throttle_delta_s":   throttle_delta_s,
            "smoothness_brake":   round(smoothness_brake, 3),
            "smoothness_throttle": round(smoothness_throttle, 3),
        })

    def finish_lap(self, lap_time: float | None, delta_s: float | None,
                   is_pb: bool, lap_smoothness_brake: float,
                   lap_smoothness_throttle: float) -> None:
        """Finalise the current lap entry and flush to disk."""
        if self._current is None:
            return
        self._current.update({
            "lap_time_s":          round(lap_time, 3) if lap_time else None,
            "delta_s":             round(delta_s, 3) if delta_s is not None else None,
            "personal_best":       is_pb,
            "smoothness_brake":    round(lap_smoothness_brake, 3),
            "smoothness_throttle": round(lap_smoothness_throttle, 3),
        })
        self._data["laps"].append(self._current)
        self._current = None
        self._flush()

    def _flush(self) -> None:
        """Write current data to disk."""
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)
