# Owl-Bot build (Gemma 4 E2B)

Fork of [Local LLM Notepad](https://github.com/runzhouye/Local_LLM_Notepad) for portable Windows chat with **Gemma 4 E2B** GGUF.

## Distribution layout

```
Owl-Bot/
  Owl-Bot.exe
  model/
    gemma-4-E2B-it-Q4_K_M.gguf
```

Copy the whole `Owl-Bot` folder to a USB stick. No `%TEMP%` model extraction — GGUF is read directly from `model/`.

PyInstaller onefile still unpacks the small app runtime (~30 MB) to `%TEMP%` on each launch; only the LLM weights stay on the USB beside the EXE.

## Verified stack (2026-06-30)

| Component | Version |
|-----------|---------|
| Python | 3.12.12 |
| llama-cpp-python | 0.3.32 |
| llama-cpp-agent | 0.2.35 |
| PyInstaller | 6.21.0 |

## Prerequisites

- Windows 10/11 x64
- Python 3.10–3.12 (3.12 recommended)
- Visual Studio 2019+ Build Tools — only if building `llama-cpp-python` from source
- Short `TEMP` path if sdist extract fails (`C:\t`)

## Setup

```powershell
cd H:\CURSOR\Owl-Bot
$py312 = "C:\Users\owner\AppData\Roaming\uv\python\cpython-3.12.12-windows-x86_64-none\python.exe"
& $py312 -m venv .venv
$env:TEMP = "C:\t"; $env:TMP = "C:\t"
.\.venv\Scripts\pip install -r requirements.txt
```

## Download model (build / dev)

```powershell
.\.venv\Scripts\pip install huggingface_hub
.\.venv\Scripts\python.exe -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='unsloth/gemma-4-E2B-it-GGUF', filename='gemma-4-E2B-it-Q4_K_M.gguf', local_dir='Notepad/models')"
```

## Build distribution folder

```powershell
cd Notepad
$env:TEMP = "C:\t"; $env:TMP = "C:\t"
.\build.ps1
```

Output: `Notepad/dist/Owl-Bot/` — ready to zip or copy as-is.

## Smoke test (headless, dev)

```powershell
cd Notepad
..\.venv\Scripts\python.exe verify_gemma4.py
```

Uses `Notepad/models/*.gguf` during development; frozen EXE uses `model/` next to `Owl-Bot.exe`.

## Runtime defaults

- Default model: `model/gemma-4-E2B-it-Q4_K_M.gguf`
- `n_ctx`: 4096, `max_tokens`: 2048
- CPU-only (`n_gpu_layers=0`)
- **File → Select Model** overrides the default

## UI notes (v1.0.0)

- Japanese menus and About dialog
- Prompt panel: light navy background + Send button
- Window title: `Owl-Bot（model-name）`
- Windows: Per-Monitor DPI awareness + Yu Gothic UI / Meiryo UI fonts (reduces blurry text on 125%+ scaling)
