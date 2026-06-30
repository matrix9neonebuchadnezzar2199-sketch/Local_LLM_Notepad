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

## Build EXE

```powershell
cd Notepad
$env:TEMP = "C:\t"; $env:TMP = "C:\t"
..\.venv\Scripts\pyinstaller.exe --onefile --noconsole --additional-hooks-dir=. --name Owl-Bot main.py
```

Output: `Notepad/dist/Owl-Bot.exe` (~50 MB). Model is **not** embedded.

## Model (Gemma 4 E2B Q4_K_M)

```powershell
.\.venv\Scripts\pip install huggingface_hub
.\.venv\Scripts\python.exe -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='unsloth/gemma-4-E2B-it-GGUF', filename='gemma-4-E2B-it-Q4_K_M.gguf', local_dir='Notepad/models')"
```

Place `gemma-4-E2B-it-Q4_K_M.gguf` next to `Owl-Bot.exe` or use **File → Select Model**.

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
