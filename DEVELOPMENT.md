# Development

## Setup

```bash
git clone https://github.com/your-username/pyracing-coach
cd pyracing-coach
uv sync --extra build
```

Run directly:

```bash
uv run python src/main.py
```

## Project structure

```
src/
  main.py           — app entry point, GUI, poll loop
  config.py         — Config class + SCHEMA (single source of truth for all settings)
  coach.py          — coaching engine (reference-based audio logic)
  instinct.py       — reference-free coaching (lockups, wheelspin, coasting, etc.)
  iracing_reader.py — pyirsdk shared-memory wrapper
  ibt_reader.py     — .ibt file parser (reference lap extraction)
  reference_lap.py  — zone detection, signal processing
  smoothness.py     — input smoothness scoring
  audio.py          — non-blocking TTS via pyttsx3
  session_log.py    — per-session JSON logging
  report.py         — HTML/PDF session report generator
  settings_ui.py    — tabbed options dialog (auto-generated from SCHEMA)
config.toml         — default user settings (auto-copied to %APPDATA%)
pyracing-coach.spec — PyInstaller build spec
```

## Building the EXE locally (Windows only)

```bash
uv run pyinstaller pyracing-coach.spec
```

Output: `dist\pyracing-coach.exe`. Copy `config.toml` next to it before running.

> The spec bundles customtkinter assets and the pyttsx3 SAPI5 driver.
> PyInstaller must be run on Windows — cross-compilation is not supported.

## Windows Defender / SmartScreen

PyInstaller EXEs are unsigned by default and may be quarantined or blocked by Windows Defender.

**Unblock a single build (no admin required):**
```powershell
Unblock-File -Path .\dist\pyracing-coach.exe
```

**Permanently exclude your dist folder from Defender (run PowerShell as Administrator):**
```powershell
Add-MpPreference -ExclusionPath "$PWD\dist"
```

Release builds are self-signed via the CI workflow, which reduces quarantine likelihood.
For full SmartScreen trust (no "unknown publisher" prompt for end users), a commercial
code-signing certificate is required.

## Releasing

Releases are built automatically by GitHub Actions on tag push (`.github/workflows/release.yml`).
The workflow installs uv, runs `uv sync --extra build`, builds the EXE, and attaches it to a GitHub Release.

To cut a release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Tag format must start with `v`. Release notes are auto-generated from commits since the previous tag.

## Dependencies and licenses

| Package | License | Notes |
|---|---|---|
| pyirsdk | MIT | iRacing shared-memory reader + .ibt parser |
| customtkinter | MIT | GUI |
| pyttsx3 | MPL-2.0 | TTS — used unmodified |
| tomllib | PSF (stdlib) | TOML parser |

Optional:
| weasyprint | BSD | PDF report generation (not bundled) |

pyracing-coach is MIT licensed. MPL-2.0 (pyttsx3) only requires modifications to pyttsx3's
own source to remain open — it does not affect this project's license.
