# pyracing-coach

An iRacing audio coaching app for Windows. Connects to live telemetry, fetches your fastest
reference lap from Garage61, and coaches you in real time via spoken audio cues — no overlays,
no screen clutter.

## Features

- **Countdown cues** — "3… 2… 1… now" (or "lift") before every braking and lift zone
- **Post-zone critique** — "brake 75%, try for 100%" and "go full throttle 0.4s sooner"
- **Smoothness scoring** — per-zone and per-lap roughness vs reference, spoken at zone exit and lap end
- **Lap delta** — "0.4 up" / "0.2 down" spoken at a configurable interval mid-lap
- **Personal best** — announces new PBs with the lap time
- **Sector deltas** — spoken at configurable split points
- **Oversteer / understeer** — detected from yaw rate vs steering angle heuristic
- **Tyre and brake temp warnings** — cold/hot callouts per corner with configurable thresholds
- **Session log** — per-session JSON written after every lap (`session_logs/`)
- **Reference lap cache** — Garage61 CSVs cached locally, auto-refreshed after `cache_max_age_hours`
- **In-app Garage61 OAuth setup** — no manual token copy-paste required

## Requirements

- Windows 10/11
- iRacing running (the app reads iRacing's shared memory — no plugins needed)
- A [Garage61](https://garage61.net) account with at least one recorded lap on the car/track combo

## Installation (development)

```
pip install -e ".[build]"
```

Fill in `config.toml` — at minimum set `garage61.token` (or use the in-app Connect button).

## Build EXE

```
pyinstaller pyracing-coach.spec
```

Output: `dist/pyracing-coach.exe`. Copy `config.toml` next to the exe.

## Usage

1. Launch `pyracing-coach.exe`
2. Click **Connect Garage61…** if you haven't set a token yet (opens OAuth flow in browser)
3. Start iRacing and load into a session — the app detects car + track automatically
4. Once the reference lap loads, click **Start Coaching**

Modes (switchable in the UI without restarting):

| Mode | Behaviour |
|---|---|
| `learning` | Countdown cues only |
| `critique` | Post-zone debrief only |
| `both` | Countdown + debrief (default) |

Smoothness, delta, sectors, temp warnings, and PB announcements are always active.

## Configuration — config.toml

All behaviour is controlled by `config.toml`, stored at:

```
%APPDATA%\pyracing-coach\config.toml
```

On first launch the app copies the bundled default `config.toml` there automatically.
Session logs and the reference lap cache are also stored under `%APPDATA%\pyracing-coach\`.

### `[garage61]`
| Key | Default | Description |
|---|---|---|
| `token` | `""` | Garage61 API access token |
| `source` | `"personal"` | `"personal"` or `"team"` best lap |
| `cache_max_age_hours` | `24.0` | Re-fetch reference if cache is older than this |

### `[coaching]`
| Key | Default | Description |
|---|---|---|
| `lookahead_seconds` | `4.0` | How far ahead to start countdown |
| `countdown_steps` | `[3, 2, 1]` | Numbers spoken before the zone |
| `brake_cue` | `"now"` | Word spoken at the brake point |
| `lift_cue` | `"lift"` | Word spoken at a lift-only zone |
| `brake_threshold` | `0.5` | Min brake pressure to count as a zone |
| `lift_threshold` | `0.5` | Throttle must drop by this much to count as a lift zone |

### `[critique]`
| Key | Default | Description |
|---|---|---|
| `mode` | `"both"` | `"learning"`, `"critique"`, or `"both"` |
| `brake_min_delta` | `0.08` | Min brake gap before critique fires |
| `brake_template` | `"brake {actual}%, try for {target}%"` | Spoken template |
| `throttle_window_m` | `150` | Metres after zone to collect throttle data |
| `throttle_full_threshold` | `0.95` | Throttle level considered "full" |
| `throttle_late_template` | `"full throttle {delta}s sooner"` | |
| `throttle_early_template` | `"wait {delta}s before full throttle"` | |

### `[smoothness]`
| Key | Default | Description |
|---|---|---|
| `lap_report` | `true` | Speak smoothness at lap end |
| `zone_report` | `true` | Speak smoothness after each zone |
| `min_delta` | `0.10` | Minimum gap (0–1) before critique fires |

### `[delta]`
| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable mid-lap delta callouts |
| `interval_s` | `20.0` | Seconds of lap time between callouts |

### `[sectors]`
| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | Speak sector delta at each split |
| `splits` | `[0.33, 0.66]` | LapDistPct positions of sector boundaries |

### `[oversteer_understeer]`
| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | Detect and call out over/understeer |
| `threshold` | `0.3` | Yaw ratio deviation required to trigger |
| `wheelbase_m` | `2.7` | Your car's wheelbase in metres |
| `oversteer_cue` | `"oversteer"` | |
| `understeer_cue` | `"understeer"` | |

### `[temps]`
| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | Tyre and brake temp warnings |
| `tyre_cold_c` | `70.0` | Warn below this tyre temp (°C) |
| `tyre_hot_c` | `110.0` | Warn above this tyre temp (°C) |
| `brake_cold_c` | `150.0` | Warn below this brake temp (°C) |
| `brake_hot_c` | `900.0` | Warn above this brake temp (°C) |

### `[audio]`
| Key | Default | Description |
|---|---|---|
| `rate` | `175` | TTS words-per-minute |
| `volume` | `1.0` | Volume (0.0–1.0) |
| `voice_index` | `0` | System voice index |

### `[app]`
| Key | Default | Description |
|---|---|---|
| `poll_interval` | `0.05` | Telemetry poll interval in seconds |
| `cache_dir` | `"lap_cache"` | Directory for cached reference lap CSVs |
| `session_log_enabled` | `true` | Write per-session JSON logs |
| `log_dir` | `"session_logs"` | Directory for session log files |

## Session logs

Each session produces a JSON file at `session_logs/YYYYMMDD_HHMMSS_Car_Track.json`.
Structure:

```json
{
  "car": "...", "track": "...", "session_start": "...",
  "laps": [
    {
      "lap": 1,
      "lap_time_s": 102.431,
      "delta_s": -0.312,
      "personal_best": true,
      "smoothness_brake": 0.74,
      "smoothness_throttle": 0.81,
      "zones": [
        {
          "zone": 0, "type": "brake",
          "brake_actual_pct": 87, "brake_ref_pct": 100,
          "smoothness_brake": 0.71, "smoothness_throttle": 0.88
        }
      ]
    }
  ]
}
```

## Legal

pyracing-coach is released under the **MIT License** — see [LICENSE](LICENSE).

This app reads iRacing's publicly documented shared-memory SDK interface and queries only
your own lap data from Garage61 via their official API, in accordance with their Terms of
Service. It does not scrape, modify, or redistribute any licensed content.

Third-party dependency licenses are listed in [LICENSE](LICENSE).
