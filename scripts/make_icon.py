"""Generate local PWA icons from simple vector shapes (requires Pillow)."""

from pathlib import Path
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "public" / "icons"
DEST.mkdir(parents=True, exist_ok=True)

for size in (192, 512):
    image = Image.new("RGB", (size, size), "#0b1220")
    draw = ImageDraw.Draw(image)
    margin = int(size * 0.09)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=int(size * 0.23),
        fill="#70d8df",
    )
    cx = cy = size // 2
    r = int(size * 0.20)
    draw.polygon(
        [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
        fill="#092b38",
    )
    image.save(DEST / f"icon-{size}.png", optimize=True)
