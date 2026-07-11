$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $Root

py -3.12 -m venv .venv-build
& .\.venv-build\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-build\Scripts\pip.exe install -r requirements.txt pyinstaller
& .\.venv-build\Scripts\python.exe -m unittest discover -s tests -v

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
Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/osd.traineddata" -OutFile "$Tessdata\osd.traineddata"

& .\.venv-build\Scripts\pyinstaller.exe --noconfirm --clean build\windows\app.spec

if (-not (Test-Path "C:\Program Files (x86)\Inno Setup 6\ISCC.exe")) {
    choco install innosetup --yes --no-progress
}
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build\windows\installer.iss

Get-FileHash dist-installer\*.exe -Algorithm SHA256

