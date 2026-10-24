"""Turns draft packages (output/drafts/<id>/) into ONE pull request per bundle (a feed post plus the stories derived from it).
Merging the pull request is the approval. Stories of a feed that was already approved are pushed straight to main (auto-approved).

  py tools/submit_draft.py --all              # one PR per bundle; auto-approved stories go directly to main
  py tools/submit_draft.py --approve 5 6 7    # merge pull requests (only on the user's explicit approval in chat)
In GitHub Actions (GH_TOKEN set) the workflow's token is used; on the PC the stored GitHub login is used. Tokens are never printed."""
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).parent.parent
REPO = pathlib.Path(os.environ.get("MEDIA_REPO", r"C:\Users\PC\Documents\GitHub\bricksync-media"))
SLUG = os.environ.get("GITHUB_REPOSITORY", "jaihaklee67/bricksync-media")
DRAFTS = ROOT / "output" / "drafts"
NL = "\n"
BOT = ["-c", "user.name=bricksync-bot", "-c", "user.email=bricksync-bot@users.noreply.github.com"] if os.environ.get("GH_TOKEN") else \
      ["-c", "user.name=jaihaklee67", "-c", "user.email=jaihaklee67@users.noreply.github.com"]


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def token():
    if os.environ.get("GH_TOKEN"):
        return os.environ["GH_TOKEN"]
    r = subprocess.run(["git", "credential", "fill"], input="protocol=https" + NL + "host=github.com" + NL + "username=jaihaklee67" + NL + NL,
                       capture_output=True, text=True, cwd=REPO)
    for line in r.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise RuntimeError("no stored GitHub credential for jaihaklee67")


def api(method, path, body=None):
    req = urllib.request.Request(f"https://api.github.com{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token()}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def copy_in(ids):
    for pid in ids:
        dst = REPO / "queue" / pid
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(DRAFTS / pid, dst)
    for name in ("data/facts.json", "config/story_static.json"):
        if (ROOT / name).exists():
            (REPO / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, REPO / name)


def validate():
    v = subprocess.run([sys.executable, "automation/validate_queue.py"], cwd=REPO, capture_output=True, text=True)
    if v.returncode:
        raise RuntimeError("validate_queue failed:" + NL + v.stdout[-900:])


def submit_bundle(feed_id, ids):
    """One PR containing the feed and its derived stories."""
    posts = {pid: json.loads((DRAFTS / pid / "post.json").read_text(encoding="utf-8")) for pid in ids}
    branch = f"draft/{feed_id}"
    git("fetch", "origin", "main")
    git("checkout", "-B", branch, "origin/main")
    try:
        copy_in(ids)
        validate()
        git("add", "queue", "data", "config")
        git(*BOT, "commit", "-m", f"Draft: {feed_id} (+{len(ids) - 1} stories)")
        git("push", "--force", "-u", "origin", branch)
        first = min(p["scheduled_at"] for p in posts.values())
        blocks = []
        for pid in ids:
            post = posts[pid]
            raw = f"https://raw.githubusercontent.com/{SLUG}/{branch}/queue/{pid}"
            previews = " ".join(f"![{n}]({raw}/{n})" for n in post["images"])
            cap = ""
            if post.get("caption_file"):
                text = (REPO / "queue" / pid / post["caption_file"]).read_text(encoding="utf-8").strip()
                cap = NL * 2 + "캡션" + NL * 2 + "```" + NL + text + NL + "```"
            tag = "피드" if post["type"] == "feed" else "스토리 (피드 내용에서 파생)"
            blocks.append(f"### {tag} | {post['scheduled_at'][:16].replace('T', ' ')}" + NL + NL + previews + cap)
        body = (f"<!-- first_post: {first} -->" + NL + "**이 PR을 머지(Merge)하면 승인**이에요. 피드와 그 피드로 만든 스토리가 모두 예약 시각에 자동으로 올라가요. "
                "대화창에서 '승인'이라고 말씀하셔도 제가 머지해 드려요. 고칠 곳이 있으면 머지하지 말고 알려 주세요." + NL * 2 + (NL * 2 + "---" + NL * 2).join(blocks))
        feed_post = posts[feed_id]
        title = f"[승인 요청] {feed_post['scheduled_at'][5:10]} 피드 + 스토리 {len(ids) - 1}건 ({feed_id.split('_feed_')[1]})"
        pr = api("POST", f"/repos/{SLUG}/pulls", {"title": title, "head": branch, "base": "main", "body": body})
        print(title.encode("ascii", "replace").decode(), "->", pr["html_url"])
    finally:
        git("checkout", "main", check=False)


def push_direct(ids):
    """Stories whose feed is already approved: straight to main."""
    git("fetch", "origin", "main")
    git("checkout", "main")
    git("pull", "--rebase", "origin", "main", check=False)
    copy_in(ids)
    validate()
    git("add", "queue", "data", "config")
    git(*BOT, "commit", "-m", f"Auto-approved stories of an approved feed: {', '.join(ids)[:180]}")
    git("push")
    print("pushed to main:", len(ids), "story post(s)")


def approve(numbers):
    for n in numbers:
        pr = api("GET", f"/repos/{SLUG}/pulls/{n}")
        res = api("PUT", f"/repos/{SLUG}/pulls/{n}/merge", {"merge_method": "merge"})
        print("merged PR", n, res.get("merged"))


def main():
    if "--approve" in sys.argv:
        approve([int(x) for x in sys.argv[sys.argv.index("--approve") + 1:]])
        return
    ids = sorted(p.name for p in DRAFTS.iterdir() if (p / "post.json").exists())
    posts = {i: json.loads((DRAFTS / i / "post.json").read_text(encoding="utf-8")) for i in ids}
    auto = [i for i in ids if posts[i].get("auto_approved")]
    if auto:
        push_direct(auto)
    bundles = {}
    for i in ids:
        if i not in auto:
            bundles.setdefault(posts[i].get("bundle", i), []).append(i)
    for feed_id, members in bundles.items():
        members.sort(key=lambda i: (posts[i]["type"] != "feed", posts[i]["scheduled_at"]))
        submit_bundle(feed_id, members)


if __name__ == "__main__":
    main()
