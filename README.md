# Owl-Bot

USB にコピーするだけで、**オフライン・CPU のみ**でローカル LLM チャットが使える Windows 向けツールです。  
[Local LLM Notepad](https://github.com/runzhouye/Local_LLM_Notepad) をベースに、**Gemma 4 E2B** 向けにカスタマイズしたフォークです。

**管理リポジトリ:** [matrix9neonebuchadnezzar2199-sketch/Local_LLM_Notepad](https://github.com/matrix9neonebuchadnezzar2199-sketch/Local_LLM_Notepad)

## 特徴

- インストール不要・インターネット不要・GPU 不要
- 会話は PC 内だけで完結（クラウド API 不使用）
- 日本語 UI（メニュー・ダイアログ・About）
- 既定モデル: **Gemma 4 E2B**（`gemma-4-E2B-it-Q4_K_M.gguf`）
- CPU 推論・軽量動作優先（`llama-cpp-python` 0.3.32 / `gemma4` アーキ対応）
- プロンプト内の語句を応答内で強調表示（Ctrl+クリックで出典プロンプトを追跡）

## 配布フォルダ構成

```
Owl-Bot/
  Owl-Bot.exe
  model/
    gemma-4-E2B-it-Q4_K_M.gguf
```

`Owl-Bot` フォルダごと USB や任意の場所に置いて、`Owl-Bot.exe` を起動してください。  
GGUF は EXE に同梱せず、`model/` から直接読み込みます（起動のたびに 3 GB を TEMP へ展開しません）。

## ダウンロード（Releases）

| ファイル | 内容 |
|----------|------|
| **Owl-Bot-v1.0.0-exe.zip** | `Owl-Bot.exe` と `model/` フォルダ（モデル入手手順付き） |
| **モデル GGUF** | [unsloth/gemma-4-E2B-it-GGUF](https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF) から `gemma-4-E2B-it-Q4_K_M.gguf` を `model/` に配置 |

> GitHub の 1 ファイル上限（2 GB）のため、約 3 GB の GGUF 本体は Releases には含めません。EXE と手順書を配布し、モデルは Hugging Face から取得してください。

## クイックスタート

1. Releases から `Owl-Bot-v1.0.0-exe.zip` を取得して展開
2. `model/` に `gemma-4-E2B-it-Q4_K_M.gguf` を置く（未同梱の場合）
3. `Owl-Bot.exe` をダブルクリック
4. 下部の入力欄に質問を書き、**送信** または **Ctrl+S**

ウィンドウタイトルは `Owl-Bot（読み込んだモデル名）` と表示されます。

## 動作環境

| 項目 | 目安 |
|------|------|
| OS | Windows 10/11 x64 |
| メモリ | 約 2 GB 以上（モデル読み込み時） |
| GPU | 不要（CPU のみ） |
| ネットワーク | 不要（初回モデル取得時のみ必要） |

## ショートカット

| 操作 | キー |
|------|------|
| 送信 | Ctrl+S |
| 生成停止 | Ctrl+Z |
| 検索 | Ctrl+F |
| 履歴クリア | Ctrl+X |
| システムプロンプト編集 | Ctrl+P |
| 語句強調の切替 | Ctrl+D |
| 拡大 / 縮小 | Ctrl+ホイール |

## ビルド（開発者向け）

詳細は [BUILD.md](BUILD.md) を参照。

```powershell
cd Owl-Bot
.\.venv\Scripts\pip install -r requirements.txt
cd Notepad
.\build.ps1
# → Notepad/dist/Owl-Bot/ に EXE + model/ が揃う
```

## 変更履歴（フォーク）

| バージョン | 概要 |
|------------|------|
| **v1.0.0** | Gemma 4 E2B 対応、`model/` 配布構成、日本語 UI、DPI/フォント改善 |

## クレジット

- ベース: [Local LLM Notepad](https://github.com/runzhouye/Local_LLM_Notepad) by Run Zhou Ye
- モデル: [Google Gemma 4](https://ai.google.dev/gemma) / [Unsloth GGUF](https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF)
- 推論: [llama.cpp](https://github.com/ggml-org/llama.cpp) / [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)

## ライセンス

ベースプロジェクトの LICENSE を継承。Gemma モデルは [Gemma 利用規約](https://ai.google.dev/gemma/terms) に従ってください。
