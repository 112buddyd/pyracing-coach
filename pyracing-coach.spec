# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller pyracing-coach.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        # Bundle config.toml so first-run users get a template
        ("config.toml", "."),
        # customtkinter ships its own theme assets
        (
            str(Path(sys.prefix) / "Lib/site-packages/customtkinter"),
            "customtkinter",
        ),
    ],
    hiddenimports=[
        "pyttsx3.drivers",
        "pyttsx3.drivers.sapi5",  # Windows SAPI
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pandas", "numpy", "matplotlib"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="pyracing-coach",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # add an .ico path here if you have one
)
