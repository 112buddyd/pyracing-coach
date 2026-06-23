"""Smoothness scoring: measures how jerky brake/throttle inputs are.

Score is the mean absolute derivative of an input signal — lower is smoother.
Per-zone and per-lap scores are compared against the reference lap.
"""


def roughness(samples: list[float]) -> float:
    """Return mean absolute change per sample. 0.0 = perfectly smooth."""
    if len(samples) < 2:
        return 0.0
    return sum(abs(samples[i] - samples[i - 1]) for i in range(1, len(samples))) / (len(samples) - 1)


def smoothness_score(samples: list[float]) -> float:
    """Return a normalised score where 1.0 = perfectly smooth, 0.0 = maximally rough."""
    return max(0.0, 1.0 - roughness(samples) * 10)


def ref_roughness(ref: dict, key: str) -> float:
    """Return the roughness of a named channel from the reference lap dict."""
    return roughness(ref[key])


class SmoothnessTracker:
    """Accumulates brake and throttle samples for the current lap and per braking zone.

    Compares roughness against the reference lap and speaks a critique via audio
    when the gap exceeds the configured minimum delta.
    """

    def __init__(self, ref: dict, audio: object, cfg: dict) -> None:
        self.ref:   dict   = ref
        self.audio: object = audio
        self.cfg:   dict   = cfg

        self._lap_brake:    list[float] = []
        self._lap_throttle: list[float] = []

        self._zone_brake:    list[float] = []
        self._zone_throttle: list[float] = []
        self._in_zone:       bool        = False
        self._last_zone_idx: int | None  = None

    def tick(self, telem: dict, zone_idx: int | None, in_zone: bool) -> None:
        """Record one telemetry sample. Call every coach tick."""
        b: float = telem["brake"]
        t: float = telem["throttle"]

        self._lap_brake.append(b)
        self._lap_throttle.append(t)

        if in_zone:
            if not self._in_zone:
                self._zone_brake    = []
                self._zone_throttle = []
                self._in_zone       = True
                self._last_zone_idx = zone_idx
            self._zone_brake.append(b)
            self._zone_throttle.append(t)
        elif self._in_zone:
            self._in_zone = False
            self._maybe_critique_zone()

    def lap_summary(self) -> None:
        """Speak lap-level smoothness critique vs reference. Call at lap completion."""
        if not self.cfg.get("smoothness_lap_report", True):
            return

        min_delta: float = self.cfg.get("smoothness_min_delta", 0.1)
        b_score:   float = smoothness_score(self._lap_brake)
        t_score:   float = smoothness_score(self._lap_throttle)
        ref_b:     float = smoothness_score(self.ref["brake"])
        ref_t:     float = smoothness_score(self.ref["throttle"])

        msgs: list[str] = []
        if (ref_b - b_score) > min_delta:
            msgs.append(self.cfg.get("smoothness_brake_template", "smoother on the brakes").format(
                score=round(b_score * 100), ref=round(ref_b * 100)
            ))
        if (ref_t - t_score) > min_delta:
            msgs.append(self.cfg.get("smoothness_throttle_template", "smoother on the throttle").format(
                score=round(t_score * 100), ref=round(ref_t * 100)
            ))
        if msgs:
            self.audio.say(". ".join(msgs))  # type: ignore[attr-defined]

        self._lap_brake    = []
        self._lap_throttle = []

    def _maybe_critique_zone(self) -> None:
        """Speak zone-level smoothness critique if the gap vs reference exceeds min_delta."""
        if not self.cfg.get("smoothness_zone_report", True):
            return

        min_delta:  float = self.cfg.get("smoothness_min_delta", 0.1)
        b_score:    float = smoothness_score(self._zone_brake)
        t_score:    float = smoothness_score(self._zone_throttle)
        zone_idx:   int | None = self._last_zone_idx
        zone:       dict | None = self.ref["zones"][zone_idx] if zone_idx is not None else None

        if zone is None:
            return

        ref_b_zone:  list[float] = _slice_ref(self.ref, "brake",    zone["start_pct"], self.cfg)
        ref_t_zone:  list[float] = _slice_ref(self.ref, "throttle", zone["start_pct"], self.cfg)
        ref_b_score: float = smoothness_score(ref_b_zone)
        ref_t_score: float = smoothness_score(ref_t_zone)

        if (ref_b_score - b_score) > min_delta:
            self.audio.say(  # type: ignore[attr-defined]
                self.cfg.get("smoothness_zone_brake_template", "smoother brake in that zone").format(
                    score=round(b_score * 100), ref=round(ref_b_score * 100)
                )
            )
        if (ref_t_score - t_score) > min_delta:
            self.audio.say(  # type: ignore[attr-defined]
                self.cfg.get("smoothness_zone_throttle_template", "smoother throttle out of that zone").format(
                    score=round(t_score * 100), ref=round(ref_t_score * 100)
                )
            )


def _slice_ref(ref: dict, key: str, start_pct: float, cfg: dict) -> list[float]:
    """Return reference samples within a short window after start_pct."""
    window:  float = cfg.get("smoothness_zone_window_pct", 0.03)
    end_pct: float = start_pct + window
    return [v for d, v in zip(ref["dist"], ref[key]) if start_pct <= d <= end_pct]
