# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

project = Path(SPECPATH).parent.parent
tesseract = project / "build" / "windows" / "vendor" / "tesseract"

datas = []
binaries = []
hiddenimports = ["tkinter", "fitz", "docx", "openpyxl", "PIL", "numpy"]
if tesseract.exists():
    datas.append((str(tesseract), "tesseract"))

# RapidOCR的ONNX模型和onnxruntime本机动态库必须随安装包复制，
# 否则源码环境可用、打包后会退化为“未提取到可用文字”。
for package in ("rapidocr", "onnxruntime"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [str(project / "app.py")],
    pathex=[str(project)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="OfflinePersonnelVerifier",
)
