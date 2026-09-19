# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('data/knowledge.json', 'data')],
    hiddenimports=['cryptography.hazmat.backends.openssl', 'cryptography.hazmat.primitives.ciphers.aead', 'cryptography.hazmat.primitives.kdf.pbkdf2', 'dotenv'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['easyocr', 'pytesseract', 'torch', 'torchvision', 'torchaudio', 'cv2', 'scipy', 'matplotlib', 'pandas', 'pytest', '_pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='study-liu',
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
)
