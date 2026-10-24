"""Shared helpers for the carousel slides (1080x1350). All Korean text is drawn by code."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import pathlib

root = pathlib.Path(__file__).parent.parent
W, H = 1080, 1350
FONT = r"C:\Windows\Fonts\NotoSansKR-VF.ttf"
PINK, BLUE, YELLOW, PURPLE, GREEN, RED = (255, 0, 134), (42, 135, 209), (255, 216, 23), (151, 15, 255), (6, 121, 85), (244, 54, 38)
INK, GRAY, WHITE = (26, 26, 26), (90, 90, 100), (255, 255, 255)

def font(size, weight=700):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        f = ImageFont.truetype(r"C:\Windows\Fonts\malgunbd.ttf", size)
    return f

def tint(c, t):
    return tuple(round(255 - (255 - v) * t) for v in c)

def vgrad(w, h, top, bottom):
    g = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / (h - 1)
        d.line([(0, y), (w, y)], fill=tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return g

def new_canvas(top=(255, 240, 246), bottom=(232, 244, 255)):
    return vgrad(W, H, top, bottom).convert("RGBA")

def rounded(img, radius):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img.convert("RGB"), (0, 0), m)
    return out

def shadow_box(canvas, x, y, w, h, radius=36, alpha=34):
    sh = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([30, 36, w + 30, h + 36], radius, fill=(0, 0, 0, alpha))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)), (x - 30, y - 30))

def panel(canvas, x, y, w, h, fill=WHITE, radius=36, shadow=True):
    if shadow:
        shadow_box(canvas, x, y, w, h, radius)
    p = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(p).rounded_rectangle([0, 0, w - 1, h - 1], radius, fill=fill + (255,))
    canvas.alpha_composite(p, (x, y))

def pill(canvas, x, y, text, size=32, fill=PINK, color=WHITE, weight=700, padx=26, h=None):
    d = ImageDraw.Draw(canvas)
    f = font(size, weight)
    tw = round(d.textlength(text, font=f))
    h = h or round(size * 1.85)
    p = Image.new("RGBA", (tw + padx * 2, h), (0, 0, 0, 0))
    ImageDraw.Draw(p).rounded_rectangle([0, 0, p.width - 1, h - 1], h // 2, fill=fill + (255,))
    canvas.alpha_composite(p, (x, y))
    d.text((x + padx, y + (h - size * 1.3) / 2 - 2), text, font=f, fill=color)
    return p.width

def wrap(d, text, f, maxw):
    lines, cur = [], ""
    for word in text.split(" "):
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=f) <= maxw:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
        while d.textlength(cur, font=f) > maxw:  # break long words by character
            i = len(cur)
            while i > 1 and d.textlength(cur[:i], font=f) > maxw:
                i -= 1
            lines.append(cur[:i])
            cur = cur[i:]
    if cur:
        lines.append(cur)
    return lines

def text_block(canvas, x, y, text, size, weight, color, maxw, spacing=1.45):
    d = ImageDraw.Draw(canvas)
    f = font(size, weight)
    for ln in wrap(d, text, f, maxw):
        d.text((x, y), ln, font=f, fill=color)
        y += round(size * spacing)
    return y

def footer(canvas, note=None, page=None):  # page numbers are never drawn (user rule 2026-10-24)
    d = ImageDraw.Draw(canvas)
    if note:
        d.text((60, 1284), note, font=font(24, 500), fill=GRAY)
    logo = Image.open(root / "brand/logos/VerticlaLogo_BL.png").convert("RGBA")
    logo = logo.crop(logo.getchannel("A").getbbox())
    lh = 56
    logo = logo.resize((round(logo.width * lh / logo.height), lh), Image.LANCZOS)
    canvas.alpha_composite(logo, (W - 60 - logo.width, 1272))

def cover_crop(src, size, box=None, focus=(0.5, 0.5)):
    s = Image.open(src).convert("RGB")
    if box:
        s = s.crop(box)
    k = max(size[0] / s.width, size[1] / s.height)
    s = s.resize((round(s.width * k), round(s.height * k)), Image.LANCZOS)
    x = round((s.width - size[0]) * focus[0])
    y = round((s.height - size[1]) * focus[1])
    return s.crop((x, y, x + size[0], y + size[1]))

def save(canvas, name):
    out = root / "output/slides" / name
    canvas.convert("RGB").save(out, quality=92)
    return out


def clean_map():
    """Game screenshot crop used as-is (the user does not want any blur on in-game text)."""
    return root / "assets/ref/map_03_crop.png"


def fit_on_fill(src, size, box=None, margin=40):
    """Subject fitted inside the card over a flat color sampled from its own backdrop, edges feathered."""
    full = Image.open(src).convert("RGB")
    fill = full.getpixel((20, 20))
    s = full.crop(box) if box else full
    k = min(size[0] / s.width, size[1] / s.height)
    fg = s.resize((round(s.width * k), round(s.height * k)), Image.LANCZOS)
    card = Image.new("RGB", size, fill)
    m = Image.new("L", fg.size, 0)
    ImageDraw.Draw(m).rectangle([margin // 2, 0, fg.width - margin // 2, fg.height], fill=255)
    card.paste(fg, ((size[0] - fg.width) // 2, (size[1] - fg.height) // 2), m.filter(ImageFilter.GaussianBlur(margin // 3)))
    return card
