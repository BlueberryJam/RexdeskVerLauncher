"""Generate assets/app-icon.ico from the REXDESK brand mark (4-square Z pattern)."""
from pathlib import Path
from PIL import Image, ImageDraw


def _draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    yellow = (245, 204, 0, 255)  # #F5CC00  (REXDESK logo colour, 300-stop)

    # Layout: 2-col × 3-row grid, 4 squares in Z/staircase shape
    #   . X   (row 0)
    #   X X   (row 1)
    #   X .   (row 2)
    # Height is the binding dimension; we leave 14% padding each side.
    padding = round(size * 0.14)
    avail_h = size - 2 * padding
    avail_w = size - 2 * padding
    gap = max(1, round(size * 0.04))
    sq = (avail_h - 2 * gap) // 3

    pattern_w = 2 * sq + gap
    x0 = padding + (avail_w - pattern_w) // 2
    y0 = padding

    col0 = x0
    col1 = x0 + sq + gap
    row0 = y0
    row1 = y0 + sq + gap
    row2 = y0 + 2 * (sq + gap)

    draw.rectangle([col1, row0, col1 + sq - 1, row0 + sq - 1], fill=yellow)
    draw.rectangle([col0, row1, col0 + sq - 1, row1 + sq - 1], fill=yellow)
    draw.rectangle([col1, row1, col1 + sq - 1, row1 + sq - 1], fill=yellow)
    draw.rectangle([col0, row2, col0 + sq - 1, row2 + sq - 1], fill=yellow)

    return img


sizes = [256, 128, 64, 48, 32, 16]
images = [_draw_icon(s) for s in sizes]

assets = Path(__file__).parent / "assets"

ico_out = assets / "app-icon.ico"
images[0].save(ico_out, format="ICO", append_images=images[1:])
print(f"Icon written to {ico_out}")

png_out = assets / "app-icon.png"
images[0].save(png_out, format="PNG")
print(f"PNG written to {png_out}")
