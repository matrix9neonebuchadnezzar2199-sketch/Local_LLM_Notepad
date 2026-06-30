from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
from typing import List, Tuple

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, ttk

from llm_utils import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL_FILENAME,
    DEFAULT_N_CTX,
    estimate_context_usage,
    get_app_dir,
    get_model_dir,
    is_model_loaded,
    preload_model,
    reset_model_cache,
    resolve_model_path,
    respond,
)
from md_render import RenderLine, format_assistant_markdown, line_kind_to_tag
from theme import DARK_THEME, LIGHT_THEME, AppTheme

__all__ = ["ChatGUI", "run_app"]

_COLOR_OVERLAY_BG = "#000000"
_COLOR_OVERLAY_FG = "#FFE566"
_APP_NAME = "Owl-Bot"
_UI_FONT_SIZE = 12
_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


def _enable_windows_dpi_awareness() -> None:
    """高 DPI 環境でウィンドウ全体が拡大ぼかしされないよう、起動前に DPI 認識を有効化。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # Per-Monitor DPI Aware V2 (Windows 10 1703+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _pick_ui_font_family() -> str:
    """日本語 UI 向けの TrueType フォントを選ぶ（ビットマップ系 MS Gothic は避ける）。"""
    for family in ("Yu Gothic UI", "Meiryo UI", "Segoe UI", "MS UI Gothic"):
        if family in tkfont.families():
            return family
    return "TkDefaultFont"


def _configure_ui_fonts(root: tk.Tk) -> None:
    """メニュー・入力欄・履歴で同じアンチエイリアス付きフォントを使う。"""
    family = _pick_ui_font_family()
    size = _UI_FONT_SIZE
    for font_name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkFixedFont"):
        try:
            tkfont.nametofont(font_name).configure(family=family, size=size)
        except tk.TclError:
            pass
    root.option_add("*Font", (family, size))
    # Tcl/Tk の論理 DPI に合わせてスケーリング（拡大率 125% 等でのにじみ軽減）
    try:
        pixels_per_inch = root.winfo_fpixels("1i")
        root.tk.call("tk", "scaling", pixels_per_inch / 72.0)
    except tk.TclError:
        pass


def _model_display_name(model_path: str) -> str:
    """GGUF ファイル名から表示用モデル名を得る。"""
    base = os.path.basename(model_path)
    if base.lower().endswith(".gguf"):
        return base[: -len(".gguf")]
    return base or "（モデル未設定）"


def _resolve_window_icon_path() -> str | None:
    """ウィンドウタイトルバー用 PNG のパス（EXE / 開発時）。"""
    for name in ("Owl-Bot.png", "Icon.png"):
        candidates = []
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                candidates.append(os.path.join(meipass, name))
        candidates.append(os.path.join(get_app_dir(), name))
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), name))
        for path in candidates:
            if os.path.isfile(path):
                return path
    return None


def _resolve_window_icon_ico_path() -> str | None:
    """Windows タイトルバー用 ICO（PhotoImage よりシャープ）。"""
    for name in ("Owl-Bot.ico",):
        candidates = []
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                candidates.append(os.path.join(meipass, name))
        candidates.append(os.path.join(get_app_dir(), name))
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), name))
        for path in candidates:
            if os.path.isfile(path):
                return path
    return None


class ChatGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.dark_mode = tk.BooleanVar(value=False)
        self.theme: AppTheme = LIGHT_THEME
        self._context_meter_after_id: str | None = None
        self._spinner_active = False
        self._spinner_after_id: str | None = None
        self._spinner_frame_idx = 0
        self._spinner_visible = False
        self._got_first_token = False
        root.configure(bg=self.theme.bg)

        icon_set = False
        if sys.platform == "win32":
            ico_path = _resolve_window_icon_ico_path()
            if ico_path:
                try:
                    root.iconbitmap(default=ico_path)
                    icon_set = True
                except Exception as ex:
                    print(f"ICO icon load failed: {ex}")
        if not icon_set:
            icon_path = _resolve_window_icon_path()
            if icon_path:
                try:
                    self._window_icon = tk.PhotoImage(file=icon_path)
                    root.iconphoto(True, self._window_icon)
                except Exception as ex:
                    print(f"Icon load failed: {ex}")

        # ─────────────────── State ───────────────────
        self.system_prompt: str = "You are a helpful assistant."
        self.history_data: List[dict] = []

        try:
            self.model_path = resolve_model_path(DEFAULT_MODEL_FILENAME)
        except FileNotFoundError:
            self.model_path = DEFAULT_MODEL_FILENAME
        self._update_window_title()

        # ─────────────────── Menus ───────────────────
        self.menubar = tk.Menu(root)
        file_menu = tk.Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="モデルを選択...", command=self.select_model)
        file_menu.add_command(label="会話を保存...", command=self.save_chat)
        file_menu.add_command(label="会話を読み込み...", command=self.load_chat)
        file_menu.add_separator()
        file_menu.add_command(label="終了", command=root.quit)
        self.menubar.add_cascade(label="ファイル", menu=file_menu)

        edit_menu = tk.Menu(self.menubar, tearoff=0)
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
        self.menubar.add_cascade(label="編集", menu=edit_menu)

        format_menu = tk.Menu(self.menubar, tearoff=0)
        format_menu.add_command(label="折り返しの切替", command=self.toggle_wrap)
        self.menubar.add_cascade(label="書式", menu=format_menu)

        view_menu = tk.Menu(self.menubar, tearoff=0)
        view_menu.add_command(label="拡大", accelerator="Ctrl++", command=self.zoom_in)
        view_menu.add_command(label="縮小", accelerator="Ctrl+-", command=self.zoom_out)
        view_menu.add_separator()
        view_menu.add_checkbutton(
            label="ダークモード（黒背景・緑文字）",
            variable=self.dark_mode,
            command=self._toggle_dark_mode,
        )
        self.menubar.add_cascade(label="表示", menu=view_menu)

        help_menu = tk.Menu(self.menubar, tearoff=0)
        help_menu.add_command(label="このツールについて", command=self.show_about)
        self.menubar.add_cascade(label="ヘルプ", menu=help_menu)
        root.config(menu=self.menubar)

        # ─────────────────── Layout ───────────────────
        self.status_frame = tk.Frame(root)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.context_label = tk.Label(
            self.status_frame,
            text=self._context_status_text(),
            anchor=tk.W,
            padx=10,
            pady=4,
        )
        self.context_label.pack(fill=tk.X)

        self.panes_style = ttk.Style()
        self.panes_style.configure(
            "Plain.TPanedwindow",
            background=self.theme.border,
            borderwidth=0,
            relief="flat",
            sashwidth=6,
        )
        panes = ttk.PanedWindow(root, orient="vertical", style="Plain.TPanedwindow")
        panes.pack(fill=tk.BOTH, expand=True)
        self.panes = panes

        # 履歴（上）
        self.hist_frame = tk.Frame(root)
        self.history_text = tk.Text(
            self.hist_frame,
            wrap=tk.WORD,
            state="disabled",
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
        self._setup_markdown_styles()
        self._setup_chat_bubble_styles()
        self.vscroll_hist = tk.Scrollbar(self.hist_frame, command=self.history_text.yview)
        self.history_text.configure(yscrollcommand=self.vscroll_hist.set)
        self.vscroll_hist.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.history_text.bind("<Configure>", self._on_history_configure, add="+")
        panes.add(self.hist_frame, weight=4)

        # プロンプト（下）
        self.prompt_outer = tk.Frame(root)
        self.prompt_border = tk.Frame(self.prompt_outer, height=2)
        self.prompt_border.pack(fill=tk.X, side=tk.TOP)

        self.inp_frame = tk.Frame(self.prompt_outer, padx=8, pady=8)
        self.inp_frame.pack(fill=tk.BOTH, expand=True)

        self.inp_body = tk.Frame(self.inp_frame)
        self.inp_body.pack(fill=tk.BOTH, expand=True)

        self.text_col = tk.Frame(self.inp_body)
        self.text_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.input_text = tk.Text(
            self.text_col,
            height=4,
            wrap=tk.WORD,
            bd=1,
            relief=tk.SOLID,
            highlightthickness=1,
        )
        self.vscroll_inp = tk.Scrollbar(self.text_col, command=self.input_text.yview)
        self.input_text.configure(yscrollcommand=self.vscroll_inp.set)
        self.vscroll_inp.pack(side=tk.RIGHT, fill=tk.Y)
        self.input_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.btn_col = tk.Frame(self.inp_body)
        self.btn_col.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))

        self.send_button = tk.Button(
            self.btn_col,
            text="送信",
            width=8,
            command=self.on_send,
            relief=tk.FLAT,
            padx=8,
            pady=6,
            cursor="hand2",
        )
        self.send_button.pack(side=tk.BOTTOM, pady=(4, 0))

        self.shortcut_label = tk.Label(
            self.btn_col,
            text="Ctrl+S",
            font=(_pick_ui_font_family(), 8),
        )
        self.shortcut_label.pack(side=tk.BOTTOM)

        panes.add(self.prompt_outer, weight=1)

        # ─────────────────── Internals ───────────────────
        self.queue: queue.Queue[str | None] = queue.Queue()
        self.gen_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
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
        self.input_text.bind("<KeyRelease>", lambda e: self._schedule_context_meter_update())

        # Ctrl+left-click on a green word
        self.history_text.tag_bind(
            "user_word", "<Control-Button-1>", self._on_ctrl_click_user_word
        )

        # モデル読み込みオーバーレイ
        self._model_loading = False
        self._model_file_missing = False
        self._create_model_overlay()
        self._apply_theme()
        self.root.after(200, self._bootstrap_model)

    # ─────────────────── Theme / dialogs ───────────────────
    def _current_theme(self) -> AppTheme:
        return DARK_THEME if self.dark_mode.get() else LIGHT_THEME

    def _toggle_dark_mode(self) -> None:
        self._apply_theme()

    def _apply_theme(self) -> None:
        t = self._current_theme()
        self.theme = t

        self.root.configure(bg=t.bg)
        self._style_menu(self.menubar)
        for i in range(self.menubar.index("end") + 1):
            try:
                submenu = self.menubar.nametowidget(self.menubar.entrycget(i, "menu"))
                self._style_menu(submenu)
            except (tk.TclError, KeyError):
                pass

        self.panes_style.configure("Plain.TPanedwindow", background=t.border)

        for frame in (
            self.hist_frame,
            self.prompt_outer,
            self.inp_frame,
            self.inp_body,
            self.text_col,
            self.btn_col,
            self.status_frame,
        ):
            frame.configure(bg=t.prompt_bg if frame is not self.hist_frame else t.history_bg)
        self.hist_frame.configure(bg=t.history_bg)
        self.status_frame.configure(bg=t.status_bg)
        self.prompt_border.configure(bg=t.border)

        self.history_text.configure(
            bg=t.history_bg,
            fg=t.history_fg,
            insertbackground=t.insert_bg,
            selectbackground=t.border,
            selectforeground=t.send_fg if t.name == "dark" else t.fg,
        )
        self.input_text.configure(
            bg=t.prompt_input_bg,
            fg=t.prompt_input_fg,
            insertbackground=t.insert_bg,
            highlightbackground=t.border,
            highlightcolor=t.border,
            selectbackground=t.border,
            selectforeground=t.send_fg if t.name == "dark" else t.fg,
        )
        self._style_scrollbar(self.vscroll_hist)
        self._style_scrollbar(self.vscroll_inp)

        self.send_button.configure(
            bg=t.send_bg,
            fg=t.send_fg,
            activebackground=t.send_active,
            activeforeground=t.send_fg,
        )
        self.shortcut_label.configure(bg=t.prompt_bg, fg=t.muted)
        self.context_label.configure(bg=t.status_bg, fg=t.status_fg)

        self.history_text.tag_config("find_highlight", background=t.find_highlight, foreground=t.find_highlight_fg)
        self._setup_markdown_styles()
        self._setup_chat_bubble_styles()
        self._apply_word_style()

        if hasattr(self, "find_window") and self.find_window.winfo_exists():
            self._style_dialog(self.find_window)
        if self.user_prompts_win and self.user_prompts_win.winfo_exists():
            self._style_dialog(self.user_prompts_win)
            if self.user_prompts_text:
                self.user_prompts_text.configure(
                    bg=t.history_bg,
                    fg=t.history_fg,
                    insertbackground=t.insert_bg,
                )
                self.user_prompts_text.tag_config("clicked_word", background=t.find_highlight)
                self.user_prompts_text.tag_config("focus_word", background=t.border)

    def _style_menu(self, menu: tk.Menu) -> None:
        t = self.theme
        menu.configure(
            bg=t.menu_bg,
            fg=t.menu_fg,
            activebackground=t.menu_active_bg,
            activeforeground=t.menu_active_fg,
        )

    def _style_scrollbar(self, sb: tk.Scrollbar) -> None:
        t = self.theme
        sb.configure(
            bg=t.scrollbar_bg,
            troughcolor=t.scrollbar_trough,
            activebackground=t.scrollbar_bg,
            highlightthickness=0,
        )

    def _style_dialog(self, win: tk.Toplevel) -> None:
        t = self.theme
        win.configure(bg=t.bg)
        for child in win.winfo_children():
            self._style_widget_tree(child)

    def _style_widget_tree(self, widget: tk.Widget) -> None:
        t = self.theme
        cls = widget.winfo_class()
        try:
            if cls in ("Frame", "Labelframe"):
                widget.configure(bg=t.bg)
            elif cls == "Label":
                widget.configure(bg=t.bg, fg=t.fg)
            elif cls == "Button":
                widget.configure(
                    bg=t.button_bg,
                    fg=t.button_fg,
                    activebackground=t.button_active_bg,
                    activeforeground=t.button_fg,
                )
            elif cls == "Entry":
                widget.configure(
                    bg=t.entry_bg,
                    fg=t.entry_fg,
                    insertbackground=t.insert_bg,
                )
            elif cls == "Text":
                widget.configure(
                    bg=t.prompt_input_bg,
                    fg=t.prompt_input_fg,
                    insertbackground=t.insert_bg,
                )
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._style_widget_tree(child)

    def _make_dialog(self, title: str, width: int = 420) -> tk.Toplevel:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.configure(bg=self.theme.bg)
        win.resizable(True, True)
        return win

    def _dlg_info(self, title: str, message: str) -> None:
        win = self._make_dialog(title)
        tk.Label(win, text=message, justify=tk.LEFT, wraplength=400, padx=16, pady=12).pack(
            anchor="w", fill=tk.BOTH, expand=True
        )
        tk.Button(win, text="OK", width=10, command=win.destroy).pack(pady=(0, 12))
        self._style_dialog(win)
        self._center_window(win)
        win.grab_set()

    def _dlg_error(self, title: str, message: str) -> None:
        self._dlg_info(title, message)

    # ─────────────────── Context meter ───────────────────
    def _context_status_text(self) -> str:
        draft = self.input_text.get("1.0", tk.END).strip() if hasattr(self, "input_text") else ""
        history = [
            (d.get("user_llm", d["user"]), d["assistant"])
            for d in getattr(self, "history_data", [])
        ]
        pending = draft

        used, limit = estimate_context_usage(
            self.system_prompt,
            history,
            pending,
            model=self.model_path,
        )
        pct = min(100, int(used * 100 / limit)) if limit else 0
        return (
            f"コンテキスト: {used:,} / {limit:,} トークン（{pct}%）"
            f"  ·  上限 n_ctx={DEFAULT_N_CTX}  ·  出力最大 {DEFAULT_MAX_TOKENS}"
        )

    def _update_context_meter(self) -> None:
        if hasattr(self, "context_label"):
            self.context_label.config(text=self._context_status_text())

    def _schedule_context_meter_update(self) -> None:
        if self._context_meter_after_id:
            self.root.after_cancel(self._context_meter_after_id)
        self._context_meter_after_id = self.root.after(250, self._update_context_meter)

    # ─────────────────── Chat bubbles / spinner ───────────────────
    def _bubble_side_margin(self) -> int:
        w = max(self.history_text.winfo_width(), 360)
        return max(int(w * 0.28), 72)

    def _on_history_configure(self, event=None) -> None:
        if hasattr(self, "theme"):
            self._setup_chat_bubble_styles()

    def _setup_chat_bubble_styles(self) -> None:
        """LINE 風: ユーザー緑・AI 薄青の吹き出しタグ。"""
        if not hasattr(self, "history_text"):
            return
        t = self.theme
        side = self._bubble_side_margin()
        base_font = tkfont.Font(font=self.history_text.cget("font"))
        family = base_font.actual("family")
        size = base_font.actual("size")
        label_font = getattr(
            self,
            "_role_font",
            tkfont.Font(family=family, size=max(size - 2, 9)),
        )
        label_font.configure(size=max(size - 2, 9), weight="normal")

        self.history_text.tag_configure(
            "chat_gap",
            spacing1=10,
            spacing3=0,
            background=t.history_bg,
        )
        bubble_specs = (
            ("user_label", tk.RIGHT, side, 12, t.history_bg, t.role_label, label_font, 2, 0),
            ("user_msg", tk.RIGHT, side, 12, t.user_bubble_bg, t.user_bubble_fg, base_font, 8, 10),
            ("assistant_label", tk.LEFT, 12, side, t.history_bg, t.role_label, label_font, 2, 0),
            (
                "assistant_msg",
                tk.LEFT,
                12,
                side,
                t.assistant_bubble_bg,
                t.assistant_bubble_fg,
                base_font,
                8,
                10,
            ),
            (
                "typing_indicator",
                tk.LEFT,
                12,
                side,
                t.assistant_bubble_bg,
                t.typing_fg,
                base_font,
                8,
                10,
            ),
        )
        for name, justify, lm, rm, bg, fg, font, sp1, sp3 in bubble_specs:
            self.history_text.tag_configure(
                name,
                justify=justify,
                lmargin1=lm,
                lmargin2=lm,
                rmargin=rm,
                background=bg,
                foreground=fg,
                spacing1=sp1,
                spacing3=sp3,
                font=font,
            )

    def _append_chat_gap(self) -> None:
        if self.history_text.get("1.0", "end-1c").strip():
            self.history_text.insert(tk.END, "\n", "chat_gap")

    def _append_user_message(self, text: str) -> None:
        self._append_chat_gap()
        self.history_text.insert(tk.END, "あなた\n", "user_label")
        self.history_text.insert(tk.END, f"{text}\n", "user_msg")

    def _append_assistant_header(self) -> None:
        self.history_text.insert(tk.END, f"{_APP_NAME}\n", "assistant_label")

    def _start_typing_spinner(self) -> None:
        self._got_first_token = False
        self._spinner_active = True
        self._spinner_frame_idx = 0
        self._spinner_visible = False
        self.assist_start = self.history_text.index("end-1c")
        self._tick_typing_spinner()

    def _tick_typing_spinner(self) -> None:
        if not self._spinner_active:
            return
        frame = _SPINNER_FRAMES[self._spinner_frame_idx % len(_SPINNER_FRAMES)]
        label = f"{frame} 生成中…"
        self.history_text.config(state=tk.NORMAL)
        if self._spinner_visible:
            end = self.history_text.index(f"{self._spinner_start} lineend")
            self.history_text.delete(self._spinner_start, end)
        else:
            self._spinner_start = self.history_text.index("end-1c")
            self._spinner_visible = True
        self.history_text.insert(self._spinner_start, label, ("typing_indicator", "assistant_msg"))
        self.history_text.config(state=tk.DISABLED)
        self._spinner_frame_idx += 1
        self._spinner_after_id = self.root.after(120, self._tick_typing_spinner)

    def _stop_typing_spinner(self) -> None:
        self._spinner_active = False
        if self._spinner_after_id:
            self.root.after_cancel(self._spinner_after_id)
            self._spinner_after_id = None
        if not self._spinner_visible:
            return
        self.history_text.config(state=tk.NORMAL)
        end = self.history_text.index(f"{self._spinner_start} lineend")
        self.history_text.delete(self._spinner_start, end)
        self.assist_start = self._spinner_start
        self._spinner_visible = False
        self.history_text.config(state=tk.DISABLED)

    def _setup_markdown_styles(self) -> None:
        """応答欄の Markdown 見た目用タグを定義する。"""
        base = tkfont.Font(font=self.history_text.cget("font"))
        family = base.actual("family")
        size = base.actual("size")
        mono = "Consolas" if "Consolas" in tkfont.families() else "Courier New"

        self._md_font_h1 = tkfont.Font(family=family, size=size + 5, weight="bold")
        self._md_font_h2 = tkfont.Font(family=family, size=size + 3, weight="bold")
        self._md_font_h3 = tkfont.Font(family=family, size=size + 2, weight="bold")
        self._md_font_h4 = tkfont.Font(family=family, size=size + 1, weight="bold")
        self._md_font_table = tkfont.Font(family=mono, size=size)
        self._role_font = tkfont.Font(family=family, size=max(size - 2, 9))
        t = self.theme

        self.history_text.tag_config("md_h1", font=self._md_font_h1, foreground=t.md_h1, spacing3=6)
        self.history_text.tag_config("md_h2", font=self._md_font_h2, foreground=t.md_h2, spacing3=4)
        self.history_text.tag_config("md_h3", font=self._md_font_h3, foreground=t.md_h3, spacing3=3)
        self.history_text.tag_config("md_h4", font=self._md_font_h4, foreground=t.md_h4, spacing3=2)
        self.history_text.tag_config("md_hr", foreground=t.md_hr, spacing1=6, spacing3=6)
        self.history_text.tag_config("md_bullet", lmargin1=18, lmargin2=18, spacing3=2)
        self.history_text.tag_config(
            "md_table",
            font=self._md_font_table,
            background=t.md_table_bg,
            foreground=t.md_table_fg,
            spacing1=4,
            spacing3=4,
        )
        self.history_text.tag_config("role_label", font=self._role_font, foreground=t.role_label)

    def _create_model_overlay(self) -> None:
        """半透明の黒背景＋黄色文字でモデル状態を表示する。"""
        self._overlay = tk.Toplevel(self.root)
        self._overlay.withdraw()
        self._overlay.overrideredirect(True)
        self._overlay.attributes("-topmost", True)
        try:
            self._overlay.attributes("-alpha", 0.78)
        except tk.TclError:
            pass
        self._overlay.configure(bg=_COLOR_OVERLAY_BG)

        family = _pick_ui_font_family()
        self._overlay_label = tk.Label(
            self._overlay,
            text="",
            fg=_COLOR_OVERLAY_FG,
            bg=_COLOR_OVERLAY_BG,
            font=(family, 15, "bold"),
            justify=tk.CENTER,
            wraplength=520,
            padx=28,
            pady=20,
        )
        self._overlay_label.pack(expand=True, fill=tk.BOTH)
        self.root.bind("<Configure>", self._sync_overlay_geometry, add="+")

    def _sync_overlay_geometry(self, event=None) -> None:
        if not hasattr(self, "_overlay"):
            return
        self.root.update_idletasks()
        w = max(self.root.winfo_width(), 400)
        h = max(self.root.winfo_height(), 300)
        x = self.root.winfo_rootx()
        y = self.root.winfo_rooty()
        self._overlay.geometry(f"{w}x{h}+{x}+{y}")

    def _show_overlay(self, message: str) -> None:
        self._overlay_label.config(text=message)
        self._sync_overlay_geometry()
        self._overlay.deiconify()
        self._overlay.lift()

    def _hide_overlay(self) -> None:
        if hasattr(self, "_overlay"):
            self._overlay.withdraw()

    def _hide_overlay_after(self, ms: int) -> None:
        self.root.after(ms, self._hide_overlay)

    def _set_input_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.input_text.config(state=state)
        self.send_button.config(state=state)

    def _bootstrap_model(self) -> None:
        """起動時: 未配置 → 警告 / 配置済み → バックグラウンド読み込み。"""
        try:
            path = resolve_model_path(self.model_path)
            self.model_path = path
            self._update_window_title()
        except FileNotFoundError:
            self._model_file_missing = True
            self._show_overlay(
                "モデルが読み込まれていません\n\n"
                "model フォルダに GGUF を置くか、\n"
                "ファイル → モデルを選択… から指定してください。"
            )
            self._set_input_enabled(False)
            return

        self._start_model_load(initial=True)

    def _start_model_load(self, *, initial: bool = False) -> None:
        if self._model_loading:
            return
        if is_model_loaded(self.model_path):
            if initial:
                self._show_overlay("モデル起動完了")
                self._hide_overlay_after(1200)
            self._set_input_enabled(True)
            self._update_context_meter()
            return

        self._model_loading = True
        self._set_input_enabled(False)
        self._show_overlay("AIモデルを読み込み中…\n\n初回は 1〜2 分かかることがあります。")

        def worker() -> None:
            err: str | None = None
            try:
                preload_model(self.model_path)
            except Exception as exc:
                err = str(exc)

            def finish() -> None:
                self._model_loading = False
                if err:
                    self._show_overlay(f"モデルの読み込みに失敗しました\n\n{err}")
                    self._set_input_enabled(False)
                    return
                self._show_overlay("モデル起動完了")
                self._hide_overlay_after(1200)
                self._set_input_enabled(True)
                self._update_context_meter()

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _update_window_title(self) -> None:
        """ウィンドウタイトルに読み込みモデル名を反映する。"""
        name = _model_display_name(self.model_path)
        self.root.title(f"{_APP_NAME}（{name}）")

    def save_chat(self):
        if not self.history_data:
            self._dlg_info("会話の保存", "保存する会話がありません。")
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
            self._dlg_info("会話の保存", f"保存しました:\n{path}")
        except Exception as ex:
            self._dlg_error("会話の保存", f"保存に失敗しました:\n{ex}")

    def load_chat(self):
        if self.gen_thread and self.gen_thread.is_alive():
            self._dlg_info("お待ちください", "生成中は読み込めません。")
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
            self._dlg_error("会話の読み込み", f"読み込めませんでした:\n{ex}")
            return

        # wipe current session
        self.on_clear()

        self.history_data = data
        self.history_text.config(state="normal")

        for entry in self.history_data:
            user_msg, assist_msg = entry["user"], entry["assistant"]
            self._append_user_message(user_msg)
            self._append_assistant_header()
            assist_start = self.history_text.index("end-1c")
            if assist_msg:
                self.history_text.insert(tk.END, f"{assist_msg}\n", "assistant_msg")
            assist_end = self.history_text.index("end-1c")
            self.history_text.insert(tk.END, "\n")
            if assist_msg:
                self._post_process(assist_start, assist_end)

        self.history_text.config(state="disabled")
        self.history_text.see(tk.END)
        self._update_context_meter()
        self._dlg_info("会話の読み込み", f"{len(self.history_data)} 件のやり取りを読み込みました。")


    # ─────────────────── System Prompt Editor ───────────────────
    def edit_system_prompt(self):
        """Open a dialog to edit the system prompt."""
        def save_and_close():
            self.system_prompt = text.get("1.0", tk.END).strip() or "You are a helpful assistant."
            self._update_context_meter()
            win.destroy()

        win = self._make_dialog("システムプロンプトの編集", width=520)
        win.grab_set()

        text = tk.Text(win, wrap=tk.WORD, height=6, width=60)
        text.insert("1.0", self.system_prompt)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=(0, 10))

        tk.Button(btn_frame, text="保存", command=save_and_close).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="キャンセル", command=win.destroy).pack(side=tk.LEFT, padx=5)

        self._style_dialog(win)
        self._center_window(win)
        text.focus_set()

    # ─────────────────── Find dialog ───────────────────
    def open_find(self):
        if hasattr(self, "find_window") and self.find_window.winfo_exists():
            return
        self.find_window = self._make_dialog("検索", width=360)
        self.find_window.protocol("WM_DELETE_WINDOW", self._close_find)

        tk.Label(self.find_window, text="検索:").pack(side=tk.LEFT, padx=(10, 0), pady=10)
        self.find_entry = tk.Entry(self.find_window)
        self.find_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=10)
        self.find_entry.bind("<Return>", lambda e: self.find_next())
        tk.Button(self.find_window, text="次へ", command=self.find_next).pack(
            side=tk.LEFT, padx=(0, 10), pady=10
        )
        self._style_dialog(self.find_window)

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
            self._dlg_info("検索", f"「{pattern}」は見つかりませんでした")
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
            reset_model_cache()
            self.model_path = path
            self._model_file_missing = False
            self._update_window_title()
            self._start_model_load(initial=True)
            self._dlg_info(
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
        self._setup_markdown_styles()

    def zoom_out(self):
        for w in (self.input_text, self.history_text):
            f = tkfont.Font(font=w.cget("font"))
            s = f.cget("size")
            if s > 6:
                f.configure(size=s - 1)
                w.config(font=f)
        self._refresh_bold_font()
        self._setup_markdown_styles()

    def show_about(self):
        win = self._make_dialog("このツールについて", width=480)
        win.resizable(False, False)

        model_name = _model_display_name(self.model_path)
        text = (
            f"{_APP_NAME}\n\n"
            "このツールは、お使いのパソコン上だけで動くローカル AI チャットです。\n"
            "インターネット接続やクラウド API は不要で、入力した文章をもとに\n"
            "AI（大規模言語モデル）が回答を生成します。会話内容は外に送られません。\n\n"
            f"読み込み中のモデル: {model_name}\n\n"
            "【動作環境】\n"
            "・必要メモリ: 約 2 GB\n"
            "・CPU のみで推論（GPU 不要・軽量動作を優先した設計）\n"
            f"・コンテキスト上限: {DEFAULT_N_CTX:,} トークン（n_ctx）\n"
            f"・1 回の最大出力: {DEFAULT_MAX_TOKENS:,} トークン\n\n"
            "【使い方】\n"
            "下部の入力欄に質問を書き、「送信」ボタンまたは Ctrl+S で送ってください。\n"
            "表示 → ダークモード で黒背景・緑文字に切り替えられます。\n"
            "モデルは同梱の model フォルダ内の GGUF を自動で読み込みます。\n\n"
            "製作者: OK"
        )
        lbl = tk.Label(win, text=text, justify=tk.LEFT, padx=15, pady=15)
        lbl.pack(anchor="w")

        tk.Button(win, text="閉じる", command=win.destroy, width=10).pack(pady=(0, 15))

        self._style_dialog(win)
        self._center_window(win)

    # ─────────────────── Chat actions ───────────────────
    def on_send(self):
        if self.gen_thread and self.gen_thread.is_alive():
            self._dlg_info(
                "お待ちください",
                "応答を生成中です。\n先に Ctrl+Z で停止してください。",
            )
            return

        if self._model_loading:
            self._dlg_info(
                "お待ちください",
                "AIモデルを読み込み中です。完了までお待ちください。",
            )
            return

        try:
            resolve_model_path(self.model_path)
        except FileNotFoundError:
            self._model_file_missing = True
            self._show_overlay(
                "モデルが読み込まれていません\n\n"
                "model フォルダに GGUF を置くか、\n"
                "ファイル → モデルを選択… から指定してください。"
            )
            self._set_input_enabled(False)
            return

        if not is_model_loaded(self.model_path):
            self._start_model_load()
            self._dlg_info(
                "お待ちください",
                "AIモデルを読み込み中です。完了後に再度送信してください。",
            )
            return

        user_text = self.input_text.get("1.0", tk.END).strip()
        if not user_text:
            return

        self.history_data.append(
            {"user": user_text, "assistant": "", "user_llm": user_text}
        )

        self.history_text.config(state="normal")
        self._append_user_message(user_text)
        self._append_assistant_header()
        self.input_text.delete("1.0", tk.END)
        self.history_text.see(tk.END)
        self._update_context_meter()

        prev = [
            (d.get("user_llm", d["user"]), d["assistant"])
            for d in self.history_data[:-1]
        ]

        self._start_typing_spinner()
        self.history_text.config(state="disabled")

        self.queue = queue.Queue()
        self.stop_event.clear()
        self.gen_thread = threading.Thread(
            target=self._worker_generate,
            args=(user_text, prev),
            daemon=True,
        )
        self.gen_thread.start()
        self.history_text.after(50, self._process_queue)

    def on_stop(self):
        if self.gen_thread and self.gen_thread.is_alive():
            self.stop_event.set()
            self._stop_typing_spinner()

    def on_clear(self):
        if self.gen_thread and self.gen_thread.is_alive():
            self._dlg_info("お待ちください", "生成中はクリアできません。")
            return
        self._stop_typing_spinner()
        self.history_data.clear()
        self.history_text.config(state="normal")
        self.history_text.delete("1.0", tk.END)
        self.history_text.config(state="disabled")
        self.input_text.delete("1.0", tk.END)
        self.assistant_segments.clear()
        self._update_context_meter()

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
                self._stop_typing_spinner()
                self.history_text.config(state="normal")
                end_pos = self.history_text.index("end-1c")
                self.history_text.insert(tk.END, "\n")
                self._post_process(self.assist_start, end_pos)
                self.history_text.tag_add("assistant_msg", self.assist_start, end_pos)
                self.history_text.config(state="disabled")
                self._update_context_meter()
                return
            at_bot = float(self.history_text.yview()[1]) >= 0.99
            self.history_text.config(state="normal")
            if not self._got_first_token and item:
                self._stop_typing_spinner()
                self._got_first_token = True
            self.history_text.insert(tk.END, item, "assistant_msg")
            self.history_text.config(state="disabled")
            if at_bot:
                self.history_text.see(tk.END)
        if self.gen_thread and self.gen_thread.is_alive():
            self.history_text.after(50, self._process_queue)

    # ─────────────────── Post-processing ───────────────────
    def _post_process(self, start: str, end: str):
        raw = self.history_text.get(start, end)
        formatted, render_lines = format_assistant_markdown(raw)

        for tag in (
            "md_h1",
            "md_h2",
            "md_h3",
            "md_h4",
            "md_hr",
            "md_bullet",
            "md_table",
        ):
            self.history_text.tag_remove(tag, start, end)

        if formatted != raw:
            self.history_text.delete(start, end)
            self.history_text.insert(start, formatted)

        new_end = self._apply_markdown_line_tags(start, render_lines)

        self.history_text.tag_remove("user_word", start, new_end)
        self._highlight_user_words(start, new_end)
        self.history_text.tag_add("assistant_msg", start, new_end)
        self.assistant_segments.append((start, new_end))

    def _apply_markdown_line_tags(self, start: str, render_lines: list[RenderLine]) -> str:
        """行ごとに Markdown 用タグを付与し、ブロック末尾インデックスを返す。"""
        if not render_lines:
            return start

        line_idx = start
        for rl in render_lines:
            line_end = f"{line_idx} lineend"
            tag = line_kind_to_tag(rl.kind)
            if tag:
                self.history_text.tag_add(tag, line_idx, line_end)
            line_idx = self.history_text.index(f"{line_idx} +1line")

        return self.history_text.index(f"{line_idx} -1c")

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
            self.user_prompts_win = self._make_dialog("プロンプト一覧", width=500)

            self.user_prompts_text = tk.Text(
                self.user_prompts_win,
                wrap=tk.WORD,
                state="disabled",
                bd=0,
                highlightthickness=0,
            )
            self.user_prompts_text.tag_config("clicked_word", background=self.theme.find_highlight)
            self.user_prompts_text.tag_config("focus_word", background=self.theme.border)

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
            self._style_scrollbar(vscroll)
            self._style_dialog(self.user_prompts_win)

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


def run_app() -> None:
    """Create Tk root and start the main loop (used by main.py)."""
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    _configure_ui_fonts(root)
    ChatGUI(root)
    root.mainloop()
