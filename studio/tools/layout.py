"""Small layout engine for the post templates.

Every piece of text is placed through this module so that it is
  * wrapped on spaces with balanced lines (no one-word orphans when avoidable),
  * shrunk until it fits its box, and reported as an error if it cannot fit,
  * vertically centered by a fixed Korean glyph reference (not by whatever glyphs the string happens to contain),
  * registered, so that overlaps (text over text, text over photos/decorations) and boxes that are too small are caught.
verify() raises when something is wrong, and writes a JSON report next to the image for the visual QA step."""
import json
from PIL import ImageDraw

from kidkit import font


class LayoutError(Exception):
    pass


def _inter(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class Layout:
    def __init__(self, canvas, name):
        self.canvas, self.name = canvas, name
        self.d = ImageDraw.Draw(canvas)
        self.texts, self.solids, self.containers, self.errors = [], [], [], []

    # ---- registry ----
    def solid(self, rect, label):
        """Something text must never overlap: photos, decorations, logos."""
        self.solids.append((tuple(rect), label))

    def container(self, rect, label):
        self.containers.append((tuple(rect), label))

    def _text_rect(self, rect, label, text, size=None):
        self.texts.append((tuple(rect), label, text, size))

    # ---- measuring ----
    def ref_metrics(self, f):
        b = f.getbbox("가", anchor="ls")  # (l, top, r, bottom) around the baseline
        return b[1], b[3]

    def width(self, text, f, stroke=0):
        return self.d.textlength(text, font=f) + 2 * stroke

    def wrap_balanced(self, text, f, maxw, stroke=0):
        words = text.split(" ")
        if len(words) == 1:
            return [text]
        w = [self.width(x, f, 0) for x in words]
        space = self.width(" ", f, 0)
        n = len(words)

        def line_w(i, j):  # words[i:j]
            return sum(w[i:j]) + space * (j - i - 1) + 2 * stroke

        # minimum number of lines (greedy), then balance with DP at that line count
        lines_needed, cur = 1, 0
        for i in range(n):
            if line_w(cur, i + 1) > maxw:
                if i == cur:
                    return None  # one word is wider than the box
                lines_needed += 1
                cur = i
        INF = 1e18
        best = [[INF] * (n + 1) for _ in range(lines_needed + 1)]
        prev = [[-1] * (n + 1) for _ in range(lines_needed + 1)]
        best[0][0] = 0
        for k in range(1, lines_needed + 1):
            for j in range(1, n + 1):
                for i in range(j):
                    if best[k - 1][i] >= INF:
                        continue
                    lw = line_w(i, j)
                    if lw > maxw:
                        continue
                    slack = (maxw - lw) / maxw
                    cost = slack ** 2
                    if k == lines_needed and lines_needed > 1 and lw / maxw < 0.38:
                        cost += 5  # short last line
                    if k == lines_needed and j - i == 1 and lines_needed > 1:
                        cost += 3  # single-word last line
                    if best[k - 1][i] + cost < best[k][j]:
                        best[k][j] = best[k - 1][i] + cost
                        prev[k][j] = i
        if best[lines_needed][n] >= INF:
            return None
        out, j = [], n
        for k in range(lines_needed, 0, -1):
            i = prev[k][j]
            out.append(" ".join(words[i:j]))
            j = i
        return out[::-1]

    def fit(self, text, kind, max_size, min_size, box_w, box_h, gap=1.3, stroke=0, max_lines=None):
        for size in range(max_size, min_size - 1, -2):
            f = font(kind, size)
            lines = self.wrap_balanced(text, f, box_w, stroke)
            if not lines or (max_lines and len(lines) > max_lines):
                continue
            top, bottom = self.ref_metrics(f)
            pitch = round(size * gap)
            block_h = (len(lines) - 1) * pitch + (bottom - top) + 2 * stroke
            if block_h <= box_h:
                return f, lines, pitch, block_h, size
        return None

    # ---- drawing ----
    def text_in_box(self, box, text, kind, fill, max_size, min_size=26, align="left", valign="middle",
                    pad=(0, 0, 0, 0), gap=1.3, stroke=0, stroke_fill=None, label=None, max_lines=None):
        x0, y0, x1, y1 = box
        ix0, iy0, ix1, iy1 = x0 + pad[0], y0 + pad[1], x1 - pad[2], y1 - pad[3]
        fitted = self.fit(text, kind, max_size, min_size, ix1 - ix0, iy1 - iy0, gap, stroke, max_lines)
        label = label or text[:24]
        if not fitted:
            self.errors.append(f"[{label}] text does not fit its box {box} even at {min_size}px")
            fitted = self.fit(text, kind, min_size, min_size - 12, 10 ** 6, 10 ** 6, gap, stroke) or (font(kind, min_size), [text], round(min_size * gap), min_size, min_size)
        f, lines, pitch, block_h, size = fitted
        top, bottom = self.ref_metrics(f)
        if valign == "middle":
            ink_top = iy0 + ((iy1 - iy0) - block_h) / 2 + stroke
        else:
            ink_top = iy0 + stroke
        base = ink_top - top  # baseline of the first line
        rects = []
        for i, ln in enumerate(lines):
            lw = self.width(ln, f, 0)
            x = ix0 + stroke if align == "left" else (ix0 + ix1) / 2 - lw / 2
            y = base + i * pitch
            if stroke:
                self.d.text((x, y), ln, font=f, fill=fill, anchor="ls", stroke_width=stroke, stroke_fill=stroke_fill or (255, 255, 255))
            else:
                self.d.text((x, y), ln, font=f, fill=fill, anchor="ls")
            rects.append((x - stroke, y + top - stroke, x + lw + stroke, y + bottom + stroke))
        rect = (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects))
        self._text_rect(rect, label, text, size)
        if rect[0] < x0 - 1 or rect[2] > x1 + 1 or rect[1] < y0 - 1 or rect[3] > y1 + 1:
            self.errors.append(f"[{label}] text {tuple(round(v) for v in rect)} sticks out of its box {box}")
        return rect, size, len(lines)

    def title(self, lines, y, max_size=80, min_size=60, x=60, width=960):
        """Sticker-style title. lines = list of lines, each a list of (text, color) parts. All lines share one size."""
        from kidkit import sticker
        size = max_size
        while size >= min_size:
            f = font("jua", size)
            if all(sum(self.width(t, f, 0) for t, _ in parts) + 20 <= width for parts in lines):
                break
            size -= 2
        f = font("jua", size)
        top, bottom = self.ref_metrics(f)
        pitch = round(size * 1.28)
        yy = y - top + 10
        rects = []
        for parts in lines:
            xx = x + 4
            for seg, seg_color in parts:
                sticker(self.canvas, (xx, yy), seg, f, seg_color, 10, anchor="ls")
                xx += self.d.textlength(seg, font=f)
            rect = (x - 6, yy + top - 10, xx + 10, yy + bottom + 10)
            rects.append(rect)
            self._text_rect(rect, "title", "".join(t for t, _ in parts), size)
            if rect[2] > x + width + 2:
                self.errors.append(f"[title] line wider than {width}px: {parts}")
            yy += pitch
        return (x, y, max(r[2] for r in rects), rects[-1][3])

    def pill(self, x, y, text, color, size=32, kind="jua", padx=28, h=None, text_color=(255, 255, 255), border=(255, 255, 255), max_w=None, label=None):
        """Rounded label; text is centered with the Korean reference metrics. Returns its rect."""
        from kidkit import Image  # noqa
        f = font(kind, size)
        tw = self.width(text, f)
        h = h or round(size * 1.8)
        w = round(tw + 2 * padx)
        if max_w and w > max_w:
            self.errors.append(f"[pill {text[:16]}] width {w} > {max_w}")
        bw = 6
        self.d.rounded_rectangle([x, y, x + w + 2 * bw, y + h + 2 * bw], (h + 2 * bw) // 2, fill=border)
        self.d.rounded_rectangle([x + bw, y + bw, x + bw + w, y + bw + h], h // 2, fill=color)
        top, bottom = self.ref_metrics(f)
        base = y + bw + h / 2 - (top + bottom) / 2
        self.d.text((x + bw + padx, base), text, font=f, fill=text_color, anchor="ls")
        rect = (x, y, x + w + 2 * bw, y + h + 2 * bw)
        self._text_rect((x + bw + padx, base + top, x + bw + padx + tw, base + bottom), label or text[:20], text, size)
        self.container(rect, "pill")
        return rect

    # ---- verification ----
    def verify(self, write_report=None):
        errs = list(self.errors)
        for i, (r1, l1, _, _s) in enumerate(self.texts):
            for r2, l2, _, _s2 in self.texts[i + 1:]:
                if _inter(r1, r2):
                    errs.append(f"text overlap: [{l1}] and [{l2}]")
            for r2, l2 in self.solids:
                if _inter(r1, r2):
                    errs.append(f"text [{l1}] overlaps {l2}")
            if r1[0] < 0 or r1[2] > self.canvas.width or r1[1] < 0 or r1[3] > self.canvas.height:
                errs.append(f"text [{l1}] leaves the canvas")
        if write_report:
            write_report.write_text(json.dumps({
                "name": self.name, "errors": errs,
                "texts": [{"rect": [round(v) for v in r], "label": l, "text": t, "size": sz} for r, l, t, sz in self.texts],
                "solids": [{"rect": [round(v) for v in r], "label": l} for r, l in self.solids]}, ensure_ascii=False, indent=1), encoding="utf-8")
        if errs:
            raise LayoutError(f"{self.name}: " + "; ".join(errs))
