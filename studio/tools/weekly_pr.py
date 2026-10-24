"""GitHub Actions entry point: plans the coming days, builds the bundles and opens one pull request per bundle.
Also opens an issue when the pool of feed topics is running low. Runs without the PC."""
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
ROOT = pathlib.Path(__file__).parent.parent
os.environ.setdefault("MEDIA_REPO", str(ROOT.parent))
os.environ.setdefault("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
import plan_content
import submit_draft


def main():
    sys.argv = ["plan_content.py", "--days", "9"]
    plan_content.main()
    if any(submit_draft.DRAFTS.glob("*/post.json")):
        sys.argv = ["submit_draft.py"]
        submit_draft.main()
        subprocess.run(["git", "checkout", "main"], cwd=submit_draft.REPO)
    left = [p for p in sorted((ROOT / "content/topics").glob("*.json")) if f"feed:{json.loads(p.read_text(encoding='utf-8'))['id']}" not in plan_content.load_state()["used"]]
    if len(left) < 3:
        body = f"남은 피드 주제가 {len(left)}개예요. 새 주제를 만들어야 해요. (Claude에게 '피드 주제 더 만들어줘'라고 말씀하시거나 OpenAI 키의 Responses 권한을 켜 주세요.)"
        subprocess.run(["gh", "issue", "create", "--title", "피드 주제가 곧 떨어져요", "--body", body], cwd=submit_draft.REPO)


if __name__ == "__main__":
    main()
