# Build Owl-Bot.exe (app only) and assemble dist/Owl-Bot/ distribution folder.
$ErrorActionPreference = "Stop"
$env:TEMP = "C:\t"
$env:TMP = "C:\t"

$ModelRel = "models\gemma-4-E2B-it-Q4_K_M.gguf"
$DistRoot = "dist\Owl-Bot"

$PyInstaller = "..\.venv\Scripts\pyinstaller.exe"
& $PyInstaller `
    --onefile `
    --noconsole `
    --additional-hooks-dir=. `
    --name Owl-Bot `
    --clean `
    main.py

New-Item -ItemType Directory -Force -Path "$DistRoot\model" | Out-Null
Copy-Item -Force "dist\Owl-Bot.exe" "$DistRoot\Owl-Bot.exe"

if (Test-Path $ModelRel) {
    Copy-Item -Force $ModelRel "$DistRoot\model\"
    Write-Host "Done: $DistRoot\ (Owl-Bot.exe + model\*.gguf)"
} else {
    Write-Warning "Model not found at $ModelRel — copy GGUF into $DistRoot\model\ manually."
    Write-Host "Done: $DistRoot\Owl-Bot.exe (model folder empty)"
}
