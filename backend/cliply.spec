# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec untuk Cliply backend
# Build: pyinstaller cliply.spec

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
        # uvicorn internals
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # fastapi / starlette
        'fastapi',
        'fastapi.middleware.cors',
        'starlette',
        'starlette.middleware',
        'starlette.middleware.cors',
        'sse_starlette',
        'sse_starlette.sse',
        # config / env
        'dotenv',
        'python_dotenv',
        # storage / networking
        'redis',
        'redis.asyncio',
        'requests',
        # AI APIs
        'openai',
        'anthropic',
        'google.generativeai',
        'google.ai.generativelanguage',
        # video / audio
        'yt_dlp',
        'cv2',
        'mediapipe',
        'numpy',
        'scenedetect',
        'scenedetect.detectors',
        # youtube transcript
        'youtube_transcript_api',
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
