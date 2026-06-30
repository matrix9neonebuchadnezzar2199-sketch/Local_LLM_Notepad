from __future__ import annotations

import json
import os
import queue
import re
import threading
from typing import List, Tuple

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog, ttk  # noqa: F401 – same imports kept

from llm_utils import DEFAULT_MODEL_FILENAME, get_model_dir, resolve_model_path, respond

__all__ = ["ChatGUI", "run_app"]

# 配色（上: 履歴 / 下: プロンプト）
_COLOR_HISTORY_BG = "#ffffff"
_COLOR_PROMPT_BG = "#dce6f2"  # 薄い紺
_COLOR_PROMPT_INPUT_BG = "#f4f7fb"
_COLOR_BORDER = "#3d5a80"
_COLOR_SEND_BG = "#3d5a80"
_COLOR_SEND_FG = "#ffffff"
_COLOR_SEND_ACTIVE = "#2c4260"
_APP_NAME = "Owl-Bot"


def _model_display_name(model_path: str) -> str:
    """GGUF ファイル名から表示用モデル名を得る。"""
    base = os.path.basename(model_path)
    if base.lower().endswith(".gguf"):
        return base[: -len(".gguf")]
    return base or "（モデル未設定）"


class ChatGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.configure(bg=_COLOR_HISTORY_BG)

        icon_path = "Icon.png"
        if os.path.exists(icon_path):
            try:
                icon = tk.PhotoImage(file=icon_path)
                root.iconphoto(True, icon)
            except Exception as ex:
                print(f"Icon load failed: {ex}")

        # ─────────────────── State ───────────────────
        self.system_prompt: str = "You are a helpful assistant."

        try:
            self.model_path = resolve_model_path(DEFAULT_MODEL_FILENAME)
        except FileNotFoundError:
            self.model_path = DEFAULT_MODEL_FILENAME
        self._update_window_title()

        # ─────────────────── Menus ───────────────────
        menubar = tk.Menu(root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="モデルを選択...", command=self.select_model)
        file_menu.add_command(label="会話を保存...", command=self.save_chat)
        file_menu.add_command(label="会話を読み込み...", command=self.load_chat)
        file_menu.add_separator()
        file_menu.add_command(label="終了", command=root.quit)
        menubar.add_cascade(label="ファイル", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="送信", accelerator="Ctrl+S", command=self.on_send)
        edit_menu.add_command(label="検索...", accelerator="Ctrl+F", command=self.open_find)
        edit_menu.add_separator()
        edit_menu.add_command(
            label="システムプロンプトを編集...",
            accelerator="Ctrl+P",
            command=self.edit_system_prompt,
        )
        edit_menu.add_separator()
        edit_menu.add_command(label="生成を停止", accelerator="Ctrl+Z", command=self.on_stop)
        edit_menu.add_command(label="履歴をクリア", accelerator="Ctrl+X", command=self.on_clear)
        edit_menu.add_separator()
        edit_menu.add_command(
            label="語句の強調表示を切替",
            accelerator="Ctrl+D",
            command=self.toggle_word_style,
        )
        menubar.add_cascade(label="編集", menu=edit_menu)

        format_menu = tk.Menu(menubar, tearoff=0)
        format_menu.add_command(label="折り返しの切替", command=self.toggle_wrap)
        menubar.add_cascade(label="書式", menu=format_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="拡大", accelerator="Ctrl++", command=self.zoom_in)
        view_menu.add_command(label="縮小", accelerator="Ctrl+-", command=self.zoom_out)
        menubar.add_cascade(label="表示", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="このツールについて", command=self.show_about)
        menubar.add_cascade(label="ヘルプ", menu=help_menu)
        root.config(menu=menubar)

        # ─────────────────── Layout ───────────────────
        style = ttk.Style()
        style.configure(
            "Plain.TPanedwindow",
            background=_COLOR_BORDER,
            borderwidth=0,
            relief="flat",
            sashwidth=6,
        )
        panes = ttk.PanedWindow(root, orient="vertical", style="Plain.TPanedwindow")
        panes.pack(fill=tk.BOTH, expand=True)

        # 履歴（上）
        hist_frame = tk.Frame(root, bg=_COLOR_HISTORY_BG)
        self.history_text = tk.Text(
            hist_frame,
            wrap=tk.WORD,
            state="disabled",
            bg=_COLOR_HISTORY_BG,
            bd=0,
            highlightthickness=0,
        )

        self.assistant_segments: list[tuple[str, str]] = []

        self.bold_font = tkfont.Font(self.history_text, self.history_text.cget("font"))
        self.bold_font.configure(weight="bold")
        self.style_on = True
        self._apply_word_style()

        self.history_text.tag_config("find_highlight", background="yellow")
        self.history_text.tag_config("user_word", font=self.bold_font, underline=True)
        vscroll_hist = tk.Scrollbar(hist_frame, command=self.history_text.yview)
        self.history_text.configure(yscrollcommand=vscroll_hist.set)
        vscroll_hist.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        panes.add(hist_frame, weight=4)

        # プロンプト（下・薄い紺）
        prompt_outer = tk.Frame(root, bg=_COLOR_PROMPT_BG)
        tk.Frame(prompt_outer, height=2, bg=_COLOR_BORDER).pack(fill=tk.X, side=tk.TOP)

        inp_frame = tk.Frame(prompt_outer, bg=_COLOR_PROMPT_BG, padx=8, pady=8)
        inp_frame.pack(fill=tk.BOTH, expand=True)

        inp_body = tk.Frame(inp_frame, bg=_COLOR_PROMPT_BG)
        inp_body.pack(fill=tk.BOTH, expand=True)

        text_col = tk.Frame(inp_body, bg=_COLOR_PROMPT_BG)
        text_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.input_text = tk.Text(
            text_col,
            height=4,
            wrap=tk.WORD,
            bg=_COLOR_PROMPT_INPUT_BG,
            fg="#1a1a1a",
            bd=1,
            relief=tk.SOLID,
            highlightthickness=1,
            highlightbackground=_COLOR_BORDER,
            highlightcolor=_COLOR_BORDER,
        )
        vscroll_inp = tk.Scrollbar(text_col, command=self.input_text.yview)
        self.input_text.configure(yscrollcommand=vscroll_inp.set)
        vscroll_inp.pack(side=tk.RIGHT, fill=tk.Y)
        self.input_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        btn_col = tk.Frame(inp_body, bg=_COLOR_PROMPT_BG)
        btn_col.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))

        self.send_button = tk.Button(
            btn_col,
            text="送信",
            width=8,
            command=self.on_send,
            bg=_COLOR_SEND_BG,
            fg=_COLOR_SEND_FG,
            activebackground=_COLOR_SEND_ACTIVE,
            activeforeground=_COLOR_SEND_FG,
            relief=tk.FLAT,
            padx=8,
            pady=6,
            cursor="hand2",
        )
        self.send_button.pack(side=tk.BOTTOM, pady=(4, 0))

        tk.Label(
            btn_col,
            text="Ctrl+S",
            bg=_COLOR_PROMPT_BG,
            fg="#5a6d82",
            font=("", 8),
        ).pack(side=tk.BOTTOM)

        panes.add(prompt_outer, weight=1)

        # ─────────────────── Internals ───────────────────
        self.queue: queue.Queue[str | None] = queue.Queue()
        self.gen_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.history_data: List[dict] = []
        self._table_pattern = re.compile(
            r"(\|[^\n]+\|\n\|[ \-:|]+\|\n(?:\|[^\n]+\|\n?)*)",
            re.MULTILINE,
        )
        self.search_start = "1.0"

        # Window for user prompts (created on first ctrl-click)
        self.user_prompts_win: tk.Toplevel | None = None
        self.user_prompts_text: tk.Text | None = None

        # ────────── NEW: remember next search start for each word ──────────
        self.next_pos: dict[str, str] = {}

        # ─────────────────── Bindings ───────────────────
        root.bind("<Control-s>", lambda e: self.on_send())
        root.bind("<Control-f>", lambda e: self.open_find())
        root.bind("<Control-p>", lambda e: self.edit_system_prompt())
        root.bind("<Control-z>", lambda e: self.on_stop())
        root.bind("<Control-x>", lambda e: self.on_clear())
        root.bind("<Control-d>", lambda e: self.toggle_word_style())
        root.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)

        # Ctrl+left-click on a green word
        self.history_text.tag_bind(
            "user_word", "<Control-Button-1>", self._on_ctrl_click_user_word
        )

    def _update_window_title(self) -> None:
        """ウィンドウタイトルに読み込みモデル名を反映する。"""
        name = _model_display_name(self.model_path)
        self.root.title(f"{_APP_NAME}（{name}）")

    def save_chat(self):
        if not self.history_data:
            messagebox.showinfo("会話の保存", "保存する会話がありません。")
            return

        path = filedialog.asksaveasfilename(
            title="会話を保存",
            defaultextension=".json",
            filetypes=[("JSON ファイル", "*.json"), ("すべてのファイル", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("会話の保存", f"保存しました:\n{path}")
        except Exception as ex:
            messagebox.showerror("会話の保存", f"保存に失敗しました:\n{ex}")

    def load_chat(self):
        if self.gen_thread and self.gen_thread.is_alive():
            messagebox.showinfo("お待ちください", "生成中は読み込めません。")
            return

        path = filedialog.askopenfilename(
            title="会話を読み込み",
            filetypes=[("JSON ファイル", "*.json"), ("すべてのファイル", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list) or not all(
                    isinstance(d, dict) and "user" in d and "assistant" in d for d in data
            ):
                raise ValueError("会話履歴の形式が正しくありません。")
        except Exception as ex:
            messagebox.showerror("会話の読み込み", f"読み込めませんでした:\n{ex}")
            return

        # wipe current session
        self.on_clear()

        self.history_data = data
        self.history_text.config(state="normal")

        for entry in self.history_data:
            user_msg, assist_msg = entry["user"], entry["assistant"]
            self.history_text.insert(tk.END, f"ユーザー: {user_msg}\nアシスタント: ")
            assist_start = self.history_text.index("end-1c")
            self.history_text.insert(tk.END, assist_msg)
            assist_end = self.history_text.index("end-1c")
            self.assistant_segments.append((assist_start, assist_end))
            self.history_text.insert(tk.END, "\n\n")
            self._post_process(assist_start, assist_end)

        self.history_text.config(state="disabled")
        self.history_text.see(tk.END)
        messagebox.showinfo("会話の読み込み", f"{len(self.history_data)} 件のやり取りを読み込みました。")


    # ─────────────────── System Prompt Editor ───────────────────
    def edit_system_prompt(self):
        """Open a dialog to edit the system prompt."""
        def save_and_close():
            self.system_prompt = text.get("1.0", tk.END).strip() or "You are a helpful assistant."
            win.destroy()

        win = tk.Toplevel(self.root)
        win.title("システムプロンプトの編集")
        win.transient(self.root)
        win.grab_set()

        text = tk.Text(win, wrap=tk.WORD, height=6, width=60)
        text.insert("1.0", self.system_prompt)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=(0, 10))

        tk.Button(btn_frame, text="保存", command=save_and_close).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="キャンセル", command=win.destroy).pack(side=tk.LEFT, padx=5)

        self._center_window(win)
        text.focus_set()

    # ─────────────────── Find dialog ───────────────────
    def open_find(self):
        if hasattr(self, "find_window") and self.find_window.winfo_exists():
            return
        self.find_window = tk.Toplevel(self.root)
        self.find_window.protocol("WM_DELETE_WINDOW", self._close_find)
        self.find_window.title("検索")
        self.find_window.transient(self.root)

        tk.Label(self.find_window, text="検索:").pack(side=tk.LEFT, padx=(10, 0), pady=10)
        self.find_entry = tk.Entry(self.find_window)
        self.find_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=10)
        self.find_entry.bind("<Return>", lambda e: self.find_next())
        tk.Button(self.find_window, text="次へ", command=self.find_next).pack(
            side=tk.LEFT, padx=(0, 10), pady=10
        )

        # Center dialog
        self.find_window.update_idletasks()
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        win_w = self.find_window.winfo_width()
        win_h = self.find_window.winfo_height()
        x = root_x + (root_w - win_w) // 2
        y = root_y + (root_h - win_h) // 2
        self.find_window.geometry(f"+{x}+{y}")

        self.find_entry.focus_set()
        self.search_start = "1.0"

    def find_next(self):
        pattern = self.find_entry.get()
        if not pattern:
            return
        idx = self.history_text.search(pattern, self.search_start, tk.END, nocase=True)
        if not idx:
            messagebox.showinfo("検索", f"「{pattern}」は見つかりませんでした")
            self.search_start = "1.0"
            return
        end_idx = f"{idx}+{len(pattern)}c"
        self.history_text.tag_remove("find_highlight", "1.0", tk.END)
        self.history_text.tag_add("find_highlight", idx, end_idx)
        self.history_text.see(idx)
        self.search_start = end_idx

    def _close_find(self):
        """Remove highlight and destroy the Find window."""
        self.history_text.tag_remove("find_highlight", "1.0", tk.END)
        if hasattr(self, "find_window") and self.find_window.winfo_exists():
            self.find_window.destroy()

    # ─────────────────── Helpers ───────────────────
    def _on_ctrl_mousewheel(self, event):
        self.zoom_in() if event.delta > 0 else self.zoom_out()

    def select_model(self):
        model_dir = get_model_dir()
        if not os.path.isdir(model_dir):
            os.makedirs(model_dir, exist_ok=True)
        path = filedialog.askopenfilename(
            title="モデルを選択",
            initialdir=model_dir,
            filetypes=[("GGUF モデル", "*.gguf"), ("すべてのファイル", "*.*")],
        )
        if path:
            self.model_path = path
            self._update_window_title()
            messagebox.showinfo(
                "モデルの選択",
                f"モデルを設定しました:\n{_model_display_name(path)}",
            )

    def toggle_wrap(self):
        for w in (self.input_text, self.history_text):
            cur = w.cget("wrap")
            w.config(wrap=tk.NONE if cur == tk.WORD else tk.WORD)

    def zoom_in(self):
        for w in (self.input_text, self.history_text):
            f = tkfont.Font(font=w.cget("font"))
            f.configure(size=f.cget("size") + 1)
            w.config(font=f)
        self._refresh_bold_font()

    def zoom_out(self):
        for w in (self.input_text, self.history_text):
            f = tkfont.Font(font=w.cget("font"))
            s = f.cget("size")
            if s > 6:
                f.configure(size=s - 1)
                w.config(font=f)
        self._refresh_bold_font()

    def show_about(self):
        win = tk.Toplevel(self.root)
        win.title("このツールについて")
        win.transient(self.root)
        win.resizable(False, False)
        win.configure(bg="white")

        model_name = _model_display_name(self.model_path)
        text = (
            f"{_APP_NAME}\n\n"
            "このツールは、お使いのパソコン上だけで動くローカル AI チャットです。\n"
            "インターネット接続やクラウド API は不要で、入力した文章をもとに\n"
            "AI（大規模言語モデル）が回答を生成します。会話内容は外に送られません。\n\n"
            f"読み込み中のモデル: {model_name}\n\n"
            "【動作環境】\n"
            "・必要メモリ: 約 2 GB\n"
            "・CPU のみで推論（GPU 不要・軽量動作を優先した設計）\n\n"
            "【使い方】\n"
            "下部の入力欄に質問を書き、「送信」ボタンまたは Ctrl+S で送ってください。\n"
            "モデルは同梱の model フォルダ内の GGUF を自動で読み込みます。\n\n"
            "製作者: OK"
        )
        lbl = tk.Label(win, text=text, justify=tk.LEFT, bg="white", padx=15, pady=15)
        lbl.pack(anchor="w")

        tk.Button(win, text="閉じる", command=win.destroy, width=10).pack(pady=(0, 15))

        self._center_window(win)

    # ─────────────────── Chat actions ───────────────────
    def on_send(self):
        if self.gen_thread and self.gen_thread.is_alive():
            messagebox.showinfo(
                "お待ちください",
                "応答を生成中です。\n先に Ctrl+Z で停止してください。",
            )
            return

        prompt = self.input_text.get("1.0", tk.END).strip()
        if not prompt:
            return

        self.history_data.append({"user": prompt, "assistant": ""})
        prev = [(d["user"], d["assistant"]) for d in self.history_data[:-1]]

        self.history_text.config(state="normal")
        self.history_text.insert(tk.END, f"ユーザー: {prompt}\nアシスタント: ")
        self.assist_start = self.history_text.index("end-1c")
        self.history_text.config(state="disabled")

        self.input_text.delete("1.0", tk.END)
        self.history_text.see(tk.END)

        self.queue = queue.Queue()
        self.stop_event.clear()
        self.gen_thread = threading.Thread(
            target=self._worker_generate, args=(prompt, prev), daemon=True
        )
        self.gen_thread.start()
        self.history_text.after(50, self._process_queue)

    def on_stop(self):
        if self.gen_thread and self.gen_thread.is_alive():
            self.stop_event.set()

    def on_clear(self):
        if self.gen_thread and self.gen_thread.is_alive():
            messagebox.showinfo("お待ちください", "生成中はクリアできません。")
            return
        self.history_data.clear()
        self.history_text.config(state="normal")
        self.history_text.delete("1.0", tk.END)
        self.history_text.config(state="disabled")
        self.input_text.delete("1.0", tk.END)
        self.assistant_segments.clear()

    # ─────────────────── Generation thread ───────────────────
    def _worker_generate(self, prompt: str, history: List[Tuple[str, str]]):
        last = ""
        try:
            for full in respond(
                prompt,
                history,
                model=self.model_path,
                system_message=self.system_prompt,
            ):
                if self.stop_event.is_set():
                    break
                delta = full[len(last) :]
                self.queue.put(delta)
                last = full
        except Exception as e:
            self.queue.put(f"[Error] {e}\n")
        finally:
            if self.history_data:
                self.history_data[-1]["assistant"] = last
            self.queue.put(None)

    def _process_queue(self):
        while True:
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                self.history_text.config(state="normal")
                self.history_text.insert(tk.END, "\n\n\n\n")
                end_pos = self.history_text.index("end-1c")
                self._post_process(self.assist_start, end_pos)
                self.history_text.config(state="disabled")
                return
            at_bot = float(self.history_text.yview()[1]) >= 0.99
            self.history_text.config(state="normal")
            self.history_text.insert(tk.END, item)
            self.history_text.config(state="disabled")
            if at_bot:
                self.history_text.see(tk.END)
        if self.gen_thread and self.gen_thread.is_alive():
            self.history_text.after(50, self._process_queue)

    # ─────────────────── Post-processing ───────────────────
    def _post_process(self, start: str, end: str):
        raw = self.history_text.get(start, end)
        clean = re.sub(r"\*\*(.*?)\*\*", r"\1", raw)
        clean = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", clean)
        clean = self._table_pattern.sub(lambda m: self._md_table_to_tsv(m.group(1)), clean)

        if clean != raw:
            self.history_text.delete(start, end)
            self.history_text.insert(start, clean)

        self.history_text.tag_remove("user_word", start, end)
        self._highlight_user_words(start, end)
        self.assistant_segments.append((start, end))

    def _highlight_user_words(self, start: str, end: str):
        """
        Bold-underline every token appearing in ANY user prompt, including:
          • plain words   → hello
          • numbers       → 45, 3.14
          • dims (NxM…)   → 2x5, 4x3x2
        """
        tokens: set[str] = set()

        word_re = re.compile(r"[A-Za-z']+")
        num_re = re.compile(r"\d+(?:\.\d+)?")
        dim_re = re.compile(r"\d+(?:x\d+)+", re.I)

        for entry in self.history_data:
            txt = entry["user"]
            tokens.update(m.group(0) for m in word_re.finditer(txt))
            tokens.update(m.group(0) for m in num_re.finditer(txt))
            tokens.update(m.group(0) for m in dim_re.finditer(txt))

        if not tokens:
            return

        for tok in tokens:
            pure_word = re.match(r"^\w+$", tok) is not None

            if pure_word:  # word → use \m..\M
                pattern = rf"\m{re.escape(tok)}\M"
                use_regex = True
            else:  # number / dim
                pattern = tok
                use_regex = False

            idx = start
            while True:
                idx = self.history_text.search(
                    pattern, idx, end, nocase=True, regexp=use_regex
                )
                if not idx:
                    break
                end_idx = f"{idx}+{len(tok)}c"
                self.history_text.tag_add("user_word", idx, end_idx)
                idx = end_idx

    # ─── toggle from menu or Ctrl+D ─────────────────────────────────
    def toggle_word_style(self):
        self.style_on = not self.style_on
        self._apply_word_style()

        # refresh highlights just for assistant segments
        self.history_text.tag_remove("user_word", "1.0", tk.END)
        for start, end in self.assistant_segments:
            self._highlight_user_words(start, end)

    # ─── apply current style to the tag ─────────────────────────────
    def _apply_word_style(self):
        if self.style_on:
            self.history_text.tag_config("user_word", font=self.bold_font, underline=True)
        else:  # plain
            self.history_text.tag_config(
                "user_word", font=self.history_text.cget("font"), underline=False
            )

    def _refresh_bold_font(self):
        """Match bold-underline font size to history_text current size."""
        base = tkfont.Font(font=self.history_text.cget("font"))
        self.bold_font.configure(size=base.cget("size"))  # keep weight/underline
        if self.style_on:  # tag might be off
            self.history_text.tag_config("user_word", font=self.bold_font)

    # ─────────────────── Ctrl-click handler ───────────────────
    def _on_ctrl_click_user_word(self, event):
        index = self.history_text.index(f"@{event.x},{event.y}")
        clicked = self.history_text.get(f"{index} wordstart", f"{index} wordend").strip()
        if clicked:
            self._show_user_prompts_window(clicked.lower())

    def _show_user_prompts_window(self, word: str):
        """Highlight *all* occurrences of <word> in yellow, but scroll to the
        next one (cycling) each time the green word is Ctrl-clicked."""
        # ── create the window & widgets on first use ──
        if self.user_prompts_win is None or not self.user_prompts_win.winfo_exists():
            self.user_prompts_win = tk.Toplevel(self.root)
            self.user_prompts_win.title("プロンプト一覧")

            # match main-window look
            self.user_prompts_win.configure(bg="white", bd=0, highlightthickness=0)

            self.user_prompts_text = tk.Text(
                self.user_prompts_win,
                wrap=tk.WORD,
                state="disabled",
                bg="white",  # same white background
                bd=0,  # no 3-D border
                highlightthickness=0,  # no focus ring
            )
            self.user_prompts_text.tag_config("clicked_word", background="yellow")
            self.user_prompts_text.tag_config("focus_word", background="gold")

            vscroll = tk.Scrollbar(
                self.user_prompts_win,
                command=self.user_prompts_text.yview,
                bd=0,
                relief="flat",
                highlightthickness=0,
            )
            self.user_prompts_text.configure(yscrollcommand=vscroll.set)

            self.user_prompts_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vscroll.pack(side=tk.RIGHT, fill=tk.Y)

            self._center_window(self.user_prompts_win)  # keep existing centering

        # ── (re)populate the text box ──
        combined = "\n".join(f"{i+1:>2}. {d['user']}" for i, d in enumerate(self.history_data)) + "\n"
        self.user_prompts_text.config(state="normal")
        self.user_prompts_text.delete("1.0", tk.END)
        self.user_prompts_text.insert("1.0", combined)

        # ── clear old tags, then tag *all* occurrences ──
        self.user_prompts_text.tag_remove("clicked_word", "1.0", tk.END)
        self.user_prompts_text.tag_remove("focus_word", "1.0", tk.END)

        pattern = rf"\m{re.escape(word)}\M"
        idx = "1.0"
        all_positions: list[str] = []
        while True:
            idx = self.user_prompts_text.search(pattern, idx, tk.END, nocase=True, regexp=True)
            if not idx:
                break
            end_idx = f"{idx}+{len(word)}c"
            self.user_prompts_text.tag_add("clicked_word", idx, end_idx)
            all_positions.append(idx)
            idx = end_idx

        if not all_positions:
            # nothing found: reset pointer and return
            self.next_pos[word] = 0
            self.user_prompts_text.config(state="disabled")
            self.user_prompts_win.lift()
            return

        # ── figure out which occurrence to focus on this click ──
        curr_index = self.next_pos.get(word, 0) % len(all_positions)
        focus_pos = all_positions[curr_index]
        focus_end = f"{focus_pos}+{len(word)}c"
        self.user_prompts_text.tag_add("focus_word", focus_pos, focus_end)
        self.user_prompts_text.see(focus_pos)

        # next time, advance
        self.next_pos[word] = (curr_index + 1) % len(all_positions)

        self.user_prompts_text.config(state="disabled")
        self.user_prompts_win.lift()

    def _center_window(self, win: tk.Toplevel):
        """Position <win> in the center of the root window."""
        win.update_idletasks()  # make sure size is known
        root_x, root_y = self.root.winfo_x(), self.root.winfo_y()
        root_w, root_h = self.root.winfo_width(), self.root.winfo_height()
        win_w, win_h = win.winfo_width(), win.winfo_height()
        x = root_x + max((root_w - win_w) // 2, 0)
        y = root_y + max((root_h - win_h) // 2, 0)
        win.geometry(f"+{x}+{y}")

    # ─────────────────── Markdown utilities ───────────────────
    @staticmethod
    def _md_table_to_tsv(md: str) -> str:
        lines = md.strip().splitlines()
        header = [c.strip() for c in lines[0].strip("|").split("|")]
        rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines[2:] if ln.startswith("|")]
        tsv = "\t".join(header) + "\n"
        tsv += "\n".join("\t".join(r) for r in rows) + "\n"
        return tsv


def run_app() -> None:
    """Create Tk root and start the main loop (used by main.py)."""
    root = tk.Tk()
    ChatGUI(root)
    root.mainloop()
