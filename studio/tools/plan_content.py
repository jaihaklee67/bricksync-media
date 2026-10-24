"""Plans posts and builds draft packages.

Rule (user decision 2026-10-24): every story is derived from the feed post that came before it, so approving the feed approves its
stories. A feed post and the stories that follow it (until the next feed day) are one bundle, and one pull request per bundle.

  py tools/plan_content.py --days 7 [--from 2026-10-25]   # plan, render, QA -> output/drafts/<id>/ (nothing is pushed)
  py tools/plan_content.py --days 7 --dry-run             # only print the plan

Feed topics come from content/topics/*.json (the LLM proposes new ones when the OpenAI key may use the Responses API).
Derived stories: a cover story (the feed's first slide), one card per feed item, and a free-trial story from the feed's call to action."""
import datetime
import json
import os
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import render
import visual_qa

ROOT = pathlib.Path(__file__).parent.parent
REPO = pathlib.Path(os.environ.get("MEDIA_REPO", r"C:\Users\PC\Documents\GitHub\bricksync-media"))
KST = datetime.timezone(datetime.timedelta(hours=9))
STATE = ROOT / "data" / "planner_state.json"
DRAFTS = ROOT / "output" / "drafts"
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
STORY_STATIC = json.loads((ROOT / "config" / "story_static.json").read_text(encoding="utf-8")) if (ROOT / "config" / "story_static.json").exists() else []


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"used": ["feed:carousel1"]}


def save_state(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def schedule():
    cfg = json.loads((REPO / "config" / "schedule.json").read_text(encoding="utf-8"))
    return cfg


def slot_list(cfg, kind, start, days):
    out = []
    for d in range(days + 1):
        day = (start + datetime.timedelta(days=d)).date()
        for s in cfg[kind]:
            if s["weekday"] != WEEKDAYS[day.weekday()]:
                continue
            assert cfg["window"]["start"] <= s["time"] <= cfg["window"]["end"], f"{s['time']} is outside the allowed window"
            h, m = map(int, s["time"].split(":"))
            out.append(datetime.datetime(day.year, day.month, day.day, h, m, tzinfo=KST))
    return sorted(out)


def taken_slots():
    seen = set()
    sources = list((REPO / "queue").glob("*/post.json")) + list(DRAFTS.glob("*/post.json"))
    for p in sources:
        spec = json.loads(p.read_text(encoding="utf-8"))
        seen.add((spec["scheduled_at"], spec["type"]))
    for p in (REPO / "published").glob("*.json"):
        spec = json.loads(p.read_text(encoding="utf-8"))
        if spec.get("scheduled_at"):
            seen.add((spec["scheduled_at"], spec.get("type", "")))
    return seen


def feed_candidates(state):
    out = []
    for p in sorted((ROOT / "content/topics").glob("*.json")):
        spec = json.loads(p.read_text(encoding="utf-8"))
        key = f"feed:{spec['id']}"
        if key not in state["used"]:
            out.append((key, spec))
    return out


def feed_items(spec):
    """Items of the feed's first content slide as (title, desc, art, color)."""
    colors = ["pink", "blue", "orange", "purple"]
    for sl in spec["slides"]:
        if sl["template"] == "steps":
            return [(it["title"], it["desc"], it["art"], colors[i % 4]) for i, it in enumerate(sl["items"])]
        if sl["template"] == "levels":
            return [(f"{it['age']} {it['name']}", it["desc"], "build", it["color"]) for it in sl["items"]]
        if sl["template"] == "info_stats":
            return [(c["title"], c["desc"], "build", c["color"]) for c in sl["chips"]]
    return []


def derived_stories(feed_spec, feed_dir, n):
    """n story specs (one slide each) derived from the feed, in posting order."""
    cover_title = feed_spec["slides"][0]["title"]
    cta = next((s for s in feed_spec["slides"] if s["template"] == "cta"), None)
    items = feed_items(feed_spec)
    palettes = ["sky", "sun", "mint", "rose"]
    out = [("cover", {"template": "story_feed_cover", "palette": "sky", "image": str(feed_dir / "slide-1.jpg"), "cta": "새 게시물에서 자세히 보기"})]
    cards = [("card%d" % (i + 1), {"template": "story_card", "palette": palettes[(i + 1) % 4], "title": cover_title, "art": art, "color": color,
                                   "item_title": t, "item_desc": d}) for i, (t, d, art, color) in enumerate(items)]
    promo = None
    if cta:
        promo = ("promo", {"template": "story_promo", "palette": "sun", "title": [[["무료 체험수업,", "navy"]], [["신청받고 있어요", "pink"]]],
                           "capsules": [["대상", "정식 등록된 교육기관/학교"], ["규모", "1클래스 최대 30명"], ["시간", "최대 120분"]],
                           "cta_line1": "프로필 링크의 문의에", "cta_line2": "'무료 체험수업'이라고 남겨주세요"})
    seq = [out[0]]
    ci = 0
    while len(seq) < n:
        if len(seq) == 2 and promo and n >= 3:
            seq.append(promo)
            promo = None
        elif ci < len(cards):
            seq.append(cards[ci])
            ci += 1
        elif promo:
            seq.append(promo)
            promo = None
        else:
            break
    return seq[:n]


def build_package(pid, when, kind, slides, caption=None, bundle=None, derived_from=None):
    spec = {"id": pid, "type": "feed" if kind == "feed" else "story", "slides": slides}
    tmp = ROOT / "output" / "_tmp_spec.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    out_dir = DRAFTS / pid
    if out_dir.exists():
        shutil.rmtree(out_dir)
    images = render.render(tmp, out_dir)
    texts, qa_notes = [], []
    for img in images:
        problems, notes, _ = visual_qa.check_image(img)
        if problems:
            raise RuntimeError(f"{pid}: visual QA failed for {img.name}: {problems}")
        qa_notes += notes
        texts += [t["text"] for t in json.loads(img.with_suffix(".layout.json").read_text(encoding="utf-8"))["texts"]]
    for f in out_dir.glob("*.layout.json"):
        f.unlink()
    post = {"id": pid, "type": spec["type"], "scheduled_at": when.isoformat(), "images": [p.name for p in images], "texts": texts,
            "qa": "programmatic PASS; " + ("; ".join(sorted(set(qa_notes))) or "vision n/a")}
    if bundle:
        post["bundle"] = bundle
    if derived_from:
        post["derived_from"] = derived_from
    if caption:
        (out_dir / "caption.txt").write_text(caption.strip() + "\n", encoding="utf-8")
        post["caption_file"] = "caption.txt"
    (out_dir / "post.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    return out_dir


def check_rules(text, facts):
    for phrase in facts["wording_rules"]["forbidden"]:
        if "(" in phrase or phrase.startswith(("범위", "상표 안내", "제휴·후원")):
            continue
        if phrase in text:
            raise ValueError(f"forbidden phrase {phrase}")
    for bad in ("AI로 제작", "상표입니다", "제휴하거나"):
        if bad in text:
            raise ValueError(f"notice '{bad}' is not allowed")
    if re.search(r"(?<!\d)01[016789][- ]?\d{3,4}[- ]?\d{4}|\+82", text):
        raise ValueError("phone number")


def llm_new_topic(state):
    """Asks the LLM for one new feed topic (render spec); None when the LLM is unavailable or the result fails validation."""
    try:
        import llm
        if not llm.available():
            return None
    except Exception:
        return None
    facts = json.loads((ROOT / "data/facts.json").read_text(encoding="utf-8"))
    ok = [f for f in facts["facts"] if f["status"] in ("verified_public", "verified_user")]
    system = ("당신은 어린이 교육 브랜드 브릭싱크의 인스타그램 기획자입니다. 반드시 제공된 '검증된 사실' 안에서만 말하고, 새로운 수치나 주장을 만들지 마세요. "
              "금지 표현: " + ", ".join(facts["wording_rules"]["forbidden"]) + ". 이미지·캡션에 AI 제작 안내, 페이지 번호, 상표 안내, 전화번호, 강사 이름을 넣지 마세요. "
              "문장은 짧고 다정한 존댓말(~해요)로 쓰고, 슬라이드 글은 짧게(제목 8자 안팎, 설명 25자 안팎) 쓰세요. 가운뎃점과 물결표 대신 '/'와 '~'를 쓰세요.")
    user = json.dumps({"task": "새 피드 카루셀 주제 1개를 JSON으로만 답하세요.", "already_used": state["used"],
                       "facts": [{"id": f["id"], "text": f["text"]} for f in ok],
                       "schema": {"id": "topic-영문소문자-하이픈", "title": "주제 이름", "type": "feed", "fact_ids": ["사용한 사실 id"], "caption": "캡션 전체(무료 체험수업 안내와 해시태그 포함)",
                                  "slides": "steps 한 장(items 4개: title, desc, art=build|blocks|browser|game) + cta 한 장"},
                       "example": json.loads((ROOT / "content/topics/topic-ai-lessons.json").read_text(encoding="utf-8"))}, ensure_ascii=False)
    for _ in range(3):
        try:
            spec = llm.ask_json(system, user)
            if not spec.get("fact_ids") or not set(spec["fact_ids"]) <= {f["id"] for f in ok}:
                raise ValueError("fact_ids missing or unknown")
            check_rules(spec["caption"] + json.dumps(spec["slides"], ensure_ascii=False), facts)
            return spec
        except Exception as e:
            user = user[:-1] + ', "previous_error": ' + json.dumps(str(e), ensure_ascii=False) + "}"
    return None


def main():
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 7
    dry = "--dry-run" in sys.argv
    start = datetime.datetime.now(KST)
    if "--from" in sys.argv:
        y, m, d = map(int, sys.argv[sys.argv.index("--from") + 1].split("-"))
        start = datetime.datetime(y, m, d, tzinfo=KST)
    cfg = schedule()
    state, taken = load_state(), taken_slots()
    now = datetime.datetime.now(KST)
    feeds = [w for w in slot_list(cfg, "feed", start, days + 7) if w > now + datetime.timedelta(hours=8)]
    stories = slot_list(cfg, "story", start, days + 7)
    pool = feed_candidates(state)
    horizon = start + datetime.timedelta(days=days)
    plan = []  # (feed_when, feed_spec|None, [(story_when)...])
    all_feed_slots = slot_list(cfg, "feed", start - datetime.timedelta(days=7), days + 14)
    for fw in [f for f in feeds if f <= horizon]:
        if (fw.isoformat(), "feed") in taken:
            continue
        if not pool:
            spec = llm_new_topic(state)
            if spec:
                (ROOT / "content/topics" / f"{spec['id']}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
                pool.append((f"feed:{spec['id']}", spec))
        if not pool:
            plan.append((fw, None, []))
            continue
        key, spec = pool.pop(0)
        nxt = min([f for f in all_feed_slots if f > fw], default=fw + datetime.timedelta(days=3))
        mine = [s for s in stories if fw <= s < nxt and (s.isoformat(), "story") not in taken and s > now + datetime.timedelta(hours=8)]
        plan.append((fw, (key, spec), mine))
    # stories of feeds that were already approved (merged) but whose derived stories are not scheduled yet
    existing = []
    for pj in sorted((REPO / "queue").glob("*/post.json")):
        fp = json.loads(pj.read_text(encoding="utf-8"))
        if fp["type"] != "feed":
            continue
        fw = datetime.datetime.fromisoformat(fp["scheduled_at"])
        slug = pj.parent.name.split("_feed_", 1)[1]
        topic = next((t for t in (ROOT / "content/topics").glob("*.json") if json.loads(t.read_text(encoding="utf-8"))["id"].lower().replace("_", "-").startswith(slug[:30])), None)
        nxt = min([f for f in all_feed_slots if f > fw], default=fw + datetime.timedelta(days=3))
        mine = [x for x in stories if fw <= x < nxt and (x.isoformat(), "story") not in taken and x > now + datetime.timedelta(hours=8)]
        if topic and mine:
            existing.append((pj.parent.name, slug, json.loads(topic.read_text(encoding="utf-8")), mine))
    print(f"{'시각(KST)':<18} 내용")
    for feed_id, slug, spec, mine in existing:
        for x in mine:
            print(f"{x:%m-%d %a %H:%M}    story (이미 승인된 피드 {feed_id}에서 파생, 자동 승인)")
    for fw, item, sts in plan:
        print(f"{fw:%m-%d %a %H:%M}    FEED  {item[0] if item else '(주제 없음: 주제를 더 만들어야 해요)'}")
        for s in sts:
            print(f"{s:%m-%d %a %H:%M}    story (이 피드에서 파생)")
    if dry:
        return
    made = []
    for feed_id, slug, spec, mine in existing:
        kids = derived_stories(spec, REPO / "queue" / feed_id, len(mine))
        feed_texts = set(json.loads((REPO / "queue" / feed_id / "post.json").read_text(encoding="utf-8")).get("texts", []))
        for when, (kind, slide) in zip(mine, kids):
            sid = f"{when:%Y-%m-%d_%H%M}_story_{slug}-{kind}"
            build_package(sid, when, "story", [slide], bundle=feed_id, derived_from=feed_id)
            pj = DRAFTS / sid / "post.json"
            post = json.loads(pj.read_text(encoding="utf-8"))
            post["auto_approved"] = True  # its feed was approved by merge
            pj.write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
            made.append(sid)
            print("auto-approved story ready:", sid)
    for fw, item, sts in plan:
        if not item:
            continue
        key, spec = item
        slug = re.sub("[^a-z0-9-]", "", spec["id"].lower())[:30]
        feed_id = f"{fw:%Y-%m-%d_%H%M}_feed_{slug}"
        try:
            feed_dir = build_package(feed_id, fw, "feed", spec["slides"], spec.get("caption"), bundle=feed_id)
            kids = derived_stories(spec, feed_dir, len(sts))
            feed_texts = json.loads((feed_dir / "post.json").read_text(encoding="utf-8"))["texts"]
            joined = " ".join(feed_texts)
            for when, (kind, slide) in zip(sts, kids):
                sid = f"{when:%Y-%m-%d_%H%M}_story_{slug}-{kind}"
                build_package(sid, when, "story", [slide], bundle=feed_id, derived_from=feed_id)
                st_texts = json.loads((DRAFTS / sid / "post.json").read_text(encoding="utf-8"))["texts"]
                stray = [t for t in st_texts if t not in feed_texts and t not in joined and t not in STORY_STATIC]
                if stray and slide["template"] != "story_feed_cover":
                    raise RuntimeError(f"{sid}: story text not found in its feed or the approved list: {stray}")
        except Exception as e:
            print("SKIPPED", feed_id, "->", str(e)[:400])
            continue
        state["used"].append(key)
        made.append(feed_id)
        print("bundle ready:", feed_id, f"(+{len(sts)} stories)")
    save_state(state)
    print(f"{len(made)} bundle(s) in {DRAFTS}")


if __name__ == "__main__":
    main()
