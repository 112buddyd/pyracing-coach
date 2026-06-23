"""Load reference lap CSV, detect braking/lift zones, and look up nearest row by LapDistPct."""


def load_reference(rows: list[dict], brake_threshold: float, brake_min_samples: int,
                   lift_threshold: float = 0.5, lift_min_samples: int = 8) -> dict:
    """Parse raw CSV rows into typed arrays and detect braking + lift zones.

    Returns a dict with parallel lists keyed by:
      dist, brake, throttle, gear, time — indexed by sample number
      zones — list of {start_pct, peak_brake, gear, type} sorted by start_pct
              type is "brake" or "lift"
    """
    dist:     list[float]        = []
    brake:    list[float]        = []
    throttle: list[float]        = []
    gear:     list[int]          = []
    time:     list[float | None] = []

    for r in rows:
        try:
            # Support both ibt channel names (capitalised) and CSV names (lower)
            dist.append(float(r.get("LapDistPct", r.get("lap_dist_pct", 0))))
            brake.append(float(r.get("Brake", r.get("brake", 0))))
            throttle.append(float(r.get("Throttle", r.get("throttle", 0))))
            gear.append(int(float(r.get("Gear", r.get("gear", 0)))))
            t = r.get("SessionTime") or r.get("Time") or r.get("time") or r.get("LapTime")
            time.append(float(t) if t is not None else None)
        except (ValueError, KeyError, TypeError):
            continue

    time_clean: list[float] = [t for t in time if t is not None]
    if time_clean:
        t0 = time_clean[0]
        time = [t - t0 if t is not None else None for t in time]

    brake_zones = _detect_brake_zones(dist, brake, gear, brake_threshold, brake_min_samples)
    lift_zones  = _detect_lift_zones(dist, brake, throttle, gear, lift_threshold, lift_min_samples, brake_threshold)
    zones = sorted(brake_zones + lift_zones, key=lambda z: z["start_pct"])

    return {"dist": dist, "brake": brake, "throttle": throttle, "gear": gear, "time": time, "zones": zones}


def _detect_brake_zones(dist: list[float], brake: list[float], gear: list[int],
                        threshold: float, min_samples: int) -> list[dict]:
    """Return zones where brake pressure exceeds threshold for at least min_samples frames."""
    zones: list[dict] = []
    in_zone = False
    start_idx = 0

    for i, b in enumerate(brake):
        if not in_zone and b >= threshold:
            in_zone = True
            start_idx = i
        elif in_zone and b < threshold:
            if (i - start_idx) >= min_samples:
                peak_i = max(range(start_idx, i), key=lambda x: brake[x])
                zones.append({
                    "start_pct":  dist[start_idx],
                    "peak_brake": brake[peak_i],
                    "gear":       gear[peak_i],
                    "type":       "brake",
                })
            in_zone = False

    return zones


def _detect_lift_zones(dist: list[float], brake: list[float], throttle: list[float],
                       gear: list[int], lift_threshold: float, min_samples: int,
                       brake_threshold: float) -> list[dict]:
    """Return zones where throttle drops significantly without meaningful braking (lift-only corners)."""
    zones: list[dict] = []
    in_zone = False
    start_idx = 0

    for i, t in enumerate(throttle):
        throttle_lifted = t < (1.0 - lift_threshold)
        not_braking     = brake[i] < brake_threshold

        if not in_zone and throttle_lifted and not_braking:
            in_zone = True
            start_idx = i
        elif in_zone and (not throttle_lifted or not not_braking):
            if (i - start_idx) >= min_samples:
                min_t_i = min(range(start_idx, i), key=lambda x: throttle[x])
                zones.append({
                    "start_pct":  dist[start_idx],
                    "peak_brake": 0.0,
                    "gear":       gear[min_t_i],
                    "type":       "lift",
                })
            in_zone = False

    return zones


def nearest_row(ref: dict, lap_dist_pct: float) -> dict:
    """Return the reference brake, throttle, and gear at the closest LapDistPct."""
    dist: list[float] = ref["dist"]
    idx = min(range(len(dist)), key=lambda i: abs(dist[i] - lap_dist_pct))
    return {"brake": ref["brake"][idx], "throttle": ref["throttle"][idx], "gear": ref["gear"][idx]}
