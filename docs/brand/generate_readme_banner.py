"""Draw the NEXRON README banner of a repository, in a dark and a light variant.

One look for every NEXRON repo (first built for Nota, after NEXRON Hive): centred row of
app icon, product name in white (dark on the light variant), a divider and the NEXRON
Studios logo, the tagline below, a short accent bar in the brand colour, a faint pattern
that fades in towards the edges.

GitHub shows README images through a proxy that loads no web fonts, so all text becomes
outlines here. Template from the `readme-banner` skill; each repo keeps its own copy in
docs/brand/ with assets/ next to it, plus banner.json, so a rerun needs nothing outside it.

    uv run --with fonttools --with brotli docs/brand/generate_readme_banner.py docs/brand/banner.json
"""

import base64
import json
import math
import mimetypes
import re
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ASSETS = Path(__file__).resolve().parent / "assets"
DEFAULT_WORDMARK_FONT = ASSETS / "climate-crisis.woff2"
DEFAULT_TAGLINE_FONT = ASSETS / "geist.woff2"
NEXRON_LOGO = ASSETS / "nexron_logo.svg"

WIDTH, HEIGHT = 1280, 340
CORNER_RADIUS = 28
SIDE_MARGIN = 90
GLYPH_SIZE = 102
GAP = 40
LOGO_HEIGHT = 72
WORDMARK_SIZE = 118
TAGLINE_SIZE = 34
ROW_BASELINE = 182
TAGLINE_BASELINE = 262
PATTERN_STEP = 30

SURFACES = {
    "dark": {"surface": "#0e0e0f", "border": "#2c2c2d", "ink": "#f0efec", "pattern_opacity": 0.16},
    "light": {"surface": "#f7f6f3", "border": "#e2e0da", "ink": "#1d1c1a", "pattern_opacity": 0.2},
}


def outline(font: TTFont, text: str, x: float, baseline: float, size: float) -> tuple[str, float]:
    """The text as one SVG path, and its advance width at `size`."""
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = size / font["head"].unitsPerEm
    pen = SVGPathPen(glyphs)
    cursor = 0.0
    for char in text:
        name = cmap.get(ord(char)) or cmap[ord("?")]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x + cursor, baseline)))
        cursor += glyphs[name].width * scale
    return pen.getCommands(), cursor


def fitted_size(font: TTFont, text: str, size: float, max_width: float) -> float:
    """Shrinks long names and taglines until they fit, so every repo keeps one layout."""
    _, width = outline(font, text, 0, 0, size)
    return size if width <= max_width else size * max_width / width


def embedded_image(path: Path, x: float, y: float, width: float, height: float) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/svg+xml"
    data = base64.b64encode(path.read_bytes()).decode()
    return (f'<image x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
            f'preserveAspectRatio="xMidYMid meet" href="data:{mime};base64,{data}"/>')


def nexron_width() -> float:
    view_box = re.search(r'viewBox="([^"]+)"', NEXRON_LOGO.read_text()).group(1).split()
    return LOGO_HEIGHT * float(view_box[2]) / float(view_box[3])


def hexagon(cx: float, cy: float, radius: float) -> str:
    points = " ".join(
        f"{cx + radius * math.cos(math.radians(60 * i - 30)):.1f},{cy + radius * math.sin(math.radians(60 * i - 30)):.1f}"
        for i in range(6)
    )
    return f'<polygon points="{points}"/>'


def pattern_shapes(kind: str) -> str:
    if kind == "ruled":
        return "".join(f'<line x1="0" x2="{WIDTH}" y1="{y}" y2="{y}"/>' for y in range(PATTERN_STEP, HEIGHT, PATTERN_STEP))
    if kind == "grid":
        rows = "".join(f'<line x1="0" x2="{WIDTH}" y1="{y}" y2="{y}"/>' for y in range(PATTERN_STEP, HEIGHT, PATTERN_STEP))
        cols = "".join(f'<line y1="0" y2="{HEIGHT}" x1="{x}" x2="{x}"/>' for x in range(PATTERN_STEP, WIDTH, PATTERN_STEP))
        return rows + cols
    if kind == "dots":
        return "".join(
            f'<circle cx="{x}" cy="{y}" r="1.6" stroke="none"/>'
            for y in range(PATTERN_STEP // 2, HEIGHT, PATTERN_STEP) for x in range(PATTERN_STEP // 2, WIDTH, PATTERN_STEP)
        )
    if kind == "comb":
        radius = 34
        step_x, step_y = radius * math.sqrt(3), radius * 1.5
        return "".join(
            hexagon(col * step_x + (row % 2) * step_x / 2, row * step_y, radius - 3)
            for row in range(-1, int(HEIGHT / step_y) + 2) for col in range(-1, int(WIDTH / step_x) + 2)
        )
    return ""


def background_pattern(kind: str, brand: str, opacity: float) -> str:
    """Clear in the middle, fading in towards the edges, so it never fights the name."""
    shapes = pattern_shapes(kind)
    if not shapes:
        return ""
    paint = (f'fill="{brand}" fill-opacity="{opacity}"' if kind == "dots"
             else f'fill="none" stroke="{brand}" stroke-opacity="{opacity}" stroke-width="1.5"')
    return (
        '<radialGradient id="fade" cx="0.5" cy="0.5" r="0.75"><stop offset="0.35" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="1"/></radialGradient>'
        f'<mask id="patternMask"><rect width="{WIDTH}" height="{HEIGHT}" fill="url(#fade)"/></mask>'
        f'<g mask="url(#patternMask)" {paint}>{shapes}</g>'
    )


def banner(config: dict, base: Path, glyph: Path, variant: str) -> str:
    surface = SURFACES[variant]
    brand = config["brand"] if variant == "dark" else config.get("brand_light", config["brand"])
    # A project with its own brand font names it in banner.json; otherwise the NEXRON wordmark face.
    wordmark_font = TTFont(base / config["wordmark_font"] if "wordmark_font" in config else DEFAULT_WORDMARK_FONT)
    tagline_font = TTFont(base / config["tagline_font"] if "tagline_font" in config else DEFAULT_TAGLINE_FONT)
    name, tagline_text = config["name"].upper(), config["tagline"]

    fixed = GLYPH_SIZE + GAP + GAP + 2 + GAP + nexron_width()
    size = fitted_size(wordmark_font, name, WORDMARK_SIZE, WIDTH - 2 * SIDE_MARGIN - fixed)
    _, name_width = outline(wordmark_font, name, 0, 0, size)
    left = (WIDTH - fixed - name_width) / 2
    name_x = left + GLYPH_SIZE + GAP
    cap_shift = (WORDMARK_SIZE - size) * 0.36  # keep smaller names vertically centred on the row
    wordmark, _ = outline(wordmark_font, name, name_x, ROW_BASELINE - cap_shift, size)
    divider_x = name_x + name_width + GAP

    tagline_size = fitted_size(tagline_font, tagline_text, TAGLINE_SIZE, WIDTH - 2 * SIDE_MARGIN)
    _, tagline_width = outline(tagline_font, tagline_text, 0, 0, tagline_size)
    tagline, _ = outline(tagline_font, tagline_text, (WIDTH - tagline_width) / 2, TAGLINE_BASELINE, tagline_size)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}">
<defs>
<clipPath id="tile"><rect width="{WIDTH}" height="{HEIGHT}" rx="{CORNER_RADIUS}"/></clipPath>
<radialGradient id="glow" cx="0.5" cy="0.35" r="0.6"><stop offset="0" stop-color="{brand}" stop-opacity="0.16"/>
<stop offset="1" stop-color="{brand}" stop-opacity="0"/></radialGradient>
</defs>
<g clip-path="url(#tile)">
<rect width="{WIDTH}" height="{HEIGHT}" fill="{surface["surface"]}"/>
{background_pattern(config.get("pattern", "dots"), brand, surface["pattern_opacity"])}
<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#glow)"/>
</g>
<rect x="0.75" y="0.75" width="{WIDTH - 1.5}" height="{HEIGHT - 1.5}" rx="{CORNER_RADIUS}" fill="none" stroke="{surface["border"]}" stroke-width="1.5"/>
{embedded_image(glyph, left, ROW_BASELINE - 97, GLYPH_SIZE, GLYPH_SIZE)}
<path d="{wordmark}" fill="{surface["ink"]}"/>
<rect x="{divider_x:.1f}" y="92" width="2" height="88" rx="1" fill="{surface["border"]}"/>
{embedded_image(NEXRON_LOGO, divider_x + 2 + GAP, 100, nexron_width(), LOGO_HEIGHT)}
<path d="{tagline}" fill="{surface["ink"]}"/>
<rect x="{WIDTH / 2 - 28}" y="290" width="56" height="4" rx="2" fill="{brand}"/>
</svg>
"""


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: generate_banner.py <path/to/banner.json>")
    config_path = Path(sys.argv[1]).resolve()
    config = json.loads(config_path.read_text())
    glyph = (config_path.parent / config["glyph"]).resolve()
    if not glyph.exists():
        sys.exit(f"glyph not found: {glyph}")
    out = (config_path.parent / config.get("out", ".")).resolve()
    for variant in SURFACES:
        (out / f"readme-banner-{variant}.svg").write_text(banner(config, config_path.parent, glyph, variant))
    print(f"wrote readme-banner-dark.svg and readme-banner-light.svg to {out}")


if __name__ == "__main__":
    main()
