"""軽量 Markdown → 表示用テキスト変換（Tkinter Text タグ付け用）。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterable

_TABLE_BLOCK = re.compile(
    r"(\|[^\n]+\|\n\|[ \-:|]+\|\n(?:\|[^\n]+\|\n?)+)",
    re.MULTILINE,
)
_TABLE_BLOCK_LOOSE = re.compile(
    r"((?:\|[^\n]+\|\n){2,})",
    re.MULTILINE,
)
_HR_LINE = re.compile(r"^---+\s*$")
_HEADER = re.compile(r"^(#{1,4})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[*\-]\s+(.*)$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


class LineKind(Enum):
    PLAIN = auto()
    H1 = auto()
    H2 = auto()
    H3 = auto()
    H4 = auto()
    HR = auto()
    BULLET = auto()
    TABLE = auto()


@dataclass(frozen=True)
class RenderLine:
    text: str
    kind: LineKind


def _md_table_to_box(md: str) -> str:
    """Markdown パイプ表を罫線付きの等幅ブロックに整形する。"""
    lines = [ln for ln in md.strip().splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        return md.strip()

    rows: list[list[str]] = []
    for ln in lines:
        if re.match(r"^\|[\s\-:|]+\|\s*$", ln):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if cells:
            rows.append(cells)

    if not rows:
        return md.strip()

    col_count = max(len(r) for r in rows)
    for row in rows:
        while len(row) < col_count:
            row.append("")

    widths = [
        max(len(rows[r][c]) for r in range(len(rows)))
        for c in range(col_count)
    ]

    def fmt_row(cells: list[str]) -> str:
        parts = [cells[i].ljust(widths[i]) for i in range(col_count)]
        return "│ " + " │ ".join(parts) + " │"

    horiz = "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"
    top = "┌" + "┬".join("─" * (w + 2) for w in widths) + "┐"
    bottom = "└" + "┴".join("─" * (w + 2) for w in widths) + "┘"

    out = [top, fmt_row(rows[0]), horiz]
    for row in rows[1:]:
        out.append(fmt_row(row))
    out.append(bottom)
    return "\n".join(out)


def _classify_line(line: str) -> RenderLine:
    if _HR_LINE.match(line.strip()):
        return RenderLine("─" * 48, LineKind.HR)

    hm = _HEADER.match(line)
    if hm:
        level = len(hm.group(1))
        text = hm.group(2).strip()
        kind = {1: LineKind.H1, 2: LineKind.H2, 3: LineKind.H3}.get(level, LineKind.H4)
        return RenderLine(text, kind)

    bm = _BULLET.match(line)
    if bm:
        indent = "  " * (len(bm.group(1)) // 2 + 1)
        return RenderLine(f"{indent}• {bm.group(2).strip()}", LineKind.BULLET)

    if line.strip().startswith("|") and "|" in line:
        return RenderLine(line, LineKind.TABLE)

    # インライン整形（見出し・箇条書き以外）
    text = _LINK.sub(r"\1 (\2)", line)
    text = _BOLD.sub(r"\1", text)
    return RenderLine(text, LineKind.PLAIN)


def format_assistant_markdown(raw: str) -> tuple[str, list[RenderLine]]:
    """応答 Markdown を表示用テキストへ。表ブロックは先に箱型へ変換。"""
    text = raw
    text = _TABLE_BLOCK.sub(lambda m: "\n" + _md_table_to_box(m.group(1)) + "\n", text)

    def _loose_table_sub(match: re.Match[str]) -> str:
        block = match.group(1)
        if any(re.match(r"^\|[\s\-:|]+\|\s*$", ln) for ln in block.splitlines()):
            return block
        return "\n" + _md_table_to_box(block) + "\n"

    text = _TABLE_BLOCK_LOOSE.sub(_loose_table_sub, text)

    # 連続空行を抑える
    text = re.sub(r"\n{3,}", "\n\n", text)

    render_lines: list[RenderLine] = []
    out_lines: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("┌") or line.strip().startswith("│") or line.strip().startswith("├") or line.strip().startswith("└"):
            rl = RenderLine(line, LineKind.TABLE)
        else:
            rl = _classify_line(line)
        render_lines.append(rl)
        out_lines.append(rl.text)

    return "\n".join(out_lines), render_lines


def line_kind_to_tag(kind: LineKind) -> str | None:
    mapping = {
        LineKind.H1: "md_h1",
        LineKind.H2: "md_h2",
        LineKind.H3: "md_h3",
        LineKind.H4: "md_h4",
        LineKind.HR: "md_hr",
        LineKind.BULLET: "md_bullet",
        LineKind.TABLE: "md_table",
    }
    return mapping.get(kind)
