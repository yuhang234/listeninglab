# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ListeningLab.

Builds a single-file executable bundling the app, the web frontend and
all built-in papers with audio, so the result runs fully offline on a
machine without Python.

Usage (from the repository root or anywhere):
    pyinstaller packaging/listeninglab.spec --noconfirm

Output: dist/ListeningLab(.exe)
"""
import os

# SPECPATH is the directory containing this spec file.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "web"), "web"),
        (os.path.join(ROOT, "content", "papers"), os.path.join("content", "papers")),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ListeningLab",
    debug=False,
    strip=False,
    upx=False,
    console=True,  # keep a console window so run status is visible
)
