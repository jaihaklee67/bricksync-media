"""Minimal Instagram API (Instagram Login) client used by the publisher, token refresh and analytics.
Credentials come from the environment (GitHub Actions secrets) or, on the PC, from the .env file; they are never printed."""
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://graph.instagram.com"
DEFAULT_ENV = pathlib.Path(os.environ.get("IG_ENV_FILE", r"C:\Users\PC\Documents\BrickSync_InstaAuto\.env"))


def load_env():
    env = {}
    if DEFAULT_ENV.exists():
        for line in DEFAULT_ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("IG_ACCESS_TOKEN", "IG_USER_ID", "OPENAI_API_KEY", "GH_ADMIN_TOKEN"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


class IGError(RuntimeError):
    pass


class IG:
    def __init__(self, token=None, user_id=None):
        env = load_env()
        self.token = token or env.get("IG_ACCESS_TOKEN", "")
        self.user_id = user_id or env.get("IG_USER_ID", "")
        if not self.token or not self.user_id:
            raise IGError("IG_ACCESS_TOKEN / IG_USER_ID are not set")

    def api(self, method, path, params=None, token=None):
        params = dict(params or {})
        params["access_token"] = token or self.token
        data = urllib.parse.urlencode(params)
        url = f"{BASE}/{path}" + (f"?{data}" if method == "GET" else "")
        req = urllib.request.Request(url, data=data.encode() if method == "POST" else None, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace").replace(self.token, "***")
            raise IGError(f"HTTP {e.code} on {path}: {body[:400]}")

    # ---- publishing ----
    def quota(self):
        d = self.api("GET", f"{self.user_id}/content_publishing_limit", {"fields": "quota_usage,config"})["data"][0]
        return d["quota_usage"], d["config"]["quota_total"]

    @staticmethod
    def check_url(url):
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                ctype = r.headers.get("Content-Type", "")
                return r.status == 200 and ctype.startswith("image/jpeg"), f"{r.status} {ctype}"
        except urllib.error.HTTPError as e:
            return False, f"HTTP {e.code}"
        except Exception as e:  # network trouble: treat as not ready
            return False, f"{type(e).__name__}"

    def _wait(self, cid, label):
        for _ in range(40):
            st = self.api("GET", cid, {"fields": "status_code,status"})
            if st.get("status_code") == "FINISHED":
                return
            if st.get("status_code") in ("ERROR", "EXPIRED"):
                raise IGError(f"{label}: container {st.get('status_code')}: {st}")
            time.sleep(3)
        raise IGError(f"{label}: timed out waiting for FINISHED")

    def publish_carousel(self, urls, caption):
        kids = []
        for i, u in enumerate(urls, 1):
            cid = self.api("POST", f"{self.user_id}/media", {"image_url": u, "is_carousel_item": "true"})["id"]
            self._wait(cid, f"slide {i}")
            kids.append(cid)
        cid = self.api("POST", f"{self.user_id}/media", {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption})["id"]
        self._wait(cid, "carousel")
        return self._publish(cid)

    def publish_image(self, url, caption):
        cid = self.api("POST", f"{self.user_id}/media", {"image_url": url, "caption": caption})["id"]
        self._wait(cid, "image")
        return self._publish(cid)

    def publish_story(self, url):
        cid = self.api("POST", f"{self.user_id}/media", {"image_url": url, "media_type": "STORIES"})["id"]
        self._wait(cid, "story")
        return self._publish(cid)

    def _publish(self, cid):
        media_id = self.api("POST", f"{self.user_id}/media_publish", {"creation_id": cid})["id"]
        info = self.api("GET", media_id, {"fields": "permalink,media_type,timestamp"})
        info["id"] = media_id
        return info

    # ---- reading ----
    def account(self):
        return self.api("GET", self.user_id, {"fields": "username,followers_count,follows_count,media_count"})

    def recent_media(self, limit=30):
        return self.api("GET", f"{self.user_id}/media", {"fields": "id,media_type,permalink,timestamp,like_count,comments_count,caption", "limit": limit}).get("data", [])

    def live_stories(self):
        try:
            return self.api("GET", f"{self.user_id}/stories", {"fields": "id,media_type,permalink,timestamp"}).get("data", [])
        except IGError:
            return []

    def insights(self, media_id, metrics):
        out, errors = {}, {}
        for m in metrics:  # one metric per call so an unsupported metric does not hide the others
            try:
                d = self.api("GET", f"{media_id}/insights", {"metric": m})["data"]
                out[m] = d[0]["values"][0]["value"] if d and d[0].get("values") else d[0].get("total_value", {}).get("value")
            except IGError as e:
                errors[m] = str(e)[:160]
        return out, errors

    def refresh(self):
        """Returns (new_token, expires_in_seconds). The old token keeps working until its own expiry."""
        j = self.api("GET", "refresh_access_token", {"grant_type": "ig_refresh_token"})
        return j["access_token"], j.get("expires_in", 0)
