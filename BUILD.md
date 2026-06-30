# Owl-Bot build (Gemma 4 E2B)

Fork of [Local LLM Notepad](https://github.com/runzhouye/Local_LLM_Notepad) for portable Windows EXE with **Gemma 4 E2B** GGUF support.

## Verified stack (2026-06-30)

| Component | Version |
|-----------|---------|
| Python | 3.12.12 |
| llama-cpp-python | 0.3.32 |
| llama-cpp-agent | 0.2.35 |
| PyInstaller | 6.21.0 |

`llama-cpp-python` 0.3.32 bundles a llama.cpp revision with `gemma4` architecture support.

## Prerequisites

- Windows 10/11 x64
- Python 3.10–3.12 (3.12 recommended)
- Visual Studio 2019+ Build Tools (C++ desktop workload) — required when building `llama-cpp-python` from source
- Short `TEMP` path if sdist extract fails on Windows (`C:\t`)

## Setup

```powershell
cd H:\CURSOR\Owl-Bot
$py312 = "C:\Users\owner\AppData\Roaming\uv\python\cpython-3.12.12-windows-x86_64-none\python.exe"
& $py312 -m venv .venv
$env:TEMP = "C:\t"; $env:TMP = "C:\t"
.\.venv\Scripts\pip install -r requirements.txt
```

## Build EXE (model embedded — single file)

Download the GGUF once, then bundle it into the EXE:

```powershell
# 1) Model (skip if already in Notepad/models/)
.\.venv\Scripts\pip install huggingface_hub
.\.venv\Scripts\python.exe -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='unsloth/gemma-4-E2B-it-GGUF', filename='gemma-4-E2B-it-Q4_K_M.gguf', local_dir='Notepad/models')"

# 2) Build
cd Notepad
$env:TEMP = "C:\t"; $env:TMP = "C:\t"
.\build_bundled.ps1
```

Output: `Notepad/dist/Owl-Bot.exe` (~3.0 GB). **No separate GGUF required** — model is inside the EXE.

PyInstaller onefile extracts the bundle to `%TEMP%` on each launch (~3 GB free temp space needed). First start may take 30–60s while extracting.

Manual equivalent:

```powershell
..\.venv\Scripts\pyinstaller.exe --onefile --noconsole --additional-hooks-dir=. --name Owl-Bot `
  --add-data "models\gemma-4-E2B-it-Q4_K_M.gguf;models" --clean main.py
```

**File → Select Model** still works to override the bundled weights.

## Smoke test (headless)

```powershell
cd Notepad
..\.venv\Scripts\python.exe verify_gemma4.py
```

Verified on this machine: model load OK, Japanese reply OK, RSS ~2.7 GB with `n_ctx=4096`.

## Runtime defaults (Owl-Bot fork)

- Default model filename: `gemma-4-E2B-it-Q4_K_M.gguf`
- `n_ctx`: 4096
- `max_tokens`: 2048
- CPU-only (`n_gpu_layers=0`)
