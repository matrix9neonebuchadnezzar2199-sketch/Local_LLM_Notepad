"""ビルド用: ソース画像から高解像度 Owl-Bot.ico / Owl-Bot.png を生成する。"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PIL import Image

_PNG_SIZE = 512
_ICO_SIZES = (16, 32, 48, 64, 128, 256)


def _to_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def _prepare_native(img: Image.Image) -> Image.Image:
    """透過付き正方形の原画。"""
    return _to_square(img.convert("RGBA"))


def _verify_ico(path: Path, min_images: int = 6) -> None:
    with path.open("rb") as f:
        f.read(4)
        (count,) = struct.unpack("<H", f.read(2))
    if count < min_images:
        raise RuntimeError(f"{path} has only {count} images; expected >={min_images}")


def generate_icons(source: Path, out_dir: Path) -> None:
    """ICO（EXE 用）と PNG（配布用プレビュー）を出力する。

    各 ICO フレームは 512px 原画から個別に LANCZOS で縮小する。
    Pillow 内蔵の ICO ダウンスケーラに任せず明示的に高品質縮小することで、
    16/32/48px の小アイコンがぼやけるのを防ぐ。
    """
    if not source.is_file():
        raise FileNotFoundError(f"Icon source not found: {source}")

    out_dir.mkdir(parents=True, exist_ok=True)
    ico_path = out_dir / "Owl-Bot.ico"
    png_path = out_dir / "Owl-Bot.png"

    with Image.open(source) as raw:
        native = _prepare_native(raw)
        if native.width < 256:
            raise ValueError(
                f"Icon source too small ({native.width}px). Use at least 256x256 PNG."
            )

        # 各サイズを原画から個別に高品質縮小したフレーム群
        frames = [
            native.resize((size, size), Image.Resampling.LANCZOS)
            for size in _ICO_SIZES
        ]
        # 最大フレーム(256)を基準に、残りを append_images で同梱
        largest = frames[-1]
        largest.save(
            ico_path,
            format="ICO",
            sizes=[(s, s) for s in _ICO_SIZES],
            append_images=frames[:-1],
        )

        preview = native.resize((_PNG_SIZE, _PNG_SIZE), Image.Resampling.LANCZOS)
        preview.save(png_path, format="PNG", optimize=True)

    _verify_ico(ico_path)
    print(
        f"Wrote {ico_path} ({len(_ICO_SIZES)} sizes, per-size LANCZOS from "
        f"{native.width}px, png {_PNG_SIZE}px)"
    )
    print(f"Wrote {png_path}")


def main() -> None:
    notepad_dir = Path(__file__).resolve().parent
    default_src = notepad_dir.parent / "Images" / "7tkhqJx7.png"
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_src
    generate_icons(source, notepad_dir)


if __name__ == "__main__":
    main()
