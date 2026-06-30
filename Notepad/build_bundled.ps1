# Build single-file Owl-Bot.exe with embedded Gemma 4 E2B GGUF.
$ErrorActionPreference = "Stop"
$env:TEMP = "C:\t"
$env:TMP = "C:\t"

$ModelRel = "models\gemma-4-E2B-it-Q4_K_M.gguf"
if (-not (Test-Path $ModelRel)) {
    Write-Error "Missing $ModelRel — download first (see BUILD.md)."
}

$PyInstaller = "..\.venv\Scripts\pyinstaller.exe"
& $PyInstaller `
    --onefile `
    --noconsole `
    --additional-hooks-dir=. `
    --name Owl-Bot `
    --add-data "${ModelRel};models" `
    --clean `
    main.py

Write-Host "Done: dist\Owl-Bot.exe (model embedded)"
