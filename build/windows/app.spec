# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

project = Path(SPECPATH).parent.parent

# 只收集RapidOCR实际需要的配置、三套ONNX模型及ONNX Runtime动态库。
# 不再使用collect_all，避免把可选Paddle/PyTorch/OpenVINO后端一并分析。
datas = collect_data_files(
    "rapidocr", includes=["models/*.onnx", "*.yaml"]
) + collect_data_files("onnxruntime")
binaries = collect_dynamic_libs("onnxruntime")
hiddenimports = [
    "tkinter", "fitz", "docx", "openpyxl", "PIL", "numpy", "cv2",
    "onnxruntime",
] + collect_submodules("rapidocr")

a = Analysis(
    [str(project / "app.py")],
    pathex=[str(project)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "pytest", "matplotlib", "pandas", "torch", "paddle", "openvino",
        "tensorrt", "MNN", "IPython", "notebook",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="OfflinePersonnelVerifier", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=False,
    upx_exclude=[], name="OfflinePersonnelVerifier",
)
