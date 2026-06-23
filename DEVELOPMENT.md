# Development

## Setup

```bash
git clone https://github.com/your-username/pyracing-coach
cd pyracing-coach
python -m venv .venv
.venv\Scripts\activate        # Windows
python -m pip install --upgrade pip setuptools
pip install -e ".[build]" --no-build-isolation
```

Copy `config.toml` and fill in your Garage61 token, then run:

```bash
python src/main.py
```

## Project structure

```
src/
  main.py           — app entry point, GUI, poll loop
  coach.py          — coaching engine (all audio logic)
  iracing_reader.py — pyirsdk shared-memory wrapper
  garage61.py       — Garage61 API client + disk cache
  reference_lap.py  — CSV parsing, zone detection
  smoothness.py     — input smoothness scoring
  audio.py          — non-blocking TTS via pyttsx3
  session_log.py    — per-session JSON logging
  oauth.py          — Garage61 OAuth2 flow (local callback server)
config.toml         — all user-facing settings
pyracing-coach.spec — PyInstaller build spec
```

## Building the EXE locally (Windows only)

```bash
.venv\Scripts\activate
pyinstaller pyracing-coach.spec
```

Output: `dist/pyracing-coach.exe`. Copy `config.toml` next to it before running.

> The spec bundles customtkinter assets and the pyttsx3 SAPI5 driver.
> PyInstaller must be run on Windows — cross-compilation is not supported.

## Releasing

Releases are built automatically by GitHub Actions on tag push (`.github/workflows/release.yml`).
The workflow runs on `windows-latest`, builds the EXE, and attaches it to a GitHub Release.

To cut a release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Tag format must start with `v`. Release notes are auto-generated from commits since the previous tag.

## Dependencies and licenses

| Package | License | Notes |
|---|---|---|
| pyirsdk | MIT | iRacing shared-memory reader |
| garage61api | MIT | Garage61 API wrapper |
| customtkinter | MIT | GUI |
| pyttsx3 | MPL-2.0 | TTS — used unmodified |
| requests | Apache-2.0 | HTTP client |
| tomllib | PSF (stdlib) | TOML parser |

pyracing-coach is MIT licensed. MPL-2.0 (pyttsx3) only requires modifications to pyttsx3's
own source to remain open — it does not affect this project's license.
