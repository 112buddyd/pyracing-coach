"""Parse iRacing .ibt telemetry files using pyirsdk's IBT class."""
import os
import irsdk


# Default iRacing telemetry folder on Windows
DEFAULT_IBT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "iRacing", "telemetry")

# Channels we need from the .ibt file
_CHANNELS = ("LapDistPct", "Brake", "Throttle", "Gear", "Speed",
             "SessionTime", "SteeringWheelAngle", "YawRate")


def read_ibt(path: str) -> list[dict]:
    """Read an .ibt file and return a list of sample dicts for the fastest complete lap.

    Each dict has keys matching iRacing variable names (LapDistPct, Brake, etc.).
    Returns an empty list if the file cannot be read or contains no complete lap.
    """
    ibt = irsdk.IBT()
    ibt.open(path)
    try:
        count: int = ibt._disk_header.session_record_count
        if count < 2:
            return []

        # Collect all samples
        samples: list[dict] = []
        for i in range(count):
            row = {ch: ibt.get(i, ch) for ch in _CHANNELS}
            row["Lap"] = ibt.get(i, "Lap") or 0
            samples.append(row)

        return _fastest_lap_samples(samples)
    finally:
        ibt.close()


def find_ibt_files(directory: str = DEFAULT_IBT_DIR) -> list[str]:
    """Return .ibt file paths in directory, newest first."""
    if not os.path.isdir(directory):
        return []
    files = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.lower().endswith(".ibt")
    ]
    return sorted(files, key=os.path.getmtime, reverse=True)


def ibt_session_info(path: str) -> dict:
    """Return car and track name from an .ibt file's session YAML."""
    ibt = irsdk.IBT()
    ibt.open(path)
    try:
        weekend = ibt["WeekendInfo"] or {}
        drivers = (ibt["DriverInfo"] or {}).get("Drivers", [])
        player_idx = ibt.get(0, "PlayerCarIdx") or 0
        car = drivers[player_idx]["CarScreenName"] if drivers else "Unknown"
        return {
            "car_name":       car,
            "track_name":     weekend.get("TrackDisplayName", "Unknown"),
            "track_config":   weekend.get("TrackConfigName", ""),
            "track_length_m": _parse_track_length(weekend.get("TrackLength", "")),
        }
    finally:
        ibt.close()


def _fastest_lap_samples(samples: list[dict]) -> list[dict]:
    """Return samples for the fastest complete lap in the session."""
    # Group sample indices by lap number
    laps: dict[int, list[int]] = {}
    for i, s in enumerate(samples):
        laps.setdefault(int(s["Lap"]), []).append(i)

    # Find the fastest complete lap (needs a full 0→1 LapDistPct sweep)
    best_time: float = float("inf")
    best_indices: list[int] = []

    for lap_num, indices in sorted(laps.items()):
        if len(indices) < 10:
            continue
        lap_samples = [samples[i] for i in indices]
        pcts = [s["LapDistPct"] for s in lap_samples]
        if max(pcts) < 0.95 or min(pcts) > 0.05:
            continue  # not a complete lap
        times = [s["SessionTime"] for s in lap_samples if s["SessionTime"]]
        if len(times) < 2:
            continue
        lap_time = times[-1] - times[0]
        if 0 < lap_time < best_time:
            best_time = lap_time
            best_indices = indices

    return [samples[i] for i in best_indices]


def _parse_track_length(s: str) -> float:
    """Parse '5.54 km' → 5540.0 metres. Falls back to 3000."""
    try:
        return float(str(s).strip().split()[0]) * 1000
    except Exception:
        return 3000.0
