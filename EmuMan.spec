# -*- mode: python ; coding: utf-8 -*-
import shutil
import sys
import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('resources', 'resources')],
    hiddenimports=['PySide6', 'qfluentwidgets', 'app', 'requests'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scipy', 'numpy', 'pandas', 'matplotlib', 'tkinter', 'unittest', 'xmlrpc', 'pdb', 'doctest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Define Aria2 Path based on OS
aria2_filename = 'aria2c.exe' if sys.platform == 'win32' else 'aria2c'
aria2_path = os.path.join('resources', 'bin', aria2_filename)
aria2_binary = []

if os.path.exists(aria2_path):
    # Bundle it to the root of the frozen app (sys._MEIPASS/aria2c)
    aria2_binary = [(aria2_filename, aria2_path, 'BINARY')]

exe = EXE(
    pyz,
    a.scripts,
    a.binaries + aria2_binary,
    a.zipfiles,
    a.datas,
    [],
    name='EmuMan',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=(sys.platform == 'win32'),
    upx_exclude=['_uuid.pyd', 'vcruntime140.dll', 'python3.dll', 'python312.dll'],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/logo.ico'
)
