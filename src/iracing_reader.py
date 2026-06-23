"""Live iRacing telemetry via pyirsdk."""
import irsdk


class IRacingReader:
    """Wraps the iRacing SDK shared-memory interface.

    Provides session metadata (car, track) and per-tick telemetry
    including inputs, speed, lap progress, and temperatures.
    """

    def __init__(self) -> None:
        self.ir: irsdk.IRSDK = irsdk.IRSDK()
        self._connected: bool = False

    def connect(self) -> bool:
        """Attempt to attach to a running iRacing session. Returns True on success."""
        self._connected = self.ir.startup()
        return self._connected

    def disconnect(self) -> None:
        """Detach from the iRacing shared memory."""
        self.ir.shutdown()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """True if the SDK is attached and iRacing is running."""
        return self._connected and self.ir.is_connected

    def get_session_info(self) -> dict:
        """Return car and track identifiers for the current session.

        Keys: car_name, track_name, track_config, track_length_m.
        Returns an empty dict if not connected.
        """
        if not self.is_connected:
            return {}
        drivers = self.ir["DriverInfo"]["Drivers"]
        idx: int = self.ir["PlayerCarIdx"]
        return {
            "car_name":       drivers[idx]["CarScreenName"],
            "track_name":     self.ir["WeekendInfo"]["TrackDisplayName"],
            "track_config":   self.ir["WeekendInfo"]["TrackConfigName"],
            "track_length_m": _parse_track_length(self.ir["WeekendInfo"].get("TrackLength", "")),
        }

    def get_telemetry(self) -> dict | None:
        """Return a snapshot of current driver inputs and vehicle state.

        Keys: lap_dist_pct, brake, throttle, gear, speed, lap, lap_time,
        last_lap_time, best_lap_time, steering_angle, yaw_rate,
        tyre_temp_{lf,rf,lr,rr}, brake_temp_{lf,rf}.
        Returns None if not connected.
        """
        if not self.is_connected:
            return None
        self.ir.freeze_var_buffer_latest()
        return {
            "lap_dist_pct":   self.ir["LapDistPct"],
            "brake":          self.ir["Brake"],
            "throttle":       self.ir["Throttle"],
            "gear":           self.ir["Gear"],
            "speed":          self.ir["Speed"],
            "lap":            self.ir["Lap"],
            "lap_time":       self.ir["LapCurrentLapTime"],
            "last_lap_time":  self.ir["LapLastLapTime"],
            "best_lap_time":  self.ir["LapBestLapTime"],
            "steering_angle": self.ir["SteeringWheelAngle"],
            "yaw_rate":       self.ir["YawRate"],
            "tyre_temp_lf":   _mid(self.ir["LFtempCM"]),
            "tyre_temp_rf":   _mid(self.ir["RFtempCM"]),
            "tyre_temp_lr":   _mid(self.ir["LRtempCM"]),
            "tyre_temp_rr":   _mid(self.ir["RRtempCM"]),
            "brake_temp_lf":  self.ir["LFbrakeLinePress"],
            "brake_temp_rf":  self.ir["RFbrakeLinePress"],
        }


def _mid(val: object) -> float | None:
    """Return the middle (index 1) value from a 3-element sequence, or None."""
    try:
        return val[1]  # type: ignore[index]
    except (TypeError, IndexError):
        return None


def _parse_track_length(s: str) -> float:
    """Parse iRacing's '5.54 km' track-length string into metres. Falls back to 3000."""
    try:
        return float(s.strip().split()[0]) * 1000
    except Exception:
        return 3000.0
