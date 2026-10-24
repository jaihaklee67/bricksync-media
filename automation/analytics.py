"""Collects post performance into data/analytics/<date>.json and refreshes docs/performance.md.

Works with the permissions the app has today (likes, comments, followers). Reach/saves/shares/views need the
instagram_business_manage_insights permission; until then insights_available is false and the report says so.
Stories disappear after 24 h, so this runs daily and stores a snapshot of the live stories."""
import datetime
import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from igapi import IG, IGError

ROOT = pathlib.Path(__file__).parent.parent
OUT = ROOT / "data" / "analytics"
KST = datetime.timezone(datetime.timedelta(hours=9))
FEED_METRICS = ["reach", "saved", "shares", "total_interactions", "views"]
STORY_METRICS = ["reach", "replies", "navigation", "views"]


def snapshot():
    ig = IG()
    now = datetime.datetime.now(KST)
    acct = ig.account()
    media = ig.recent_media(30)
    insights_ok = False
    posts = []
    for m in media:
        item = {k: m.get(k) for k in ("id", "media_type", "permalink", "timestamp", "like_count", "comments_count")}
        item["caption_head"] = (m.get("caption") or "").split("\n")[0][:60]
        ins, errs = ig.insights(m["id"], FEED_METRICS)
        if ins:
            insights_ok = True
            item["insights"] = ins
        posts.append(item)
    stories = []
    for s in ig.live_stories():
        ins, errs = ig.insights(s["id"], STORY_METRICS)
        if ins:
            insights_ok = True
        stories.append({"id": s["id"], "timestamp": s.get("timestamp"), "permalink": s.get("permalink"), "insights": ins})
    snap = {"collected_at": now.isoformat(timespec="seconds"), "account": acct, "insights_available": insights_ok, "posts": posts, "stories": stories}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{now.date().isoformat()}.json"
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    return snap


def slot_label(ts):
    t = datetime.datetime.fromisoformat(ts.replace("+0000", "+00:00")).astimezone(KST)
    return f"{'월화수목금토일'[t.weekday()]} {t.hour:02d}시대"


def report(snap):
    lines = ["# 성과 요약", "", f"수집 시각: {snap['collected_at']} (KST)", "",
             f"- 팔로워 {snap['account'].get('followers_count')}명, 게시물 {snap['account'].get('media_count')}개",
             f"- 인사이트(도달·저장·공유) 수집: {'가능' if snap['insights_available'] else '불가 (instagram_business_manage_insights 권한과 새 토큰 필요)'}", "",
             "## 게시물", "", "| 게시 시각 | 유형 | 좋아요 | 댓글 | 도달 | 저장 | 공유 | 첫 줄 |", "|---|---|---|---|---|---|---|---|"]
    by_slot = defaultdict(list)
    for p in snap["posts"]:
        ins = p.get("insights", {})
        lines.append(f"| {slot_label(p['timestamp'])} | {p['media_type']} | {p.get('like_count')} | {p.get('comments_count')} | {ins.get('reach', '-')} | {ins.get('saved', '-')} | {ins.get('shares', '-')} | {p['caption_head']} |")
        score = (p.get("like_count") or 0) + 2 * (p.get("comments_count") or 0) + 3 * (ins.get("saved") or 0) + 3 * (ins.get("shares") or 0)
        by_slot[slot_label(p["timestamp"])].append(score)
    lines += ["", "## 요일·시간대별 평균 반응 점수 (좋아요 + 댓글x2 + 저장x3 + 공유x3)", "", "| 시간대 | 게시물 수 | 평균 점수 |", "|---|---|---|"]
    for k, v in sorted(by_slot.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        lines.append(f"| {k} | {len(v)} | {sum(v) / len(v):.1f} |")
    lines += ["", "표본이 적을 때는 참고용입니다. 시간대별로 최소 4~5건이 쌓인 뒤 비교하세요."]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "performance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        s = snapshot()
        report(s)
        print(f"collected {len(s['posts'])} posts, {len(s['stories'])} live stories, insights_available={s['insights_available']}")
    except IGError as e:
        print("analytics failed:", e)
        sys.exit(1)
