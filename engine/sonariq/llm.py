"""AI explanations. The model explains; it never sets a verdict. Every number it writes must be in the finding.

Endpoint: any OpenAI-compatible URL (env LLM_BASE_URL, LLM_MODEL). For Vertex AI the API key is a short-lived
gcloud access token. With no endpoint configured, explanations come from a deterministic template (E3: AI off).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time

NUM = re.compile(r"(?<![A-Za-z])[-−]?\d[\d,]*(?:\.\d+)?")

SYSTEM = (
    "You explain ship design compliance findings to engineers. Use only the finding JSON you are given. "
    "Never decide or change a verdict; the rule engine already decided it. Do not compute new numbers: every number "
    "you write must appear in the finding JSON. Use the engineer's words: deck, frame (Fr), port (P), starboard (S). "
    "Two to four short sentences. No product, vendor or model names."
)


def numbers_in(obj) -> set[str]:
    """All numbers that appear anywhere in a JSON-able object, normalised (no thousands commas)."""
    text = json.dumps(obj, ensure_ascii=False)
    out = set()
    for m in NUM.findall(text):
        out |= _norm(m)
    return out


def _norm(tok: str) -> set[str]:
    t = tok.replace(",", "").replace("−", "-").lstrip("-")
    out = {t}
    try:
        f = float(t)
        out.add(f"{f:g}")
        if f == int(f):
            out.add(str(int(f)))
    except ValueError:
        pass
    return out


def check_numbers(text: str, finding: dict) -> list[str]:
    """Return the numbers in `text` that are not in the finding (empty list = honest)."""
    allowed = numbers_in(finding)
    bad = []
    for m in NUM.findall(text):
        if not (_norm(m) & allowed):
            bad.append(m)
    return bad


def template_explanation(f: dict) -> str:
    loc = (f.get("location") or {}).get("label", "")
    req, meas = f.get("required") or {}, f.get("measured") or {}
    def v(d):
        if d.get("value") is None:
            return "missing"
        val = d["value"]
        val = f"{val:,}" if isinstance(val, int) else val
        return f"{val} {d.get('unit', '')}".strip()
    s = f"{f['status_word']} at {loc}: {f['title']} ({f['ref']})."
    if f["status"] == "unk":
        s += f" The model is missing {', '.join(f.get('missing') or ['an input'])}, so SonarIQ does not guess."
    else:
        s += f" Required {v(req)}, measured {v(meas)}."
    if f.get("formula"):
        s += f" {f['formula']['text']}: {f['formula']['worked']}."
    return s


class LLM:
    def __init__(self):
        self.base = os.getenv("LLM_BASE_URL")
        self.model = os.getenv("LLM_MODEL")
        self._tok = (None, 0.0)
        self.offline_since: float | None = None

    @property
    def configured(self) -> bool:
        return bool(self.base and self.model)

    def _key(self) -> str:
        if os.getenv("LLM_API_KEY"):
            return os.environ["LLM_API_KEY"]
        tok, t = self._tok
        if tok and time.time() - t < 1800:
            return tok
        tok = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True,
                             check=True, timeout=30).stdout.strip()
        self._tok = (tok, time.time())
        return tok

    def status(self) -> dict:
        return {"endpoint": "approved cloud" if self.configured else "off",
                "online": self.configured and self.offline_since is None,
                "offline_since": self.offline_since}

    def explain(self, finding: dict, question: str | None = None, retries: int = 1) -> dict:
        slim = {k: finding.get(k) for k in ("id", "title", "ref", "clause_text", "status_word", "location",
                                             "required", "measured", "margin", "formula", "method", "missing",
                                             "summary")}
        if not self.configured:
            return {"text": template_explanation(finding), "source": "template", "checked": True, "rejected": []}
        from openai import OpenAI
        rejected = []
        for _ in range(retries + 1):
            try:
                client = OpenAI(base_url=self.base, api_key=self._key(), timeout=30)
                msg = [{"role": "system", "content": SYSTEM},
                       {"role": "user", "content": json.dumps({"finding": slim, "question": question or
                                                               "Why does this fail, in plain words?"},
                                                              ensure_ascii=False)}]
                r = client.chat.completions.create(model=self.model, messages=msg, temperature=0.1, max_tokens=300)
                text = (r.choices[0].message.content or "").strip()
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
                self.offline_since = None
            except Exception as e:  # noqa: BLE001
                self.offline_since = self.offline_since or time.time()
                return {"text": template_explanation(finding), "source": "template", "checked": True,
                        "rejected": [], "error": f"AI offline: {type(e).__name__}"}
            bad = check_numbers(text, slim)
            if not bad:
                return {"text": text, "source": "ai", "checked": True, "rejected": rejected}
            rejected.append({"text": text, "numbers_not_in_finding": bad})
        return {"text": template_explanation(finding), "source": "template", "checked": True, "rejected": rejected}
