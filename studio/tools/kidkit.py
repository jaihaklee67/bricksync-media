"""Kid-friendly visual kit: rounded display fonts, sticker lettering, flat pastel backgrounds and simple drawn decorations.
Style cues come from the reference posts (chunky rounded lettering, bright single-color backgrounds, clouds, bunting, bushes);
no reference artwork, characters or wording is reused. Fonts: Jua, Black Han Sans, Do Hyeon (SIL OFL, in assets/fonts)."""
import math
import pathlib
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from fontTools.ttLib import TTFont

root = pathlib.Path(__file__).parent.parent
FD = root / "assets/fonts"
PINK, BLUE, YELLOW, PURPLE, GREEN, RED = (255, 0, 134), (42, 135, 209), (255, 216, 23), (151, 15, 255), (6, 121, 85), (244, 54, 38)
ORANGE, NAVY, INK, GRAY, WHITE = (232, 118, 10), (30, 41, 99), (26, 26, 26), (90, 90, 100), (255, 255, 255)
LEAF, LEAF2 = (88, 190, 60), (60, 160, 50)
_files = {"jua": "Jua-Regular.ttf", "black": "BlackHanSans-Regular.ttf", "do": "DoHyeon-Regular.ttf"}
_cmaps = {}


def font(kind, size):
    return ImageFont.truetype(str(FD / _files[kind]), size)


def missing_glyphs(kind, text):
    if kind not in _cmaps:
        _cmaps[kind] = set(TTFont(str(FD / _files[kind])).getBestCmap().keys())
    return sorted({ch for ch in text if not ch.isspace() and ord(ch) not in _cmaps[kind]})


def tint(c, t):
    return tuple(round(255 - (255 - v) * t) for v in c)


def flat_bg(size, top, bottom=None):
    w, h = size
    bottom = bottom or top
    g = Image.new("RGB", size)
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(h - 1, 1)
        d.line([(0, y), (w, y)], fill=tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return g.convert("RGBA")


def _over(canvas):
    return Image.new("RGBA", canvas.size, (0, 0, 0, 0))


def sticker(canvas, xy, text, f, fill, sw=10, stroke=WHITE, shadow=True, anchor="la"):
    """Chunky lettering with a white outline and a soft drop shadow."""
    if shadow:
        sh = _over(canvas)
        ImageDraw.Draw(sh).text((xy[0], xy[1] + 8), text, font=f, fill=(0, 0, 0, 70), stroke_width=sw, stroke_fill=(0, 0, 0, 70), anchor=anchor)
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(7)))
    ov = _over(canvas)
    ImageDraw.Draw(ov).text(xy, text, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke, anchor=anchor)
    canvas.alpha_composite(ov)


def sticker_parts(canvas, x, y, parts, f, sw=10):
    d = ImageDraw.Draw(canvas)
    for text, color in parts:
        sticker(canvas, (x, y), text, f, color, sw)
        x += d.textlength(text, font=f)
    return x


def card(canvas, x, y, w, h, fill=WHITE, border=None, radius=40, bw=8, shadow=True):
    if shadow:
        sh = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([30, 36, w + 30, h + 36], radius, fill=(0, 0, 0, 40))
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)), (x - 30, y - 30))
    p = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(p).rounded_rectangle([0, 0, w - 1, h - 1], radius, fill=fill + (255,), outline=(border + (255,)) if border else None, width=bw if border else 0)
    canvas.alpha_composite(p, (x, y))


def photo(canvas, img, x, y, radius=36, border=WHITE, bw=10):
    w, h = img.size
    card(canvas, x - bw, y - bw, w + 2 * bw, h + 2 * bw, fill=border, radius=radius + bw)
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius, fill=255)
    canvas.paste(img.convert("RGB"), (x, y), m)


def label(canvas, x, y, text, color, size=34, kind="jua", padx=28, h=None, text_color=WHITE, border=WHITE):
    f = font(kind, size)
    d = ImageDraw.Draw(canvas)
    tw = round(d.textlength(text, font=f))
    h = h or round(size * 1.8)
    p = Image.new("RGBA", (tw + padx * 2 + 12, h + 12), (0, 0, 0, 0))
    pd = ImageDraw.Draw(p)
    pd.rounded_rectangle([0, 0, p.width - 1, p.height - 1], (h + 12) // 2, fill=border + (255,))
    pd.rounded_rectangle([6, 6, p.width - 7, p.height - 7], h // 2, fill=color + (255,))
    sh = Image.new("RGBA", (p.width + 40, p.height + 40), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([20, 26, p.width + 20, p.height + 26], p.height // 2, fill=(0, 0, 0, 45))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)), (x - 20, y - 20))
    canvas.alpha_composite(p, (x, y))
    ImageDraw.Draw(canvas).text((x + 6 + padx, y + 6 + h / 2), text, font=f, fill=text_color, anchor="lm")
    return p.width


def number_badge(canvas, cx, cy, n, color=ORANGE, r=34):
    d = ImageDraw.Draw(canvas)
    d.ellipse([cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6], fill=WHITE)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    d.text((cx, cy + 2), str(n), font=font("black", int(r * 1.2)), fill=WHITE, anchor="mm")


# ---------- decorations ----------
def cloud(canvas, cx, cy, s=1.0, color=(255, 255, 255, 255)):
    ov = _over(canvas)
    d = ImageDraw.Draw(ov)
    for dx, dy, r in ((-70, 10, 42), (-25, -22, 55), (35, -10, 48), (80, 14, 36)):
        d.ellipse([cx + (dx - r) * s, cy + (dy - r) * s, cx + (dx + r) * s, cy + (dy + r) * s], fill=color)
    d.rounded_rectangle([cx - 110 * s, cy + 6 * s, cx + 115 * s, cy + 52 * s], int(24 * s), fill=color)
    canvas.alpha_composite(ov)


def bunting(canvas, y0=0, sag=60, n=9, colors=(PINK, YELLOW, BLUE, GREEN, PURPLE), x0=-20, x1=None):
    x1 = x1 or canvas.width + 20
    ov = _over(canvas)
    d = ImageDraw.Draw(ov)

    def pt(t):
        return x0 + (x1 - x0) * t, y0 + sag * 4 * t * (1 - t)

    pts = [pt(i / 80) for i in range(81)]
    d.line(pts, fill=(60, 60, 80, 255), width=4)
    for i in range(n):
        t = (i + 0.5) / n
        x, y = pt(t)
        w = (x1 - x0) / n * 0.78
        d.polygon([(x - w / 2, y), (x + w / 2, y), (x, y + w * 1.15)], fill=colors[i % len(colors)] + (255,))
    canvas.alpha_composite(ov)


def bush(canvas, x, y, s=1.0):
    ov = _over(canvas)
    d = ImageDraw.Draw(ov)
    for dx, dy, r, c in ((0, 0, 70, LEAF2), (70, 14, 62, LEAF), (-66, 20, 56, LEAF), (30, -38, 52, LEAF)):
        d.ellipse([x + (dx - r) * s, y + (dy - r) * s, x + (dx + r) * s, y + (dy + r) * s], fill=c + (255,))
    for dx, dy in ((-30, -10), (40, 10), (0, 34), (-70, 24)):
        d.ellipse([x + (dx - 11) * s, y + (dy - 18) * s, x + (dx + 11) * s, y + (dy + 18) * s], fill=(190, 240, 140, 255))
    canvas.alpha_composite(ov)


def sparkle(canvas, cx, cy, r=22, color=(255, 255, 255, 255)):
    ov = _over(canvas)
    pts = []
    for i in range(8):
        a = math.pi / 4 * i - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.32
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    ImageDraw.Draw(ov).polygon(pts, fill=color)
    canvas.alpha_composite(ov)


def dots(canvas, x, y, cols=4, rows=3, gap=34, r=7, color=(255, 255, 255, 200)):
    ov = _over(canvas)
    d = ImageDraw.Draw(ov)
    for i in range(cols):
        for j in range(rows):
            d.ellipse([x + i * gap - r, y + j * gap - r, x + i * gap + r, y + j * gap + r], fill=color)
    canvas.alpha_composite(ov)


def toy_brick(canvas, x, y, w, h, color, studs=2, angle=0):
    """Generic toy brick with studs and no markings."""
    pad = 40
    layer = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    dark = tuple(max(0, int(v * 0.78)) for v in color)
    d.rounded_rectangle([pad, pad, pad + w, pad + h], 14, fill=dark + (255,))
    d.rounded_rectangle([pad, pad, pad + w, pad + h - 10], 14, fill=color + (255,))
    sr = int(min(w / studs, 70) * 0.28)
    for i in range(studs):
        cx = pad + (i + 0.5) * w / studs
        d.rounded_rectangle([cx - sr, pad - sr * 0.9, cx + sr, pad + 4], sr // 2, fill=dark + (255,))
        d.ellipse([cx - sr, pad - sr * 1.25, cx + sr, pad + sr * 0.2], fill=color + (255,))
        d.ellipse([cx - sr * 0.45, pad - sr * 0.95, cx + sr * 0.45, pad - sr * 0.15], fill=tuple(min(255, v + 40) for v in color) + (255,))
    layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, 60), mask=layer.getchannel("A"))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)), (x - pad + 6, y - pad + 10))
    canvas.alpha_composite(layer, (x - pad, y - pad))


def logo(canvas, x=None, y=0, h=64, anchor="right", margin=60):
    lg = Image.open(root / "brand/logos/VerticlaLogo_BL.png").convert("RGBA")
    lg = lg.crop(lg.getchannel("A").getbbox())
    lg = lg.resize((round(lg.width * h / lg.height), h), Image.LANCZOS)
    plate = Image.new("RGBA", (lg.width + 44, lg.height + 30), (0, 0, 0, 0))
    ImageDraw.Draw(plate).rounded_rectangle([0, 0, plate.width - 1, plate.height - 1], 28, fill=(255, 255, 255, 235))
    plate.alpha_composite(lg, (22, 15))
    if x is None:
        x = canvas.width - margin - plate.width if anchor == "right" else (canvas.width - plate.width) // 2
    canvas.alpha_composite(plate, (x, y))
    return (x, y, x + plate.width, y + plate.height)
