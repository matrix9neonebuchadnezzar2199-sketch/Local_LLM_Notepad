# Build Owl-Bot.exe (app only) and assemble dist/Owl-Bot/ distribution folder.
$ErrorActionPreference = "Stop"
$env:TEMP = "C:\t"
$env:TMP = "C:\t"

$ModelRel = "models\gemma-4-E2B-it-Q4_K_M.gguf"
$DistRoot = "dist\Owl-Bot"
$IconSrc = "..\Images\7tkhqJx7.png"
$Python = "..\.venv\Scripts\python.exe"
$PyInstaller = "..\.venv\Scripts\pyinstaller.exe"

& $Python "ensure_icon.py" $IconSrc
if (-not (Test-Path "Owl-Bot.ico")) {
    throw "Owl-Bot.ico was not generated. Check $IconSrc"
}

& $PyInstaller `
    --onefile `
    --noconsole `
    --additional-hooks-dir=. `
    --name Owl-Bot `
    --icon "Owl-Bot.ico" `
    --add-data "Owl-Bot.png;." `
    --add-data "Owl-Bot.ico;." `
    --clean `
    main.py

New-Item -ItemType Directory -Force -Path "$DistRoot\model" | Out-Null
Copy-Item -Force "dist\Owl-Bot.exe" "$DistRoot\Owl-Bot.exe"
Copy-Item -Force "Owl-Bot.png" "$DistRoot\Owl-Bot.png"
$ReadmeSrc = "..\packaging\model\README.txt"
if (Test-Path $ReadmeSrc) {
    Copy-Item -Force $ReadmeSrc "$DistRoot\model\README.txt"
}

if (Test-Path $ModelRel) {
    Copy-Item -Force $ModelRel "$DistRoot\model\"
    Write-Host "Done: $DistRoot\ (Owl-Bot.exe + model\*.gguf)"
} else {
    Write-Warning "Model not found at $ModelRel — copy GGUF into $DistRoot\model\ manually."
    Write-Host "Done: $DistRoot\Owl-Bot.exe (model folder empty)"
}
