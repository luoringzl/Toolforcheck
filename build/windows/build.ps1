$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $Root

py -3.12 -m venv .venv-build
& .\.venv-build\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-build\Scripts\pip.exe install -r requirements.txt pyinstaller
& .\.venv-build\Scripts\python.exe -m unittest discover -s tests -v
# 初始化主OCR，确保中文检测、分类、识别模型在构建机上可离线加载。
& .\.venv-build\Scripts\python.exe -c "from rapidocr import RapidOCR; import numpy as np; e=RapidOCR(); e(np.full((96,512,3),255,dtype=np.uint8)); print('RapidOCR offline self-test passed')"
if ($LASTEXITCODE -ne 0) { throw "RapidOCR offline self-test failed" }

$Vendor = Join-Path $Root "build\windows\vendor\tesseract"
if (Test-Path $Vendor) { Remove-Item -Recurse -Force $Vendor }
New-Item -ItemType Directory -Force -Path $Vendor | Out-Null

$TesseractInstall = "C:\Program Files\Tesseract-OCR"
if (-not (Test-Path "$TesseractInstall\tesseract.exe")) {
    choco install tesseract --yes --no-progress
}
Copy-Item "$TesseractInstall\*" $Vendor -Recurse -Force

$Tessdata = Join-Path $Vendor "tessdata"
Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/chi_sim.traineddata" -OutFile "$Tessdata\chi_sim.traineddata"
Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata" -OutFile "$Tessdata\eng.traineddata"
Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/osd.traineddata" -OutFile "$Tessdata\osd.traineddata"

& .\.venv-build\Scripts\pyinstaller.exe --noconfirm --clean build\windows\app.spec

$BundledTesseract = Join-Path $Root "dist\OfflinePersonnelVerifier\_internal\tesseract"
if (Test-Path $BundledTesseract) { Remove-Item -Recurse -Force $BundledTesseract }
New-Item -ItemType Directory -Force -Path $BundledTesseract | Out-Null
Copy-Item "$Vendor\*" $BundledTesseract -Recurse -Force

$RequiredModels = @("chi_sim.traineddata", "eng.traineddata", "osd.traineddata")
foreach ($Model in $RequiredModels) {
    $ModelPath = Join-Path $BundledTesseract "tessdata\$Model"
    if (-not (Test-Path $ModelPath)) { throw "Missing bundled OCR model: $ModelPath" }
}
$env:TESSDATA_PREFIX = Join-Path $BundledTesseract "tessdata"
& "$BundledTesseract\tesseract.exe" --list-langs
if ($LASTEXITCODE -ne 0) { throw "Bundled Tesseract language self-test failed" }

# RapidOCR包必须把ONNX模型和onnxruntime动态库一并收集到_internal。
$RapidFiles = Get-ChildItem "dist\OfflinePersonnelVerifier\_internal" -Recurse -Include *.onnx
if ($RapidFiles.Count -lt 2) { throw "Bundled RapidOCR ONNX models are missing" }
$OrtFiles = Get-ChildItem "dist\OfflinePersonnelVerifier\_internal" -Recurse -Include onnxruntime*.dll
if ($OrtFiles.Count -lt 1) { throw "Bundled ONNX Runtime is missing" }

if (-not (Test-Path "C:\Program Files (x86)\Inno Setup 6\ISCC.exe")) {
    choco install innosetup --yes --no-progress
}
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build\windows\installer.iss

Get-FileHash dist-installer\*.exe -Algorithm SHA256
