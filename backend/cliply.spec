# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec untuk Cliply backend
# Build: pyinstaller cliply.spec
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['cliply_server.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Bundle folder app/ dan models/ ke dalam exe
        ('app', 'app'),
        ('models', 'models'),
    ],
    hiddenimports=[
        *collect_submodules("fastapi"),
        *collect_submodules("starlette"),
        *collect_submodules("uvicorn"),
        *collect_submodules("sse_starlette"),
        *collect_submodules("dotenv"),
        *collect_submodules("redis"),
        *collect_submodules("requests"),
        *collect_submodules("openai"),
        *collect_submodules("anthropic"),
        *collect_submodules("google.generativeai"),
        *collect_submodules("google.ai.generativelanguage"),
        *collect_submodules("yt_dlp"),
        *collect_submodules("cv2"),
        *collect_submodules("mediapipe"),
        *collect_submodules("numpy"),
        *collect_submodules("scenedetect"),
        *collect_submodules("youtube_transcript_api"),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude library besar yang tidak dipakai
    excludes=[
        'faster_whisper',
        'torch',
        'torchaudio',
        'torchvision',
        'tensorflow',
        'sklearn',
        'matplotlib',
        'pandas',
        'PIL',
        'tkinter',
        'PyQt5',
        'PyQt6',
        'wx',
    ],
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
    name='cliply_server',
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
    icon=None,
)
