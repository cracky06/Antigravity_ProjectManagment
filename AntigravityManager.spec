# -*- mode: python ; coding: utf-8 -*-
"""Spécification PyInstaller versionnée pour Antigravity Manager.

Build : `.\Build-App.ps1` (qui appelle `pyinstaller AntigravityManager.spec`).

Allègements Qt6 appliqués ici (voir _drop) :
  - opengl32sw.dll (~20 Mo)  : rasterizer OpenGL logiciel, inutile (aucun OpenGL
    dans l'app) — le fallback software raster de Qt suffit.
  - Qt6/translations/*.qm (~6.7 Mo) : traductions des dialogues NATIFS Qt.
    On ne garde que qtbase_fr.qm (~40 Ko).
  - Qt6Pdf.dll (~4.5 Mo) : l'export PDF projet (pdf_export_html.py) imprime
    via Edge/Chrome headless, plus besoin du moteur PDF de Qt.
"""

import os

block_cipher = None

a = Analysis(
    ['antigravity_manager.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/icon.png', 'assets'),
        ('assets/icon.ico', 'assets'),
        ('assets/splash.jpg', 'assets'),
        # v2.5 : icônes du sélecteur de source (Antigravity clair/sombre, Claude)
        ('assets/antigravity_black.svg', 'assets'),
        ('assets/antigravity_white.svg', 'assets'),
        ('assets/claude.png', 'assets'),
        ('VERSION', '.'),
    ],
    # QtSvg : jamais importé dans le code Python, mais requis pour que QIcon
    # rende les .svg du sélecteur de source (plugin iconengines/qsvgicon).
    hiddenimports=['PyQt6.QtSvg'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets', 'PyQt6.QtPrintSupport'],
    noarchive=False,
    optimize=0,
)


def _drop(entries, predicate):
    return [e for e in entries if not predicate(e[0].replace('\\', '/'))]


# --- opengl32sw.dll : on le retire ---
a.binaries = _drop(a.binaries, lambda dest: dest.lower().endswith('opengl32sw.dll'))

# --- Qt6Pdf.dll : plus utilisé (export PDF via navigateur headless) ---
a.binaries = _drop(a.binaries, lambda dest: dest.lower().endswith('qt6pdf.dll'))

# --- translations Qt : ne garder que qtbase_fr.qm ---
def _is_extra_qm(dest: str) -> bool:
    d = dest.lower()
    return ('qt6/translations/' in d or d.startswith('translations/') or '/translations/' in d) \
        and d.endswith('.qm') and not d.endswith('qtbase_fr.qm')

a.binaries = _drop(a.binaries, _is_extra_qm)
a.datas = _drop(a.datas, _is_extra_qm)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AntigravityManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)
