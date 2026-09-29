# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src/qc_inspector/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/qc_inspector/assets', 'assets'),
        ('src/qc_inspector/main-icon.png', '.'),
        ('src/qc_inspector/ISTRUZIONI_USO.md', '.'),
        ('LICENSE', '.'),
        ('NOTICE.md', '.'),
        ('THIRD_PARTY_NOTICES.md', '.'),
        ('third_party/licenses', 'third_party/licenses'),
    ],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name='qc-inspector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['src/qc_inspector/main-icon.png'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='qc-inspector',
)
