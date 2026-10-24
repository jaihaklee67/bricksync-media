"""Visual QA for rendered images.
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

Layer 1 (always): uses the layout report written by render.py (no overlaps, text fits, sizes) plus pixel checks:
  format/size, safe zones on stories, minimum text size, and text contrast measured on the image.
Layer 2 (when the OpenAI key may use the Responses API): a vision model looks at each image for LEGO/brand logos,
  typos, clipped or overlapping text, awkward line breaks and identifiable people.
Usage: py tools/visual_qa.py image1.jpg [image2.jpg ...]   (exit code 1 on failure; layer 2 is reported as SKIPPED when unavailable)"""
import json
import pathlib
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parent))

SIZES = {"slide": (1080, 1350), "story": (1080, 1920)}
MIN_SIZE = {"slide": 24, "story": 28}
SAFE = (250, 1670)  # story top/bottom zones covered by Instagram's UI
VISION_SYSTEM = (
    "당신은 어린이 교육 브랜드(브릭싱크)의 인스타그램 이미지를 검수하는 꼼꼼한 한국어 편집자입니다. "
    "이미지를 보고 아래 JSON 형식으로만 답하세요. 확실하지 않으면 보수적으로 문제로 표시하세요.")
VISION_USER = (
    '{"lego_or_brand_logo_visible": 이미지 안에 LEGO·SPIKE·Fortnite·Epic Games 등 타사 로고나 브랜드 마크가 보이는가(브릭 표면 각인 포함, BrickSync 자사 로고는 제외),'
    ' "text_typos": 맞춤법·오탈자·어색한 표현 목록(없으면 []),'
    ' "text_clipped_or_overlapping": 글자가 잘리거나 다른 글자·그림과 겹치는가,'
    ' "awkward_line_breaks": 줄바꿈이 부자연스러운 곳(한 단어만 남은 줄, 어절 중간 끊김 등) 목록(없으면 []),'
    ' "misaligned": 박스 안에서 정렬이 어긋난 글자나 요소 목록(없으면 []),'
    ' "identifiable_real_person": 실존 인물을 닮았거나 식별 가능한 얼굴이 있는가,'
    ' "forbidden_notices": "AI로 제작", 페이지 번호, 상표 안내 문구, 전화번호, 강사 실명이 보이는가(보이면 내용),'
    ' "notes": 한 줄 총평}')


def contrast_ratio(img, rect):
    x0, y0, x1, y1 = [max(0, int(v)) for v in rect]
    x1, y1 = min(img.width, x1), min(img.height, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return 99
    px = list(img.crop((x0, y0, x1, y1)).convert("L").getdata())
    px.sort()
    lo, hi = px[int(len(px) * 0.08)], px[int(len(px) * 0.92)]

    def lum(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    a, b = sorted((lum(lo), lum(hi)))
    return (b + 0.05) / (a + 0.05)


def check_image(path, vision=True):
    path = pathlib.Path(path)
    problems, notes = [], []
    kind = "story" if path.name.startswith("story") else "slide"
    with Image.open(path) as im:
        im = im.convert("RGB")
        if path.suffix.lower() not in (".jpg", ".jpeg"):
            problems.append("not a JPEG file")
        if im.size != SIZES[kind]:
            problems.append(f"size {im.size}, expected {SIZES[kind]}")
        report = path.with_suffix(".layout.json")
        if not report.exists():
            problems.append("no layout report next to the image (render it with tools/render.py)")
        else:
            data = json.loads(report.read_text(encoding="utf-8"))
            problems += [f"layout: {e}" for e in data.get("errors", [])]
            for t in data.get("texts", []):
                r, size = t["rect"], t.get("size")
                if size and size < MIN_SIZE[kind]:
                    problems.append(f"text '{t['text'][:18]}' is only {size}px (min {MIN_SIZE[kind]})")
                if kind == "story" and (r[1] < SAFE[0] or r[3] > SAFE[1]) and t["label"] != "logo":
                    problems.append(f"story text '{t['text'][:18]}' sits in the top/bottom UI zone {r}")
                if contrast_ratio(im, r) < 2.6:
                    problems.append(f"low contrast for '{t['text'][:18]}' ({contrast_ratio(im, r):.1f}:1)")
    verdict = None
    if vision:
        try:
            import llm
            if llm.available():
                verdict = llm.ask_json_with_image(VISION_SYSTEM, VISION_USER, path)
                if verdict.get("lego_or_brand_logo_visible"):
                    problems.append("vision: third-party logo/brand mark visible")
                for key, label in (("text_typos", "typo"), ("awkward_line_breaks", "line break"), ("misaligned", "alignment"), ("forbidden_notices", "forbidden notice")):
                    v = verdict.get(key)
                    if v:
                        problems.append(f"vision {label}: {v}")
                if verdict.get("text_clipped_or_overlapping"):
                    problems.append("vision: text clipped or overlapping")
                if verdict.get("identifiable_real_person"):
                    problems.append("vision: identifiable real person")
                notes.append("vision: " + str(verdict.get("notes", "")))
            else:
                notes.append("vision: SKIPPED (the OpenAI key has no Responses permission)")
        except Exception as e:  # never let the optional layer hide the programmatic result
            notes.append(f"vision: SKIPPED ({str(e)[:80]})")
    return problems, notes, verdict


if __name__ == "__main__":
    failed = False
    for p in sys.argv[1:]:
        problems, notes, _ = check_image(p)
        print(("FAIL " if problems else "PASS ") + pathlib.Path(p).name)
        for line in problems + notes:
            print("   ", line)
        failed |= bool(problems)
    sys.exit(1 if failed else 0)
