# -*- mode: python ; coding: utf-8 -*-
# Especificación PyInstaller de VeniceMAGI: consola (el REPL es el producto).
# Playwright necesita SU PAQUETE ENTERO (con el driver de Node que lanza Edge):
# en PYZ su __file__ no apunta a ficheros reales y el driver no se encuentra.
from PyInstaller.utils.hooks import collect_all

_pw_datas, _pw_bins, _pw_hidden = collect_all('playwright')

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=_pw_bins,
    datas=_pw_datas,
    hiddenimports=_pw_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PySide6', 'PyQt5', 'IPython', 'jedi',
              'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VeniceMAGI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # REPL de consola: la consola ES la interfaz
    disable_windowed_traceback=False,
)
