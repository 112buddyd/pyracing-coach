# pyracing-coach

An iRacing audio coaching app for Windows. Load any `.ibt` telemetry file as a reference lap and get real-time spoken coaching — no overlays, no screen clutter.

## Features

### Reference-lap coaching (requires .ibt)
- **Countdown cues** — "3… 2… 1… now" (or "lift") before every braking and lift zone
- **Post-zone critique** — "brake 75%, try for 100%" and "go full throttle 0.4s sooner"
- **Smoothness scoring** — per-zone and per-lap roughness vs reference
- **Lap delta** — "0.4 up" / "0.2 down" spoken mid-lap at configurable intervals
- **Personal best** — announces new PBs with the lap time
- **Sector deltas** — spoken at configurable split points

### Reference-free coaching (always active)
- **Wheel lockup** — detects individual wheel lock under braking
- **Wheelspin** — detects rear wheel slip on throttle application
- **Coasting** — flags time lost with both pedals released
- **Throttle snap** — warns on harsh throttle application
- **Brake/throttle overlap** — detects both pedals pressed simultaneously
- **Trail braking quality** — analysis of brake release vs steering input correlation
- **Steering under braking** — flags high steering angle at peak brake pressure
- **Lateral G excess** — warns when cornering G exceeds threshold
- **Fuel management** — warns if fuel won't last to session end
- **Lap consistency** — speaks standard deviation of recent lap times

### Vehicle monitoring
- **Oversteer / understeer detection** — yaw rate vs steering angle heuristic
- **Tyre and brake temp warnings** — cold/hot callouts per corner

### Session reporting
- **Session log** — per-session JSON with all events, smoothness scores, and lap times
- **HTML/PDF report** — styled report with summary stats, event counts, per-lap detail, and prioritised improvement recommendations
- **Options UI** — all settings editable in-app without touching config files

## Reference lap

The reference lap is a local `.ibt` file — iRacing's native telemetry format, saved automatically to `Documents\iRacing\telemetry\` after every session.

- **Auto-load** — click "Auto-load from iRacing folder" to use the most recent `.ibt`
- **Manual load** — click "Load .ibt…" to browse for any `.ibt` (e.g. from a faster driver)
- **No reference needed** — instinct coaching and vehicle monitoring work without a loaded reference

The app extracts the fastest complete lap from the file and uses that as the reference.

## Requirements

- Windows 10/11
- iRacing running (reads shared memory — no plugins needed)

## Installation

```
pip install -e ".[build]"
```

Or with uv:

```
uv sync --extra build
```

## Build EXE

```
uv run pyinstaller pyracing-coach.spec
```

Output: `dist\pyracing-coach.exe`

## Usage

1. Launch `pyracing-coach.exe`
2. Click **Load .ibt…** or **Auto-load from iRacing folder** to set a reference lap (optional)
3. Start iRacing and load into a session
4. Click **Start Coaching**
5. Click **Generate Session Report…** after your session to see improvement tips
6. Click **Options…** to adjust any setting without editing files

Modes (switchable in the UI):

| Mode | Behaviour |
|---|---|
| `learning` | Countdown cues only |
| `critique` | Post-zone debrief only |
| `both` | Countdown + debrief (default) |

## Configuration

All settings are stored at `%APPDATA%\pyracing-coach\config.toml` (auto-created on first run).

Settings can be edited via the **Options…** button in the app — no need to edit the file manually.
All settings are defined in a central schema (`src/config.py`) which drives both defaults and the UI.

## Session reports

Click **Generate Session Report…** to open an HTML report of your most recent session.

The report includes:
- Lap count, best time, average time, smoothness scores
- Instinct event counts (lockups, wheelspin, coasting, etc.)
- Prioritised improvement tips based on your actual issues
- Per-lap table with times, deltas, smoothness, and events

To generate PDF instead of HTML, set `format = "pdf"` in Options → Report (requires `weasyprint`).

## Legal

Released under the **MIT License** — see [LICENSE](LICENSE).

Reads iRacing's publicly documented shared-memory SDK. Does not scrape, modify, or redistribute any licensed content.
