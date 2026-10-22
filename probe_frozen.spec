# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['secrets', 'getpass', 'uuid', 'socket', 'select', 'decimal', 'base64', 'contextvars', 'queue', 'array', 'struct', 'copy', 'enum', 'functools', 'json', 'string', 'time', 'datetime', 'numbers', 'pickle', 'types', 'abc', 'keyword', 'token', 'xml', 'html']

# python-oracledb 1.4.x thin_impl is a Cython .pyd that does its imports via
# the C API (PyImport_Import) - invisible to PyInstaller's static analysis.
# crypto.pyx inside it needs EXACTLY these cryptography submodules; if any
# fails, HAS_CRYPTOGRAPHY is silently set False and every connect() dies with
# DPY-3016.  Belt and braces: the explicit list below PLUS every submodule.
CRYPTO_IMPORTS = [
    'cryptography',
    'cryptography.x509',
    'cryptography.hazmat.primitives.hashes',
    'cryptography.hazmat.primitives.serialization',
    'cryptography.hazmat.primitives.ciphers',
    'cryptography.hazmat.primitives.ciphers.algorithms',
    'cryptography.hazmat.primitives.ciphers.modes',
    'cryptography.hazmat.primitives.ciphers.aead',
    'cryptography.hazmat.primitives.asymmetric.padding',
    'cryptography.hazmat.primitives.kdf.pbkdf2',
]
hiddenimports += CRYPTO_IMPORTS
hiddenimports += collect_submodules('cryptography')


a = Analysis(
    ['probe_frozen.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='probe_frozen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
