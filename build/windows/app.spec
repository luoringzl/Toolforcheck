# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path(SPECPATH).parent.parent
tesseract = project / "build" / "windows" / "vendor" / "tesseract"

datas = []
if tesseract.exists():
    datas.append((str(tesseract), "tesseract"))

a = Analysis(
    [str(project / "app.py")],
    pathex=[str(project)],
    binaries=[],
    datas=datas,
    hiddenimports=["tkinter", "fitz", "docx", "openpyxl", "PIL", "numpy"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "matplotlib", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OfflinePersonnelVerifier",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="核验工具",
)
