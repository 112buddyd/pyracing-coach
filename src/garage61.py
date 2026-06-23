"""Fetch fastest lap + telemetry CSV from Garage61."""
import os
import csv
import hashlib
import io
import time
from garage61api.client import Garage61Client


class Garage61Fetcher:
    """Retrieves reference lap telemetry from the Garage61 API with disk caching.

    Cached CSVs are re-fetched automatically once they exceed cache_max_age_hours.
    """

    def __init__(self, token: str, source: str, cache_dir: str,
                 cache_max_age_hours: float = 24.0) -> None:
        self.client: Garage61Client = Garage61Client(token=token)
        self.source: str = source  # "personal" | "team"
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_dir: str = cache_dir
        self.cache_max_age_s: float = cache_max_age_hours * 3600

    def get_fastest_lap_csv(self, car_name: str, track_name: str,
                            track_config: str) -> list[dict] | None:
        """Return telemetry rows for the fastest matching lap, served from cache when fresh.

        Each row is a dict keyed by the CSV header names.
        Returns None if no matching lap is found.
        """
        cache_key = hashlib.md5(
            f"{car_name}|{track_name}|{track_config}|{self.source}".encode()
        ).hexdigest()
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.csv")

        if os.path.exists(cache_path):
            if time.time() - os.path.getmtime(cache_path) < self.cache_max_age_s:
                return _read_csv(cache_path)

        lap_id = self._find_fastest_lap_id(car_name, track_name, track_config)
        if lap_id is None:
            return None

        csv_text: str = self.client.lap_csv(lap_id=lap_id)
        with open(cache_path, "w", newline="") as f:
            f.write(csv_text)
        return list(csv.DictReader(io.StringIO(csv_text)))

    def _find_fastest_lap_id(self, car_name: str, track_name: str,
                             track_config: str) -> str | None:
        """Query Garage61 for laps on this car/track and return the ID of the fastest."""
        params: dict = {"car": car_name, "track": track_name, "limit": 50}
        laps: list[dict] | None = self.client.laps(team=(self.source == "team"), **params)

        candidates: list[dict] = [
            lap for lap in (laps or [])
            if track_config.lower() in (lap.get("track_config") or "").lower()
        ] or (laps or [])

        if not candidates:
            return None

        fastest: dict = min(candidates, key=lambda l: l.get("lap_time", float("inf")))
        return fastest.get("id")


def _read_csv(path: str) -> list[dict]:
    """Read a CSV file and return rows as a list of dicts."""
    with open(path, newline="") as f:
        return list(csv.DictReader(f))
