# Owl-Bot v1.0.0

## 配布物

| アセット | 説明 |
|----------|------|
| `Owl-Bot-v1.0.0-exe.zip` | `Owl-Bot/Owl-Bot.exe` + `Owl-Bot/model/README.txt` |
| モデル（別途） | [gemma-4-E2B-it-Q4_K_M.gguf](https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF) を `model/` に配置 |

GGUF（約 3 GB）は GitHub Releases の 2 GB 上限のため同梱していません。

## 完成 dist のローカルパス（ビルド後）

```
Notepad/dist/Owl-Bot/
  Owl-Bot.exe
  model/
    gemma-4-E2B-it-Q4_K_M.gguf   # ビルド環境で models/ からコピー
    README.txt
```

## 主な機能

- Gemma 4 E2B（Q4_K_M）CPU チャット
- 日本語 UI・送信ボタン・プロンプト欄の視覚区分
- `model/` 直読み（大容量 TEMP 展開なし）
- Windows 高 DPI 対応・UI フォント改善
