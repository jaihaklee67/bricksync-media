"""Checks every unpublished post in queue/ against the hard rules (runs on pull requests, so the result shows up on the phone).
Rules come from data/facts.json (wording_rules, privacy) plus format checks. Exit code 1 when anything is wrong."""
import datetime
import json
import pathlib
import re
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).parent.parent
facts = json.loads((ROOT / "data" / "facts.json").read_text(encoding="utf-8"))
RULES = facts["wording_rules"]
SIZES = {"feed": (1080, 1350), "story": (1080, 1920)}
errors = []


def check_text(label, text):
    for phrase in RULES["forbidden"]:
        if "(" in phrase or phrase.startswith("범위") or phrase.startswith("상표 안내") or phrase.startswith("제휴·후원"):
            continue
        if phrase in text:
            errors.append(f"{label}: forbidden phrase '{phrase}'")
    for bad in ("AI로 제작", "상표입니다", "제휴하거나"):
        if bad in text:
            errors.append(f"{label}: '{bad}' notice must not be added (user rule)")
    if re.search(r"(?<!\d)01[016789][- ]?\d{3,4}[- ]?\d{4}|\+82", text):
        errors.append(f"{label}: phone number found")
    if re.search(r"국내 유일|세계 최초", text) and "LEGO SPIKE" not in text:
        errors.append(f"{label}: '국내 유일/세계 최초' needs the scope phrase")
    if re.search(r"수료율|재수강률|만족", text) and "자체 집계" not in text:
        errors.append(f"{label}: stat without the '자체 집계' footnote")


def main():
    published = {p.stem for p in (ROOT / "published").glob("*.json")}
    checked = 0
    for pj in sorted((ROOT / "queue").glob("*/post.json")):
        pid = pj.parent.name
        if pid in published:
            continue
        checked += 1
        spec = json.loads(pj.read_text(encoding="utf-8"))
        for key in ("type", "scheduled_at", "images"):
            if key not in spec:
                errors.append(f"{pid}: post.json lacks '{key}'")
        if spec.get("type") not in SIZES:
            errors.append(f"{pid}: type must be feed or story")
            continue
        try:
            when = datetime.datetime.fromisoformat(spec["scheduled_at"])
            if when.tzinfo is None:
                errors.append(f"{pid}: scheduled_at needs a time zone (+09:00)")
        except ValueError:
            errors.append(f"{pid}: scheduled_at is not an ISO date")
        for name in spec["images"]:
            f = pj.parent / name
            if not f.exists():
                errors.append(f"{pid}: missing image {name}")
                continue
            with Image.open(f) as im:
                if im.format != "JPEG" or im.size != SIZES[spec["type"]]:
                    errors.append(f"{pid}/{name}: expected JPEG {SIZES[spec['type']]}, got {im.format} {im.size}")
            if f.stat().st_size > 8 * 1024 * 1024:
                errors.append(f"{pid}/{name}: larger than 8 MB")
        if spec["type"] == "feed":
            cap = pj.parent / spec.get("caption_file", "caption.txt")
            if not cap.exists():
                errors.append(f"{pid}: caption file missing")
            else:
                text = cap.read_text(encoding="utf-8")
                check_text(f"{pid}/caption", text)
                if len(text) > 2200 or len(re.findall(r"#\S+", text)) > 30:
                    errors.append(f"{pid}: caption too long or too many hashtags")
                if "무료 체험수업" not in text:
                    errors.append(f"{pid}: caption has no free-trial call to action")
        for t in spec.get("texts", []):  # on-image text exported by the renderer
            check_text(f"{pid}/image-text", t)
    print(f"checked {checked} unpublished post(s)")
    if errors:
        print("\n".join(" - " + e for e in errors))
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
