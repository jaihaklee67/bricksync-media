"""Publishes approved posts from queue/ when their time has come.

queue/<id>/post.json  {"type": "feed"|"story", "scheduled_at": "2026-10-27T12:20:00+09:00", "images": ["slide-1.jpg", ...], "caption_file": "caption.txt"}
A post is approved by merging its pull request into main (drafts live on draft/* branches and are never read here).
published/<id>.json is written and pushed BEFORE the API call (lock), then completed afterwards, so a crash can never post twice;
a lock without a result needs a human look (the workflow opens an issue).

Usage: py automation/queue_publish.py [--dry-run] [--base-url https://jaihaklee67.github.io/bricksync-media]"""
import datetime
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from igapi import IG, IGError

ROOT = pathlib.Path(__file__).parent.parent
QUEUE, DONE = ROOT / "queue", ROOT / "published"
BASE_URL = "https://jaihaklee67.github.io/bricksync-media"
MAX_LATE_HOURS = 6  # after this the slot is considered missed and is not published automatically


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, check=check, capture_output=True, text=True)


def commit_push(paths, message):
    git("add", *[str(p) for p in paths])
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    git("-c", "user.name=bricksync-bot", "-c", "user.email=bricksync-bot@users.noreply.github.com", "commit", "-m", message)
    git("pull", "--rebase", "--autostash", check=False)
    git("push")


def due_posts(now):
    out = []
    for d in sorted(QUEUE.glob("*/post.json")):
        spec = json.loads(d.read_text(encoding="utf-8"))
        pid = d.parent.name
        when = datetime.datetime.fromisoformat(spec["scheduled_at"])
        if when <= now and not (DONE / f"{pid}.json").exists():
            out.append((pid, spec, when))
    return out


def main():
    dry = "--dry-run" in sys.argv
    base = BASE_URL
    if "--base-url" in sys.argv:
        base = sys.argv[sys.argv.index("--base-url") + 1].rstrip("/")
    now = datetime.datetime.now(datetime.timezone.utc)
    posts = due_posts(now)
    print(f"{len(posts)} post(s) due")
    problems = []
    for pid, spec, when in posts:
        late_h = (now - when).total_seconds() / 3600
        if late_h > MAX_LATE_HOURS:
            DONE.mkdir(exist_ok=True)
            (DONE / f"{pid}.json").write_text(json.dumps({"status": "missed", "scheduled_at": spec["scheduled_at"], "checked_at": now.isoformat(timespec="seconds")}, indent=1), encoding="utf-8")
            problems.append(f"{pid}: missed its slot by {late_h:.1f} h, not published")
            if not dry:
                commit_push([DONE / f"{pid}.json"], f"Mark {pid} as missed")
            continue
        urls = [f"{base}/queue/{pid}/{name}" for name in spec["images"]]
        try:
            ig = IG()
        except IGError as e:
            problems.append(str(e))
            break
        ready = [IG.check_url(u) for u in urls]
        if not all(ok for ok, _ in ready):
            print(f"{pid}: images not reachable yet {[i for _, i in ready]}; will retry on the next run")
            continue
        used, total = ig.quota()
        if used >= total - 2:
            problems.append(f"{pid}: publishing quota nearly used ({used}/{total})")
            continue
        caption = (QUEUE / pid / spec["caption_file"]).read_text(encoding="utf-8").strip() if spec.get("caption_file") else ""
        if dry:
            print(f"DRY RUN: would publish {spec['type']} {pid} ({len(urls)} image(s))")
            continue
        lock = DONE / f"{pid}.json"
        DONE.mkdir(exist_ok=True)
        lock.write_text(json.dumps({"status": "publishing", "started_at": now.isoformat(timespec="seconds"), "scheduled_at": spec["scheduled_at"]}, indent=1), encoding="utf-8")
        commit_push([lock], f"Lock {pid} before publishing")
        try:
            if spec["type"] == "story":
                info = ig.publish_story(urls[0])
            elif len(urls) == 1:
                info = ig.publish_image(urls[0], caption)
            else:
                info = ig.publish_carousel(urls, caption)
            lock.write_text(json.dumps({"status": "published", "scheduled_at": spec["scheduled_at"], "published_at": info.get("timestamp"), "media_id": info["id"], "permalink": info.get("permalink"), "type": spec["type"]}, indent=1), encoding="utf-8")
            print(f"published {pid}: {info.get('permalink')}")
        except IGError as e:
            lock.write_text(json.dumps({"status": "failed", "error": str(e)[:300], "scheduled_at": spec["scheduled_at"]}, indent=1), encoding="utf-8")
            problems.append(f"{pid}: publish failed: {str(e)[:200]}")
        commit_push([lock], f"Record result for {pid}")
    if problems:
        pathlib.Path(ROOT / "problems.txt").write_text("\n".join(problems), encoding="utf-8")
        print("PROBLEMS:\n" + "\n".join(problems))
        sys.exit(2)


if __name__ == "__main__":
    main()
