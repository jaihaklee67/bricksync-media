"""Refreshes the long-lived Instagram token (60 days) and records its expiry date.

Local run (PC):   py automation/refresh_token.py          -> new token is written to .env, expiry to data/token_state.json
GitHub Actions:   py automation/refresh_token.py --ci     -> new token is stored in the IG_ACCESS_TOKEN repository secret
                  (needs the GH_ADMIN_TOKEN secret: a fine-grained token with 'Secrets: read and write' on this repo).
                  Without it the script fails loudly so that the workflow opens an issue.
The token itself is never printed."""
import base64
import datetime
import json
import os
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from igapi import IG, IGError, DEFAULT_ENV

ROOT = pathlib.Path(__file__).parent.parent
STATE = ROOT / "data" / "token_state.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "jaihaklee67/bricksync-media")


def write_env(new_token):
    lines = DEFAULT_ENV.read_text(encoding="utf-8").splitlines()
    out, done = [], False
    for ln in lines:
        if ln.startswith("IG_ACCESS_TOKEN="):
            out.append("IG_ACCESS_TOKEN=" + new_token)
            done = True
        else:
            out.append(ln)
    if not done:
        out.append("IG_ACCESS_TOKEN=" + new_token)
    DEFAULT_ENV.write_text("\n".join(out) + "\n", encoding="utf-8")


def gh(method, path, token, body=None):
    req = urllib.request.Request(f"https://api.github.com{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def update_secret(name, value, admin_token):
    from nacl import encoding, public  # pip install pynacl
    key = gh("GET", f"/repos/{REPO}/actions/secrets/public-key", admin_token)
    box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
    enc = base64.b64encode(box.encrypt(value.encode())).decode()
    gh("PUT", f"/repos/{REPO}/actions/secrets/{name}", admin_token, {"encrypted_value": enc, "key_id": key["key_id"]})


def main():
    ci = "--ci" in sys.argv
    ig = IG()
    new_token, expires_in = ig.refresh()
    expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in)).date().isoformat()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"expires_at": expires_at, "expires_in_days": round(expires_in / 86400, 1),
                                 "refreshed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                                 "token_changed": new_token != ig.token}, indent=1), encoding="utf-8")
    if ci:
        admin = os.environ.get("GH_ADMIN_TOKEN")
        if not admin:
            if new_token != ig.token:
                raise SystemExit("token was refreshed but GH_ADMIN_TOKEN is missing, so the secret could not be updated")
        elif new_token != ig.token:
            update_secret("IG_ACCESS_TOKEN", new_token, admin)
    elif new_token != ig.token and DEFAULT_ENV.exists():
        write_env(new_token)
    print(f"refreshed: expires {expires_at} (in {expires_in / 86400:.0f} days), token changed: {new_token != ig.token}")


if __name__ == "__main__":
    try:
        main()
    except IGError as e:
        print("refresh failed:", e)
        sys.exit(1)
