$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $Root

py -3.12 -m venv .venv-build
& .\.venv-build\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-build\Scripts\pip.exe install -r requirements.txt pyinstaller

# RapidOCR声明依赖桌面版OpenCV；安装包没有imshow等窗口需求，改用较小的headless构建。
& .\.venv-build\Scripts\pip.exe uninstall -y opencv-python opencv-python-headless
& .\.venv-build\Scripts\pip.exe install --no-cache-dir --no-deps opencv-python-headless==4.12.0.88

& .\.venv-build\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv-build\Scripts\python.exe -c "from rapidocr import RapidOCR; import numpy as np; e=RapidOCR(); e(np.full((96,512,3),255,dtype=np.uint8)); print('RapidOCR offline self-test passed')"
if ($LASTEXITCODE -ne 0) { throw "RapidOCR offline self-test failed" }

& .\.venv-build\Scripts\pyinstaller.exe --noconfirm --clean build\windows\app.spec

$RapidFiles = Get-ChildItem "dist\OfflinePersonnelVerifier\_internal" -Recurse -Include *.onnx
if ($RapidFiles.Count -lt 3) { throw "Bundled RapidOCR ONNX models are missing" }
$OrtFiles = Get-ChildItem "dist\OfflinePersonnelVerifier\_internal" -Recurse -Include onnxruntime*.dll
if ($OrtFiles.Count -lt 1) { throw "Bundled ONNX Runtime is missing" }
if (Get-ChildItem "dist\OfflinePersonnelVerifier" -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "tesseract|traineddata" }) {
    throw "Obsolete Tesseract files were unexpectedly bundled"
}

if (-not (Test-Path "C:\Program Files (x86)\Inno Setup 6\ISCC.exe")) {
    choco install innosetup --yes --no-progress
}
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build\windows\installer.iss

Get-FileHash dist-installer\*.exe -Algorithm SHA256
