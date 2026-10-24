"""Thin LLM client (OpenAI Responses API). Text and image-input calls. Needs the key's 'Responses' permission (api.responses.write).
Returns None-safe results: callers check llm.available() first so the pipeline still runs without it."""
import base64
import json
import os
import pathlib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).parent.parent
MODEL = os.environ.get("LLM_MODEL", "gpt-5-mini")
VISION_MODEL = os.environ.get("LLM_VISION_MODEL", "gpt-5-mini")


def _key():
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return os.environ.get("OPENAI_API_KEY") or env.get("OPENAI_API_KEY", "")


def _post(body):
    key = _key()
    req = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"LLM HTTP {e.code}: " + e.read().decode(errors="replace")[:300].replace(key, "***"))


def available():
    """True when the key may call the Responses API (cheap 1-token probe)."""
    try:
        _post({"model": MODEL, "input": "ok", "max_output_tokens": 16})
        return True
    except RuntimeError:
        return False


def _text(resp):
    parts = []
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") in ("output_text", "text"):
                    parts.append(c.get("text", ""))
    return "".join(parts).strip()


def ask_json(system, user, model=None, max_tokens=6000):
    resp = _post({"model": model or MODEL, "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                  "max_output_tokens": max_tokens, "text": {"format": {"type": "json_object"}}})
    return json.loads(_text(resp))


def ask_json_with_image(system, user, image_path, model=None, max_tokens=3000):
    b64 = base64.b64encode(pathlib.Path(image_path).read_bytes()).decode()
    content = [{"type": "input_text", "text": user}, {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"}]
    resp = _post({"model": model or VISION_MODEL, "input": [{"role": "system", "content": system}, {"role": "user", "content": content}],
                  "max_output_tokens": max_tokens, "text": {"format": {"type": "json_object"}}})
    return json.loads(_text(resp))
