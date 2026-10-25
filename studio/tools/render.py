"""Data-driven renderer: a post spec (JSON) -> slide / story JPEGs, laid out with tools/layout.py.

Spec (see content/posts/*.json):
  {"id": "...", "type": "feed" | "story", "slides": [{"template": "...", ...}]}
Feed templates (1080x1350): hero_compare, steps, levels, info_stats, cta
Story templates (1080x1920): story_teaser, story_promo, story_faq
Every image is verified by Layout.verify(): no text over photos/decorations or other text, text must fit its box.
Usage: py -I tools/render.py content/posts/carousel1.json [out_dir]"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from PIL import Image, ImageDraw
import qrcode
from kidkit import (root, font, tint, flat_bg, card, photo, number_badge, cloud, bunting, bush, sparkle, toy_brick, logo,
                    PINK, BLUE, YELLOW, PURPLE, GREEN, RED, ORANGE, NAVY, INK, GRAY, WHITE)
from layout import Layout, LayoutError
from slidekit import cover_crop, fit_on_fill

COLORS = {"pink": PINK, "blue": BLUE, "yellow": YELLOW, "purple": PURPLE, "green": GREEN, "red": RED, "orange": ORANGE,
          "navy": NAVY, "ink": INK, "gray": GRAY, "white": WHITE}
PALETTES = {"sky": ((170, 218, 252), (222, 242, 255)), "sun": ((255, 238, 140), (255, 248, 200)),
            "rose": ((255, 212, 230), (255, 236, 244)), "mint": ((196, 238, 218), (226, 248, 238))}
BODY = (70, 80, 110)
ASSETS = {
    "build": (root / "output/raw/build_ferris_v1.png", "fit", (60, 0, 1480, 1024)),
    "game": (root / "assets/ref/map_03_crop.png", "cover", (0, 30, 970, 560)),
    "kids": (root / "output/raw/hero_kids_v1.png", "cover", None),
    "kids_wide": (root / "output/raw/hero_kids_v1.png", "cover", (0, 262, 1536, 785)),    # whole faces, with room above and below
    "kids_story": (root / "output/raw/hero_kids_v1.png", "cover", (0, 215, 1536, 915)),
    "gen_gesture": (root / "assets/gen/gesture_hands.png", "cover", (40, 300, 990, 700)),
    "gen_object": (root / "assets/gen/object_detect.png", "cover", (130, 110, 890, 900)),
    # BrickSync app screenshots (user-provided, assets/ref/app_*.webp)
    "app_home": (root / "assets/ref/app_home.webp", "cover", (810, 240, 1457, 602)),
    "app_stage": (root / "assets/ref/app_stage.webp", "cover", (590, 328, 1403, 692)),
    "app_icon_blocks": (root / "assets/ref/app_stage.webp", "cover", (640, 380, 940, 495)),
    "app_word_blocks": (root / "assets/ref/app_stage.webp", "cover", (1025, 345, 1385, 528)),
    "app_gesture_blocks": (root / "assets/ref/app_gesture.webp", "cover", (690, 350, 1140, 500)),
    "app_voice_blocks": (root / "assets/ref/app_voice.webp", "cover", (600, 310, 1000, 450)),
    "app_verse": (root / "assets/ref/app_gesture.webp", "cover", (1456, 140, 2000, 330)),
    # teacher / parent screens and mission screen (crops avoid e-mail addresses and issued codes)
    "teacher_dashboard": (root / "assets/safe/teacher_dashboard.png", "cover", None),
    "teacher_missions": (root / "assets/safe/teacher_missions.png", "cover", None),
    "parent_overview": (root / "assets/safe/parent_overview.png", "cover", None),
    "parent_feedback": (root / "assets/safe/parent_feedback.png", "cover", None),
    "mission_goal": (root / "assets/safe/mission_goal.png", "cover", None),
    # the eight lesson thumbnails shown in the app's unit lists
    "lesson1": (root / "assets/ref/app_units.webp", "cover", (810, 132, 1125, 347)),
    "lesson2": (root / "assets/ref/app_units.webp", "cover", (1141, 132, 1457, 347)),
    "lesson3": (root / "assets/ref/app_units.webp", "cover", (810, 398, 1125, 613)),
    "lesson4": (root / "assets/ref/app_units.webp", "cover", (1141, 398, 1457, 613)),
    "lesson5": (root / "assets/ref/app_units.webp", "cover", (810, 664, 1457, 874)),
    "lesson6": (root / "assets/ref/app_ai_units.webp", "cover", (810, 132, 1125, 480)),
    "lesson7": (root / "assets/ref/app_ai_units.webp", "cover", (1141, 132, 1457, 480)),
    "lesson8": (root / "assets/ref/app_ai_units.webp", "cover", (810, 531, 1457, 874)),
}
CONTACT_URL = "https://edu.bricksync.org/contact"


def col(name):
    return COLORS[name] if isinstance(name, str) else tuple(name)


def parts(spec_line):
    return [(t, col(c)) for t, c in spec_line]


def asset_image(key, size, focus=(0.5, 0.5)):
    path, mode, box = ASSETS[key]
    if mode == "fit":
        return fit_on_fill(path, size, box).convert("RGB")
    return cover_crop(path, size, box, focus)


class Page:
    def __init__(self, name, w, h, palette):
        self.name, self.w, self.h = name, w, h
        self.canvas = flat_bg((w, h), *PALETTES[palette])
        self.L = Layout(self.canvas, name)

    # decorations (registered as solids so text can never overlap them)
    def bunting(self, y0, sag=36, n=11):
        bunting(self.canvas, y0=y0, sag=sag, n=n)
        self.L.solid((0, 0, self.w, y0 + sag + 96), "bunting")

    def cloud(self, cx, cy, s=1.0):
        cloud(self.canvas, cx, cy, s)
        self.L.solid((cx - 118 * s, cy - 80 * s, cx + 122 * s, cy + 56 * s), "cloud")

    def bush(self, x, y, s=1.0):
        bush(self.canvas, x, y, s)
        self.L.solid((x - 130 * s, y - 92 * s, x + 135 * s, y + 85 * s), "bush")

    def logo(self, y, anchor="right", h=64):
        r = logo(self.canvas, y=y, anchor=anchor, h=h)
        self.L.solid(r, "logo")

    def photo(self, img, x, y, label):
        photo(self.canvas, img, x, y)
        self.L.solid((x - 10, y - 10, x + img.width + 10, y + img.height + 10), label)

    def sparkle(self, cx, cy, r=18):
        sparkle(self.canvas, cx, cy, r)
        self.L.solid((cx - r, cy - r, cx + r, cy + r), "sparkle")

    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.L.verify(write_report=path.with_suffix(".layout.json"))
        self.canvas.convert("RGB").save(path, quality=92)
        return path


def capsule(P, x, y, tag, text, tag_color, size=34, h=76, max_w=960):
    """White capsule: colored tag on the left, text on the right, both centered on the capsule's middle line."""
    L, d = P.L, ImageDraw.Draw(P.canvas)
    tf, f = font("jua", size - 4), font("jua", size)
    tag_w = round(L.width(tag, tf)) + 44
    w = tag_w + round(L.width(text, f)) + 56
    if w > max_w:
        L.errors.append(f"[capsule {text[:14]}] width {w} > {max_w}")
    card(P.canvas, x, y, w, h, fill=WHITE, radius=h // 2)
    d.rounded_rectangle([x + 6, y + 6, x + 6 + tag_w, y + h - 6], (h - 12) // 2, fill=tag_color)
    L.text_in_box((x + 6, y + 6, x + 6 + tag_w, y + h - 6), tag, "jua", WHITE, size - 4, size - 4, align="center", label=f"tag {tag}")
    L.text_in_box((x + tag_w + 22, y + 6, x + w - 14, y + h - 6), text, "jua", INK, size, size, label=f"capsule {text[:12]}")
    return w


# ---------------- feed templates ----------------
COMBOS = {  # recognition/blocks on the left, the matching Fortnite scene on the right: both react at the same time
    "combo_blocks": ("blocks_tile", "lesson3", "draw_blocks"),
    "combo_gesture": ("gen_gesture", "lesson6", "contain"),
    "combo_voice": ("voice_draw", "lesson7", "draw"),
    "combo_object": ("gen_object", "lesson8", "cover"),
}


def _blocks_tile(size):
    """Four real icon blocks cut from the app's block palette (play, timer, motor, move) on the palette's own background."""
    w, h = size
    src = Image.open(root / "assets/ref/app_icon_coding.webp").convert("RGB")
    boxes = [(8, 890, 72, 962), (84, 890, 148, 962), (1346, 890, 1410, 962), (1030, 890, 1094, 962)]
    bw, bh = 78, 88
    img = Image.new("RGB", size, (250, 250, 247))
    gx, gy = (w - (2 * bw + 10)) // 2, (h - (2 * bh + 8)) // 2
    for i, b in enumerate(boxes):
        blk = src.crop(b).resize((bw, bh), Image.LANCZOS)
        img.paste(blk, (gx + (i % 2) * (bw + 10), gy + (i // 2) * (bh + 8)))
    return img


def _voice_tile(size):
    w, h = size
    img = Image.new("RGB", size, tint(YELLOW, 0.3))
    d = ImageDraw.Draw(img)
    bw, bh = w - 24, int(h * 0.50)
    d.rounded_rectangle([12, 10, 12 + bw, 10 + bh], 18, fill=WHITE, outline=BLUE, width=3)
    d.polygon([(w // 2 - 10, 10 + bh), (w // 2 + 10, 10 + bh), (w // 2, 10 + bh + 14)], fill=WHITE, outline=BLUE)
    d.line([(w // 2 - 8, 10 + bh), (w // 2 + 8, 10 + bh)], fill=WHITE, width=4)
    f = font("jua", 21)
    for i, line in enumerate(("앞으로 3바퀴", "돌아!")):
        d.text((w // 2, 10 + bh / 2 + (i - 0.5) * 27), line, font=f, fill=NAVY, anchor="mm")
    cx, cy = w // 2, int(h * 0.80)
    d.rounded_rectangle([cx - 11, cy - 22, cx + 11, cy + 8], 11, fill=PINK)
    d.arc([cx - 19, cy - 12, cx + 19, cy + 22], 20, 160, fill=PINK, width=4)
    d.line([(cx, cy + 22), (cx, cy + 30)], fill=PINK, width=4)
    d.line([(cx - 12, cy + 30), (cx + 12, cy + 30)], fill=PINK, width=4)
    return img


def combo_art(kind, size):
    w, h = size
    left_key, right_key, mode = COMBOS[kind]
    lw, rw = int(w * 0.50), int(w * 0.44)
    if mode == "draw":
        left = _voice_tile((lw, h))
    elif mode == "draw_blocks":
        left = _blocks_tile((lw, h))
    elif mode == "fill":
        left = asset_image(left_key, (lw, h))
    elif mode == "contain":
        src = asset_image(left_key, (lw * 3, int(h * 1.6)))  # crop first, then fit whole inside the tile
        path, _, box = ASSETS[left_key]
        crop = Image.open(path).convert("RGB").crop(box)
        k = min(lw / crop.width, h / crop.height)
        crop = crop.resize((round(crop.width * k), round(crop.height * k)), Image.LANCZOS)
        left = Image.new("RGB", (lw, h), crop.getpixel((2, 2)))
        left.paste(crop, ((lw - crop.width) // 2, (h - crop.height) // 2))
    else:
        left = asset_image(left_key, (lw, h))
    right = asset_image(right_key, (rw, h))
    img = Image.new("RGB", size, WHITE)
    img.paste(left, (0, 0))
    img.paste(right, (w - rw, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = w // 2, h // 2, 21
    d.ellipse([cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4], fill=WHITE)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ORANGE)
    d.line([(cx - 11, cy - 6), (cx + 7, cy - 6)], fill=WHITE, width=3)
    d.polygon([(cx + 7, cy - 12), (cx + 13, cy - 6), (cx + 7, cy)], fill=WHITE)
    d.line([(cx + 11, cy + 7), (cx - 7, cy + 7)], fill=WHITE, width=3)
    d.polygon([(cx - 7, cy + 1), (cx - 13, cy + 7), (cx - 7, cy + 13)], fill=WHITE)
    return img


def art_image(kind, size):
    w, h = size
    if kind in COMBOS:
        return combo_art(kind, size)
    if kind in ASSETS:
        return asset_image(kind, size)
    img = Image.new("RGB", size, tint(YELLOW, 0.3) if kind == "blocks" else tint(BLUE, 0.22))
    dd = ImageDraw.Draw(img)
    if kind == "blocks":
        for j, (bc, g) in enumerate(((YELLOW, "play"), (YELLOW, "5"), (GREEN, "3"))):
            bs = int(h * 0.62)
            bx = int((w - 3 * bs - 2 * 24) / 2) + j * (bs + 24)
            by = int(h * 0.22)
            dd.rounded_rectangle([bx, by, bx + bs, by + bs], 22, fill=bc)
            for sx in (0.28, 0.72):
                dd.ellipse([bx + bs * sx - 11, by - 10, bx + bs * sx + 11, by + 8], fill=bc)
            if g == "play":
                dd.polygon([(bx + bs * .36, by + bs * .26), (bx + bs * .36, by + bs * .74), (bx + bs * .76, by + bs * .5)], fill=WHITE)
            else:
                cx, cy, r = bx + bs / 2, by + bs / 2, bs * 0.29
                dd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
                dd.text((cx, cy), g, font=font("black", int(bs * 0.38)), fill=INK, anchor="mm")
    else:  # browser
        dd.rounded_rectangle([54, 18, w - 54, h - 18], 18, fill=WHITE, outline=BLUE, width=4)
        dd.rectangle([56, 20, w - 56, 46], fill=tint(BLUE, 0.35))
        for k in range(3):
            dd.ellipse([72 + k * 24, 27, 86 + k * 24, 39], fill=BLUE)
        mx, my = w // 2, int(h * 0.62)
        dd.ellipse([mx - 24, my - 24, mx + 24, my + 24], fill=BLUE)
        for r in (40, 58):
            dd.arc([mx - r, my - r, mx + r, my + r], 200, 340, fill=BLUE, width=5)
        for bx, bc in ((82, PINK), (w - 138, GREEN)):
            dd.rounded_rectangle([bx, my - 24, bx + 56, my + 26], 10, fill=bc)
    return img


def title_block(P, spec, y=140, max_size=80, min_size=62):
    lines = [parts(l) for l in spec["title"]]
    return P.L.title(lines, y, max_size=max_size, min_size=min_size)


def tpl_hero_compare(P, s):
    L = P.L
    P.bunting(-14)
    P.cloud(950, 130, 0.7)
    t = title_block(P, s, 140, 78, 62)
    ph = 290
    rows = [(s["top"], 360, 446), (s["bottom"], 850, 934)]
    for (item, py, img_y) in rows:
        rect = P.L.pill(60, py - 4, item["label"], col(item["color"]), size=32, padx=26, h=58, max_w=960)
        img = asset_image(item["art"], (940, ph))
        P.photo(img, 70, img_y, "photo " + item["art"])
    cy = 792
    P.canvas_ellipse = ImageDraw.Draw(P.canvas)
    P.canvas_ellipse.ellipse([540 - 50, cy - 50, 540 + 50, cy + 50], fill=WHITE)
    P.canvas_ellipse.ellipse([540 - 42, cy - 42, 540 + 42, cy + 42], fill=YELLOW)
    L.text_in_box((540 - 42, cy - 22, 540 + 42, cy + 22), "SYNC", "black", NAVY, 28, 20, align="center", label="sync")
    P.bush(90, 1300, 0.6)
    P.logo(1252)


def tpl_steps(P, s):
    L = P.L
    P.bunting(-14)
    P.cloud(955, 150, 0.65)
    title_block(P, s, 140, 78, 62)
    if s.get("tagline"):
        P.L.pill(60, 346, s["tagline"], NAVY, size=28, padx=22, h=52, max_w=960)
    cw, ch, gap = 468, 392, 22
    for i, it in enumerate(s["items"]):
        x = 60 + (i % 2) * (cw + gap)
        y = 430 + (i // 2) * (ch + gap)
        card(P.canvas, x, y, cw, ch, fill=(226, 243, 255), border=WHITE, bw=8)
        aw, ah = cw - 36, 196
        img = art_image(it["art"], (aw, ah))
        m = Image.new("L", img.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, aw - 1, ah - 1], 24, fill=255)
        P.canvas.paste(img, (x + 18, y + 18), m)
        L.solid((x + 18, y + 18, x + 18 + aw, y + 18 + ah), "art")
        cy = y + 18 + ah + 44
        number_badge(P.canvas, x + 52, cy, i + 1, color=ORANGE, r=30)
        L.text_in_box((x + 100, cy - 32, x + cw - 24, cy + 32), it["title"], "jua", NAVY, 34, 28, label=f"step{i+1} title")
        L.text_in_box((x + 30, y + 18 + ah + 80, x + cw - 30, y + ch - 14), it["desc"], "do", BODY, 31, 27, valign="top", label=f"step{i+1} desc")
    P.bush(90, 1304, 0.6)
    P.logo(1252)


def tpl_levels(P, s):
    L = P.L
    P.bunting(-14)
    P.cloud(965, 190, 0.55)
    title_block(P, s, 140, 78, 62)
    toy_brick(P.canvas, 800, 118, 110, 56, PINK, 2, -8)
    toy_brick(P.canvas, 852, 64, 90, 50, YELLOW, 2, 8)
    L.solid((760, 20, 960, 190), "bricks")
    n, gap = len(s["items"]), 18
    rh = min(200, (1140 - 366 - (n - 1) * gap) // n)
    y = 366
    for it in s["items"]:
        c = col(it["color"])
        card(P.canvas, 60, y, 960, rh, fill=WHITE, border=c, bw=8, radius=44)
        d = ImageDraw.Draw(P.canvas)
        d.rounded_rectangle([60, y, 310, y + rh - 1], 44, fill=c)
        d.rectangle([250, y, 310, y + rh - 1], fill=c)
        dark = tuple(int(v * 0.65) for v in c)
        mid = y + rh / 2
        L.text_in_box((68, mid - 66, 302, mid + 2), it["age"], "black", WHITE, 50, 34, align="center", stroke=4, stroke_fill=dark, label="age " + it["age"])
        L.text_in_box((68, mid + 6, 302, mid + 58), it["name"], "jua", WHITE, 34, 26, align="center", label="level " + it["name"])
        L.text_in_box((344, y + 14, 1000, y + rh - 14), it["desc"], "jua", INK, 34, 28, label="desc " + it["name"])
        y += rh + gap
    if s.get("footer"):
        L.pill(60, y + 12, s["footer"], NAVY, size=28, padx=24, h=56, max_w=700)
    P.bush(90, 1306, 0.55)
    P.logo(1252)


def tpl_info_stats(P, s):
    L = P.L
    P.bunting(-14)
    P.cloud(955, 160, 0.6)
    title_block(P, s, 140, 78, 62)
    cw, chh = 468, 190
    for i, it in enumerate(s["chips"]):
        x = 60 + (i % 2) * (cw + 24)
        y = 350 + (i // 2) * (chh + 22)
        c = col(it["color"])
        card(P.canvas, x, y, cw, chh, fill=WHITE, border=c, bw=7, radius=40)
        toy_brick(P.canvas, x + 30, y + 44, 64, 36, c, 2, 0)
        L.solid((x + 20, y + 24, x + 108, y + 92), "brick icon")
        L.text_in_box((x + 118, y + 24, x + cw - 24, y + 92), it["title"], "jua", NAVY, 35, 28, label="chip " + it["title"])
        L.text_in_box((x + 28, y + 100, x + cw - 28, y + chh - 18), it["desc"], "do", BODY, 31, 27, valign="top", label="chipdesc " + it["title"])
    L.pill(60, 790, s["pill"], NAVY, size=32, padx=30, h=64, max_w=960)
    card(P.canvas, 60, 890, 960, 340, fill=WHITE, border=WHITE, radius=44)
    L.text_in_box((100, 908, 980, 956), s["stats_title"], "jua", GRAY, 32, 26, label="stats title")
    d = ImageDraw.Draw(P.canvas)
    for i, it in enumerate(s["stats"]):
        c = col(it["color"])
        cx, cy, r = 60 + 160 + i * 320, 1080, 100
        d.ellipse([cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10], fill=tint(c, 0.2))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
        dark = tuple(int(v * 0.7) for v in c)
        L.text_in_box((cx - 74, cy - 52, cx + 74, cy + 6), it["num"], "black", WHITE, 54, 36, align="center", stroke=3, stroke_fill=dark, label="stat " + it["num"])
        L.text_in_box((cx - 74, cy + 14, cx + 74, cy + 62), it["label"], "jua", WHITE, 30, 24, align="center", label="statlabel " + it["label"])
    L.text_in_box((100, 1180, 980, 1218), s["footnote"], "do", GRAY, 26, 24, label="footnote")
    P.bush(90, 1308, 0.55)
    P.logo(1252)


def apply_box(P, x, y, w, h, s):
    L = P.L
    card(P.canvas, x, y, w, h, fill=WHITE, border=WHITE, radius=44)
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(s.get("qr_url", CONTACT_URL))
    qr.make(fit=True)
    qs = 220
    q = qr.make_image(fill_color=INK, back_color=WHITE).convert("RGB").resize((qs, qs), Image.NEAREST)
    P.canvas.paste(q, (x + 36, y + (h - qs) // 2))
    L.solid((x + 36, y + (h - qs) // 2, x + 36 + qs, y + (h - qs) // 2 + qs), "qr")
    tx, right = x + 36 + qs + 44, x + w - 30
    L.text_in_box((tx, y + 24, right, y + 78), s["apply_title"], "jua", NAVY, 40, 32, label="apply title")
    d = ImageDraw.Draw(P.canvas)
    ry = y + 96
    pitch = (h - 96 - 20) // len(s["apply_rows"])
    for t, desc, c in s["apply_rows"]:
        c = col(c)
        d.ellipse([tx, ry + 14, tx + 20, ry + 34], fill=c)
        L.text_in_box((tx + 34, ry, right, ry + 46), t, "jua", INK, 34, 28, label="row " + t)
        L.text_in_box((tx + 34, ry + 48, right, ry + 48 + 44), desc, "do", BODY, 29, 25, valign="top", max_lines=1, label="rowdesc " + t)
        ry += pitch


def tpl_cta(P, s):
    L = P.L
    P.bunting(-14, n=11)
    img = asset_image("kids_wide", (940, 320))
    P.photo(img, 70, 96, "hero")
    L.title([parts(l) for l in s["title"]], 456, max_size=74, min_size=62)
    y = 640
    capsule(P, 60, y, s["capsules"][0][0], s["capsules"][0][1], BLUE, size=32, h=72)
    y += 88
    w1 = capsule(P, 60, y, s["capsules"][1][0], s["capsules"][1][1], BLUE, size=32, h=72)
    capsule(P, 60 + w1 + 18, y, s["capsules"][2][0], s["capsules"][2][1], BLUE, size=32, h=72)
    apply_box(P, 60, 818, 960, 402, s)
    P.logo(1262)


# ---------------- story templates ----------------
def story_frame(P, title_lines=None):
    P.bunting(10, sag=34, n=11)
    P.cloud(140, 238, 0.55)
    P.cloud(950, 232, 0.5)
    P.logo(146, anchor="center")
    P.bush(80, 1850, 0.8)
    P.bush(1000, 1860, 0.7)


def tpl_story_teaser(P, s):
    L = P.L
    story_frame(P)
    L.title([parts(l) for l in s["title"]], 330, max_size=84, min_size=66)
    ph = 340
    L.pill(60, 560, s["top"]["label"], col(s["top"]["color"]), size=34, h=60, max_w=960)
    P.photo(asset_image(s["top"]["art"], (940, ph)), 70, 650, "photo top")
    cy = 1050
    d = ImageDraw.Draw(P.canvas)
    d.ellipse([540 - 50, cy - 50, 540 + 50, cy + 50], fill=WHITE)
    d.ellipse([540 - 42, cy - 42, 540 + 42, cy + 42], fill=YELLOW)
    L.text_in_box((540 - 42, cy - 22, 540 + 42, cy + 22), "SYNC", "black", NAVY, 28, 20, align="center", label="sync")
    L.pill(60, 1112, s["bottom"]["label"], col(s["bottom"]["color"]), size=34, h=60, max_w=960)
    P.photo(asset_image(s["bottom"]["art"], (940, ph)), 70, 1202, "photo bottom")
    L.pill(60, 1580, s["cta"], NAVY, size=36, padx=34, h=70, max_w=960)


def tpl_story_promo(P, s):
    L = P.L
    story_frame(P)
    P.photo(asset_image("kids_story", (940, 430)), 70, 330, "hero")
    L.title([parts(l) for l in s["title"]], 830, max_size=88, min_size=70)
    y = 1070
    for tag, text in s["capsules"]:
        capsule(P, 60, y, tag, text, BLUE, size=36, h=84)
        y += 100
    card(P.canvas, 60, 1390, 960, 200, fill=NAVY, radius=44)
    L.text_in_box((100, 1410, 980, 1490), s["cta_line1"], "jua", WHITE, 40, 32, label="cta1")
    L.text_in_box((100, 1494, 980, 1574), s["cta_line2"], "jua", YELLOW, 42, 32, label="cta2")


def tpl_story_faq(P, s):
    L = P.L
    story_frame(P)
    L.title([parts([("자주 묻는 질문", "green")])], 370, max_size=82, min_size=66)
    card(P.canvas, 60, 530, 960, 400, fill=WHITE, border=PINK, bw=10, radius=48)
    number_badge(P.canvas, 150, 610, "Q", color=PINK, r=44)
    L.text_in_box((100, 676, 980, 900), s["q"], "jua", NAVY, 58, 40, label="question")
    card(P.canvas, 60, 990, 960, 620, fill=WHITE, border=GREEN, bw=10, radius=48)
    number_badge(P.canvas, 150, 1070, "A", color=GREEN, r=44)
    L.text_in_box((100, 1136, 980, 1220), s["a_head"], "black", GREEN, 66, 48, label="answer head")
    L.text_in_box((100, 1240, 980, 1580), s["a_body"], "do", (50, 60, 90), 50, 34, valign="top", label="answer body")


def tpl_story_feed_cover(P, s):
    """Story teaser: the feed post's own first slide plus a pointer to the post."""
    L = P.L
    story_frame(P)
    img = Image.open(s["image"]).convert("RGB").resize((800, 1000), Image.LANCZOS)
    P.photo(img, 140, 320, "feed cover")
    f = font("jua", 36)
    w = round(L.width(s["cta"], f)) + 2 * 34 + 12
    L.pill((1080 - w) // 2, 1390, s["cta"], NAVY, size=36, padx=34, h=70, max_w=960)


def tpl_story_card(P, s):
    """Story card for one item of the feed post (steps / levels / chips), same wording as the feed."""
    L = P.L
    story_frame(P)
    L.title([parts(l) for l in s["title"]], 330, max_size=78, min_size=62)
    P.photo(art_image(s["art"], (940, 460)), 70, 630, "art")
    c = col(s["color"])
    card(P.canvas, 60, 1150, 960, 400, fill=WHITE, border=c, bw=10, radius=48)
    L.text_in_box((100, 1186, 980, 1286), s["item_title"], "jua", NAVY, 64, 42, label="card title")
    L.text_in_box((100, 1300, 980, 1510), s["item_desc"], "do", (50, 60, 90), 54, 36, valign="top", label="card desc")


def tpl_screen(P, s):
    """One app screen (cropped) with up to three explanatory rows. The picture height follows the crop's aspect ratio."""
    L = P.L
    P.bunting(-14)
    P.cloud(955, 150, 0.6)
    title_block(P, s, 140, 78, 62)
    with Image.open(ASSETS[s["art"]][0]) as _im:
        iw, ih = _im.size
    h = max(300, min(500, round(940 * ih / iw)))
    img = asset_image(s["art"], (940, h))
    P.photo(img, 70, 350, "screen")
    y0 = 350 + h + 44
    rows = s["bullets"]
    ch = 36 + len(rows) * 96
    card(P.canvas, 60, y0, 960, ch, fill=WHITE, border=WHITE, radius=44)
    d = ImageDraw.Draw(P.canvas)
    for i, b in enumerate(rows):
        c = col(b.get("color", ["pink", "blue", "green"][i % 3]))
        ry = y0 + 24 + i * 96
        d.ellipse([96, ry + 14, 120, ry + 38], fill=c)
        L.text_in_box((140, ry, 990, ry + 48), b["title"], "jua", NAVY, 36, 28, label="bullet " + b["title"])
        L.text_in_box((140, ry + 48, 990, ry + 88), b["desc"], "do", BODY, 30, 26, valign="top", max_lines=1, label="bulletdesc " + b["title"])
    P.bush(90, 1306, 0.55)
    P.logo(1252)


TEMPLATES = {"screen": tpl_screen, "hero_compare": tpl_hero_compare, "steps": tpl_steps, "levels": tpl_levels, "info_stats": tpl_info_stats,
             "cta": tpl_cta, "story_teaser": tpl_story_teaser, "story_promo": tpl_story_promo, "story_faq": tpl_story_faq,
             "story_feed_cover": tpl_story_feed_cover, "story_card": tpl_story_card}


def render(spec_path, out_dir=None):
    spec = json.loads(pathlib.Path(spec_path).read_text(encoding="utf-8"))
    out_dir = pathlib.Path(out_dir) if out_dir else root / "output" / "rendered" / spec["id"]
    size = (1080, 1350) if spec["type"] == "feed" else (1080, 1920)
    outs = []
    for i, s in enumerate(spec["slides"], 1):
        name = f"{spec['id']}-{i}"
        P = Page(name, *size, s.get("palette", "sky"))
        TEMPLATES[s["template"]](P, s)
        outs.append(P.save(out_dir / f"{'slide' if spec['type'] == 'feed' else 'story'}-{i}.jpg"))
    return outs


if __name__ == "__main__":
    try:
        for p in render(*sys.argv[1:3]):
            print(p)
    except LayoutError as e:
        print("LAYOUT ERROR:", e)
        sys.exit(1)
