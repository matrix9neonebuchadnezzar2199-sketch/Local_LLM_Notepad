"""Owl-Bot UI テーマ（ライト / ダーク）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppTheme:
    """Tkinter ウィジェットへ適用する配色セット。"""

    name: str
    bg: str
    fg: str
    history_bg: str
    history_fg: str
    prompt_bg: str
    prompt_input_bg: str
    prompt_input_fg: str
    border: str
    send_bg: str
    send_fg: str
    send_active: str
    attach_bg: str
    attach_fg: str
    attach_active: str
    muted: str
    status_bg: str
    status_fg: str
    find_highlight: str
    find_highlight_fg: str
    md_h1: str
    md_h2: str
    md_h3: str
    md_h4: str
    md_hr: str
    md_table_bg: str
    md_table_fg: str
    role_label: str
    user_bubble_bg: str
    user_bubble_fg: str
    assistant_bubble_bg: str
    assistant_bubble_fg: str
    typing_fg: str
    scrollbar_trough: str
    scrollbar_bg: str
    menu_bg: str
    menu_fg: str
    menu_active_bg: str
    menu_active_fg: str
    button_bg: str
    button_fg: str
    button_active_bg: str
    entry_bg: str
    entry_fg: str
    insert_bg: str


LIGHT_THEME = AppTheme(
    name="light",
    bg="#ffffff",
    fg="#1a1a1a",
    history_bg="#eceff1",
    history_fg="#1a1a1a",
    prompt_bg="#dce6f2",
    prompt_input_bg="#f4f7fb",
    prompt_input_fg="#1a1a1a",
    border="#3d5a80",
    send_bg="#3d5a80",
    send_fg="#ffffff",
    send_active="#2c4260",
    attach_bg="#5a7a9a",
    attach_fg="#ffffff",
    attach_active="#4a6a8a",
    muted="#8e8e93",
    status_bg="#eef2f7",
    status_fg="#3d5a80",
    find_highlight="#fff59d",
    find_highlight_fg="#1a1a1a",
    md_h1="#1a365d",
    md_h2="#2c5282",
    md_h3="#2d3748",
    md_h4="#4a5568",
    md_hr="#3d5a80",
    md_table_bg="#eef2f7",
    md_table_fg="#1a202c",
    role_label="#8e8e93",
    user_bubble_bg="#8de055",
    user_bubble_fg="#111111",
    assistant_bubble_bg="#c8e6ff",
    assistant_bubble_fg="#111111",
    typing_fg="#5a6d82",
    scrollbar_trough="#e8ecf0",
    scrollbar_bg="#b0bec5",
    menu_bg="#f0f0f0",
    menu_fg="#1a1a1a",
    menu_active_bg="#3d5a80",
    menu_active_fg="#ffffff",
    button_bg="#e8ecf0",
    button_fg="#1a1a1a",
    button_active_bg="#d0d8e0",
    entry_bg="#ffffff",
    entry_fg="#1a1a1a",
    insert_bg="#1a1a1a",
)

DARK_THEME = AppTheme(
    name="dark",
    bg="#000000",
    fg="#33ff66",
    history_bg="#000000",
    history_fg="#33ff66",
    prompt_bg="#050505",
    prompt_input_bg="#0a0a0a",
    prompt_input_fg="#33ff66",
    border="#1a9933",
    send_bg="#1a9933",
    send_fg="#000000",
    send_active="#33ff66",
    attach_bg="#0d4d1a",
    attach_fg="#33ff66",
    attach_active="#1a9933",
    muted="#1a9933",
    status_bg="#050505",
    status_fg="#33ff66",
    find_highlight="#1a4d1a",
    find_highlight_fg="#66ff99",
    md_h1="#66ff99",
    md_h2="#55ee88",
    md_h3="#44dd77",
    md_h4="#33cc66",
    md_hr="#1a9933",
    md_table_bg="#0a1a0a",
    md_table_fg="#66ff99",
    role_label="#7a9e7a",
    user_bubble_bg="#06c755",
    user_bubble_fg="#000000",
    assistant_bubble_bg="#1e4d6b",
    assistant_bubble_fg="#d6ecff",
    typing_fg="#1a9933",
    scrollbar_trough="#0a0a0a",
    scrollbar_bg="#1a4d1a",
    menu_bg="#000000",
    menu_fg="#33ff66",
    menu_active_bg="#1a9933",
    menu_active_fg="#000000",
    button_bg="#0a1a0a",
    button_fg="#33ff66",
    button_active_bg="#1a4d1a",
    entry_bg="#0a0a0a",
    entry_fg="#33ff66",
    insert_bg="#33ff66",
)

THEMES: dict[str, AppTheme] = {
    "light": LIGHT_THEME,
    "dark": DARK_THEME,
}
