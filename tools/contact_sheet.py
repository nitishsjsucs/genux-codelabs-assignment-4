"""Optional: tile the 28 lab screenshots into docs/screenshots/contact-sheet.png (needs Pillow)."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import registry  # noqa: E402

SHOTS = ROOT / "docs" / "screenshots"
W, H, PAD, LABEL = 320, 275, 8, 18
rows = registry.TECHS
sheet = Image.new("RGB", (PAD + 4 * (W + PAD), PAD + len(rows) * (H + LABEL + PAD)), "white")
draw = ImageDraw.Draw(sheet)
for r, (tech, name, _d) in enumerate(rows):
    for c, mode in enumerate(registry.MODES):
        img = Image.open(SHOTS / f"{tech}-{mode}.png").convert("RGB")
        img = img.crop((0, 0, img.width, int(img.width * H / W)))
        img.thumbnail((W, H))
        x, y = PAD + c * (W + PAD), PAD + r * (H + LABEL + PAD)
        draw.text((x, y), f"{name} - {registry.MODE_TITLES[mode]}", fill="black")
        sheet.paste(img, (x, y + LABEL))
sheet.save(SHOTS / "contact-sheet.png", optimize=True)
print(f"wrote docs/screenshots/contact-sheet.png ({sheet.width}x{sheet.height})")
