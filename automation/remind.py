"""Nudges the owner about approval pull requests that are still open as the first post of the bundle gets close.
A comment that @mentions the owner triggers a GitHub notification (push on the GitHub mobile app, plus e-mail)."""
import datetime
import json
import os
import re
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "jaihaklee67/bricksync-media")
OWNER = REPO.split("/")[0]
TOKEN = os.environ["GH_TOKEN"]
STEPS = [("48h", 48, "이틀 뒤"), ("24h", 24, "내일"), ("6h", 6, "6시간 뒤"), ("1h", 1, "1시간 뒤")]


def api(method, path, body=None):
    req = urllib.request.Request(f"https://api.github.com{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    for pr in api("GET", f"/repos/{REPO}/pulls?state=open&per_page=50"):
        m = re.search(r"<!-- first_post: (\S+) -->", pr.get("body") or "")
        if not m:
            continue
        first = datetime.datetime.fromisoformat(m.group(1))
        hours = (first - now).total_seconds() / 3600
        done = {c["body"] for c in api("GET", f"/repos/{REPO}/issues/{pr['number']}/comments?per_page=100")}
        if hours <= 0:
            tag = "<!-- reminder-missed -->"
            if not any(tag in d for d in done):
                api("POST", f"/repos/{REPO}/issues/{pr['number']}/comments", {"body": f"{tag}\n@{OWNER} 예약 시각이 지났어요. 지금 머지하면 15분 안에 올라가요. (6시간이 지나면 이 시각의 글은 건너뛰어요.)"})
            continue
        for key, h, label in STEPS:
            tag = f"<!-- reminder-{key} -->"
            if hours <= h and not any(tag in d for d in done):
                when = first.astimezone(datetime.timezone(datetime.timedelta(hours=9))).strftime("%m월 %d일 %H:%M")
                api("POST", f"/repos/{REPO}/issues/{pr['number']}/comments", {"body": f"{tag}\n@{OWNER} 아직 승인 전이에요. **{label}({when})**에 올라갈 글이 있어요. 머지하면 승인이고, 대화창에서 '승인'이라고 해도 돼요."})
                break


if __name__ == "__main__":
    main()
