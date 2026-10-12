"""Draw the Android app's launcher icon from the same geometry as every other Whiskers icon.

    python android/make_icons.py

Android 8 and later build a launcher icon from layers: a background (the teal, set in
res/values/colors.xml), a foreground (the cat, drawn here on a transparent square) and a
monochrome copy that Android 13 tints to match the wallpaper. The launcher crops the
square to a circle, a squircle or whatever shape the phone uses, and only the middle 66
of its 108 units are sure to survive the crop, so the cat is drawn to fit inside that.
"""

from __future__ import annotations

import pathlib
import sys

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import make_icons as logo  # noqa: E402  (the shared geometry: HEAD, WHISKERS, ALERT...)

RES = pathlib.Path(__file__).resolve().parent / "app" / "src" / "main" / "res"
#: Pixels across the 108-unit adaptive icon at each screen density.
DENSITIES = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}
#: How wide the cat is, whisker tip to whisker tip, in the 108 units. Corners of the
#: whiskers are the parts nearest the edge of a round crop; at 56 they clear it.
WIDTH = 56.0


def draw(px: int, monochrome: bool = False) -> Image.Image:
    big = px * 4                                         # drawn large, scaled down: smooth
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    head = logo._flatten(logo.HEAD)
    xs = [x for line in logo.WHISKERS + [logo.ALERT] for x, _ in line] + [x for x, _ in head]
    ys = [y for line in logo.WHISKERS + [logo.ALERT] for _, y in line] + [y for _, y in head]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    unit = big / 108.0
    scale = WIDTH / (max(xs) - min(xs)) * unit

    def P(x, y):
        return (big / 2 + (x - cx) * scale, big / 2 + (y - cy) * scale)

    face = (255, 255, 255, 255) if monochrome else logo.FACE + (255,)
    hole = (0, 0, 0, 0) if monochrome else logo.TILE + (255,)
    accent = (255, 255, 255, 255) if monochrome else logo.ACCENT + (255,)
    d.polygon([P(*q) for q in head], fill=face)
    for ex in (25, 39):                                  # eyes
        r = 2.9 * scale
        x, y = P(ex, 32.5)
        d.ellipse([x - r, y - r, x + r, y + r], fill=hole)
    d.polygon([P(29.8, 38.6), P(34.2, 38.6), P(32, 41.4)], fill=hole)    # nose
    w = max(1, int(2.2 * scale))
    for line in logo.WHISKERS:
        d.line([P(*q) for q in line], fill=face, width=w, joint="curve")
    d.line([P(*q) for q in logo.ALERT], fill=accent, width=max(1, int(2.6 * scale)), joint="curve")
    for x, y in (logo.ALERT[0], logo.ALERT[-1]):
        ex, ey = P(x, y)
        r = 1.3 * scale
        d.ellipse([ex - r, ey - r, ex + r, ey + r], fill=accent)
    return im.resize((px, px), Image.LANCZOS)


def main() -> None:
    for name, px in DENSITIES.items():
        out = RES / f"mipmap-{name}"
        out.mkdir(parents=True, exist_ok=True)
        draw(px).save(out / "ic_launcher_foreground.png", optimize=True)
        draw(px, monochrome=True).save(out / "ic_launcher_monochrome.png", optimize=True)
    print(f"wrote the launcher icon layers for {len(DENSITIES)} screen densities")


if __name__ == "__main__":
    main()
