"""Load product logos from SVG (rasterized via PyMuPDF or CairoSVG) for Tkinter."""

from __future__ import annotations

import io
import re
from pathlib import Path

import tkinter as tk


def _parse_svg_intrinsic_size(svg_path: Path) -> tuple[float, float] | None:
    text = svg_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(
        r'viewBox="\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*"',
        text,
    )
    if m:
        return float(m.group(3)), float(m.group(4))
    m = re.search(r'<svg[^>]*\bwidth="(\d+(?:\.\d+)?)"[^>]*\bheight="(\d+(?:\.\d+)?)"', text)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'<svg[^>]*\bheight="(\d+(?:\.\d+)?)"[^>]*\bwidth="(\d+(?:\.\d+)?)"', text)
    if m:
        return float(m.group(2)), float(m.group(1))
    return None


def _intrinsic_size_from_fitz(svg_path: Path) -> tuple[float, float] | None:
    try:
        import fitz
    except ImportError:
        return None
    try:
        doc = fitz.open(stream=svg_path.read_bytes(), filetype="svg")
        r = doc[0].rect
        doc.close()
        if r.width <= 0 or r.height <= 0:
            return None
        return float(r.width), float(r.height)
    except Exception:
        return None


def _svg_intrinsic_size(svg_path: Path) -> tuple[float, float] | None:
    p = _parse_svg_intrinsic_size(svg_path)
    if p:
        return p
    return _intrinsic_size_from_fitz(svg_path)


def _resolve_intrinsic_size(svg_path: Path) -> tuple[float, float]:
    """Width/height in SVG user units (or pixel probe if metadata is missing)."""
    p = _svg_intrinsic_size(svg_path)
    if p:
        return p
    im = _rasterize_svg_fitz(svg_path, 64.0)
    if im is None:
        im = _rasterize_svg_cairo(svg_path, 64)
    if im is not None:
        return float(im.width), float(im.height)
    return 200.0, 48.0


def _target_pixel_size(
    iw: float,
    ih: float,
    max_width: int | None,
    max_height: int,
) -> tuple[int, int]:
    """Fit inside max_width x max_height, preserve aspect ratio, never upscale."""
    if iw <= 0 or ih <= 0:
        return 1, 1
    mw = max_width if max_width is not None else 10_000
    s = min(mw / iw, max_height / ih, 1.0)
    tw = max(1, int(round(iw * s)))
    th = max(1, int(round(ih * s)))
    return tw, th


def _rasterize_svg_fitz(svg_path: Path, pixel_height: float) -> "Image.Image | None":
    try:
        import fitz
    except ImportError:
        return None
    try:
        from PIL import Image

        svg = svg_path.read_bytes()
        doc = fitz.open(stream=svg, filetype="svg")
        page = doc[0]
        rh = float(page.rect.height)
        if rh <= 0:
            doc.close()
            return None
        zoom = pixel_height / rh
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True)
        doc.close()
        return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
    except Exception:
        return None


def _rasterize_svg_cairo(svg_path: Path, pixel_height: int) -> "Image.Image | None":
    try:
        import cairosvg
    except (ImportError, OSError):
        return None
    try:
        from PIL import Image

        data = cairosvg.svg2png(url=str(svg_path), output_height=pixel_height)
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        return None


def _rasterize_svg(svg_path: Path, pixel_height: float) -> "Image.Image | None":
    """Rasterize SVG to a PIL image at the given pixel height (width follows aspect)."""
    im = _rasterize_svg_fitz(svg_path, pixel_height)
    if im is None:
        im = _rasterize_svg_cairo(svg_path, int(round(pixel_height)))
    return im


def _resize_to_target(
    im: "Image.Image",
    target_w: int,
    target_h: int,
) -> "Image.Image":
    from PIL import Image

    if im.width == target_w and im.height == target_h:
        return im
    return im.resize((target_w, target_h), Image.Resampling.LANCZOS)


def _image_to_photo(master: tk.Misc, im: "Image.Image") -> tk.PhotoImage | None:
    try:
        from PIL import ImageTk

        return ImageTk.PhotoImage(im, master=master)
    except Exception:
        return None


def load_product_logo(
    master: tk.Misc,
    svg_filename: str,
    assets_dir: Path,
    *,
    max_height: int = 32,
    max_width: int | None = 220,
) -> tk.PhotoImage | None:
    """Load logo for the product bar from SVG.

    Rasterizes ``assets_dir / svg_filename`` using PyMuPDF (or CairoSVG as fallback).
    Wide wordmarks are scaled to fit ``max_width`` x ``max_height`` with 4x supersampling.
    """
    if not svg_filename.strip():
        return None

    svg_path = assets_dir / svg_filename
    if not svg_path.is_file():
        return None

    iw, ih = _resolve_intrinsic_size(svg_path)
    tw, th = _target_pixel_size(iw, ih, max_width, max_height)
    render_h = min(512.0, float(th * 4))
    im = _rasterize_svg(svg_path, render_h)
    if im is None:
        return None
    im = _resize_to_target(im, tw, th)
    return _image_to_photo(master, im)
