@echo off
REM Upload Owl-Bot v1.0.0 release assets (run after: gh auth login)
setlocal
cd /d "%~dp0Notepad\dist"
gh release create v1.0.0 ^
  --repo matrix9neonebuchadnezzar2199-sketch/Local_LLM_Notepad ^
  --title "Owl-Bot v1.0.0" ^
  --notes-file "..\..\RELEASE.md" ^
  Owl-Bot-v1.0.0-exe.zip ^
  Owl-Bot\Owl-Bot.exe
echo Done. Full dist with GGUF: copy Owl-Bot\ folder manually (GGUF exceeds GitHub 2GB limit).
