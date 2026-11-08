"""AI gateway. Rules and simulation compute; the AI only suggests and explains; the engineer decides.

Every number the AI writes must already be in the facts it was given (number guard). If the model is slow
(> 8 s), offline, or writes a number it was not given, the engine's own wording is used instead.

Backends (env SONARIQ_AI_GATEWAY):
  gemini (default)  Gemini on Vertex AI through the Google Gen AI SDK (GEMINI_MODEL, GEMINI_LOCATION, GOOGLE_CLOUD_PROJECT).
  openai            any OpenAI-compatible server, e.g. a self-hosted open model behind vLLM on your own servers
                    (SONARIQ_AI_URL=http://host:8000/v1, SONARIQ_AI_MODEL=<served model>, optional SONARIQ_AI_KEY).
`Gateway` is the swap point: any class with `generate()` and `stream()` can replace these.
SONARIQ_AI=off turns the AI off (tests, offline demo).
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Iterator

NUM = re.compile(r"(?<![A-Za-z])[-−]?\d[\d,]*(?:\.\d+)?")
CACHE = Path(os.getenv("SQ_AI_CACHE", Path(__file__).resolve().parents[2] / "data" / "cache" / "ai"))
TIMEOUT_S = 8.0
MAX_TOKENS = 300

SYSTEM = (
    "You explain ship design compliance findings to engineers. Use only the finding JSON you are given. "
    "Never decide or change a verdict; the rule engine already decided it. Do not compute new numbers: every number "
    "you write must appear in the finding JSON. Use the engineer's words: deck, frame (Fr), port (P), starboard (S). "
    "Two to four short sentences. No product, vendor or model names."
)


# ---------------------------------------------------------------- number guard
def numbers_in(obj) -> set[str]:
    """All numbers that appear anywhere in a JSON-able object, normalised (no thousands commas)."""
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
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


_UNITS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
          "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
WORDNUM = re.compile(r"\b(" + "|".join(list(_TENS)) + r")(?:[- ](" + "|".join(["one"] + list(_UNITS)[:8]) + r"))?\b|\b("
                     + "|".join(_UNITS) + r")\b", re.I)


def _word_numbers(text: str) -> list[tuple[str, str]]:
    """Number words in text -> (word, digits). 'one' alone is skipped (usually a pronoun)."""
    out = []
    for m in WORDNUM.finditer(text):
        if m.group(1):
            v = _TENS[m.group(1).lower()] + ({"one": 1} | _UNITS).get((m.group(2) or "").lower(), 0)
        else:
            v = _UNITS[m.group(3).lower()]
        out.append((m.group(0), str(v)))
    return out


def check_numbers(text: str, facts) -> list[str]:
    """Return the numbers in `text` (digits or number words) that are not in the facts (empty list = honest)."""
    allowed = numbers_in(facts)
    bad = [m for m in NUM.findall(text) if not (_norm(m) & allowed)]
    bad += [w for w, v in _word_numbers(text) if v not in allowed]
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


# ---------------------------------------------------------------- gateway
class Gateway:
    """Swap point for the model. Implementations return plain text (or a JSON string when `schema` is given)."""
    name = "none"

    def generate(self, system: str, prompt: str, schema: dict | None = None, max_tokens: int = MAX_TOKENS) -> str:
        raise NotImplementedError

    def stream(self, system: str, prompt: str, max_tokens: int = MAX_TOKENS) -> Iterator[str]:
        yield self.generate(system, prompt, None, max_tokens)

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


def _project() -> str:
    p = os.getenv("GOOGLE_CLOUD_PROJECT")
    if p:
        return p
    try:
        return subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


class GeminiGateway(Gateway):
    def __init__(self, model: str | None = None, location: str | None = None):
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.location = location or os.getenv("GEMINI_LOCATION", "eu")
        self.name = f"{self.model}@{self.location}"
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai
            from google.genai import types
            self._client = genai.Client(vertexai=True, project=_project(), location=self.location,
                                        http_options=types.HttpOptions(timeout=int(TIMEOUT_S * 1000)))
        return self._client

    def _config(self, system, schema, max_tokens):
        from google.genai import types
        kw = dict(system_instruction=system, max_output_tokens=max_tokens, temperature=0.1,
                  thinking_config=types.ThinkingConfig(thinking_level="minimal"))
        if schema:
            kw |= dict(response_mime_type="application/json", response_json_schema=schema)
        return types.GenerateContentConfig(**kw)

    def generate(self, system, prompt, schema=None, max_tokens=MAX_TOKENS):
        r = self.client.models.generate_content(model=self.model, contents=prompt,
                                                config=self._config(system, schema, max_tokens))
        return (r.text or "").strip()

    def stream(self, system, prompt, max_tokens=MAX_TOKENS):
        for ch in self.client.models.generate_content_stream(model=self.model, contents=prompt,
                                                             config=self._config(system, None, max_tokens)):
            if ch.text:
                yield ch.text

    def embed(self, texts):
        out = []
        for i in range(0, len(texts), 50):
            r = self.client.models.embed_content(model=os.getenv("GEMINI_EMBED_MODEL", "text-embedding-005"),
                                                 contents=texts[i:i + 50])
            out += [e.values for e in r.embeddings]
        return out


class OpenAICompatGateway(Gateway):
    """Self-hosted path: an OpenAI-compatible chat endpoint (vLLM, TGI, llama.cpp server). Standard library only."""

    def __init__(self, url: str | None = None, model: str | None = None, key: str | None = None):
        self.url = (url or os.getenv("SONARIQ_AI_URL", "http://127.0.0.1:8000/v1")).rstrip("/")
        self.model = model or os.getenv("SONARIQ_AI_MODEL", "Qwen/Qwen2.5-7B-Instruct")
        self.key = key if key is not None else os.getenv("SONARIQ_AI_KEY", "")
        self.name = f"{self.model}@{self.url.split('//')[-1].split('/')[0]}"

    def _post(self, path: str, body: dict) -> dict:
        import urllib.request
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self.key}"} if self.key else {})})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read())

    def generate(self, system, prompt, schema=None, max_tokens=MAX_TOKENS):
        body = {"model": self.model, "temperature": 0.1, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}
        return (self._post("/chat/completions", body)["choices"][0]["message"]["content"] or "").strip()

    def embed(self, texts):
        r = self._post("/embeddings", {"model": os.getenv("SONARIQ_AI_EMBED_MODEL", self.model), "input": texts})
        return [d["embedding"] for d in r["data"]]


def make_gateway() -> Gateway:
    kind = os.getenv("SONARIQ_AI_GATEWAY", "gemini").lower()
    return OpenAICompatGateway() if kind in ("openai", "vllm", "local") else GeminiGateway()


# ---------------------------------------------------------------- disk cache
def _key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:24]


def cache_get(key: str):
    p = CACHE / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return None
    return None


def cache_put(key: str, value) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{key}.json").write_text(json.dumps(value, ensure_ascii=False, indent=1))


_POOL = cf.ThreadPoolExecutor(max_workers=4)


class LLM:
    def __init__(self, gateway: Gateway | None = None):
        self.enabled = os.getenv("SONARIQ_AI", "on").lower() not in ("off", "0", "false")
        self.gateway = gateway or make_gateway()
        self.offline_since: float | None = None
        self.last_ms: float | None = None

    @property
    def configured(self) -> bool:
        return self.enabled and self.gateway is not None

    def status(self) -> dict:
        return {"endpoint": self.gateway.name if self.configured else "off",
                "online": self.configured and self.offline_since is None,
                "offline_since": self.offline_since, "last_ms": self.last_ms}

    # -- raw call with timeout + cache
    def call(self, system: str, prompt: str, schema: dict | None = None, max_tokens: int = MAX_TOKENS,
             use_cache: bool = True) -> tuple[str | None, str]:
        """Returns (text or None, source) where source is 'cache' | 'ai' | 'off' | 'timeout' | 'error:<type>'."""
        if not self.configured:
            return None, "off"
        key = _key(self.gateway.name, system, prompt, schema, max_tokens)
        if use_cache and (hit := cache_get(key)) is not None:
            return hit["text"], "cache"
        t = time.time()
        fut = _POOL.submit(self.gateway.generate, system, prompt, schema, max_tokens)
        try:
            text = fut.result(timeout=TIMEOUT_S)
        except cf.TimeoutError:
            self.offline_since = self.offline_since or time.time()
            return None, "timeout"
        except Exception as e:  # noqa: BLE001
            self.offline_since = self.offline_since or time.time()
            return None, f"error:{type(e).__name__}"
        self.offline_since = None
        self.last_ms = round((time.time() - t) * 1000)
        cache_put(key, {"text": text, "model": self.gateway.name, "ms": self.last_ms, "system": system,
                       "prompt": prompt, "json": bool(schema)})
        return text, "ai"

    def guarded(self, system: str, facts, question: str, fallback: str, retries: int = 1) -> dict:
        """Free-text answer about `facts`; every number must be in `facts`, else the engine's `fallback` text."""
        prompt = json.dumps({"facts": facts, "question": question}, ensure_ascii=False, default=str)
        rejected = []
        for i in range(retries + 1):
            text, src = self.call(system, prompt + (f"\n(retry {i})" if i else ""))
            if text is None:
                out = {"text": fallback, "source": "template", "checked": True, "rejected": rejected}
                if src != "off":
                    out["error"] = f"AI offline: {src}"
                return out
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
            bad = check_numbers(text, facts)
            if not bad:
                return {"text": text, "source": "ai", "cached": src == "cache", "checked": True, "rejected": rejected}
            rejected.append({"text": text, "numbers_not_in_facts": bad})
        return {"text": fallback, "source": "template", "checked": True, "rejected": rejected}

    def ask_json(self, system: str, prompt: str, schema: dict) -> tuple[dict | None, str]:
        text, src = self.call(system, prompt, schema=schema)
        if text is None:
            return None, src
        try:
            return json.loads(text), src
        except json.JSONDecodeError:
            return None, "error:json"

    # -- findings
    @staticmethod
    def slim(finding: dict) -> dict:
        return {k: finding.get(k) for k in ("id", "title", "ref", "clause_text", "status_word", "location",
                                            "required", "measured", "margin", "formula", "method", "missing",
                                            "summary")}

    def explain(self, finding: dict, question: str | None = None, retries: int = 1) -> dict:
        return self.guarded(SYSTEM, self.slim(finding), question or "Why does this fail, in plain words?",
                            template_explanation(finding), retries)

    def stream_guarded(self, system: str, facts, question: str, fallback: str) -> Iterator[dict]:
        """SSE events: {'delta'} while streaming, then {'done', text, source}. If the finished text has a number
        that is not in the facts, a final {'replace'} event swaps it for the engine's text."""
        prompt = json.dumps({"facts": facts, "question": question}, ensure_ascii=False, default=str)
        key = _key(self.gateway.name if self.configured else "off", system, prompt, None, MAX_TOKENS)
        hit = cache_get(key) if self.configured else None
        if hit:
            text = hit["text"]
            bad = check_numbers(text, facts)
            yield {"done": True, "text": text if not bad else fallback, "source": "ai" if not bad else "template",
                   "cached": True}
            return
        if not self.configured:
            yield {"done": True, "text": fallback, "source": "template"}
            return
        buf, t = [], time.time()
        try:
            for d in self.gateway.stream(system, prompt):
                buf.append(d)
                yield {"delta": d}
                if time.time() - t > TIMEOUT_S:
                    raise TimeoutError
        except Exception as e:  # noqa: BLE001
            self.offline_since = self.offline_since or time.time()
            yield {"replace": True, "done": True, "text": fallback, "source": "template",
                   "error": f"AI offline: {type(e).__name__}"}
            return
        text = "".join(buf).strip()
        bad = check_numbers(text, facts)
        if bad:
            yield {"replace": True, "done": True, "text": fallback, "source": "template",
                   "rejected": [{"text": text, "numbers_not_in_facts": bad}]}
            return
        cache_put(key, {"text": text, "model": self.gateway.name, "system": system, "prompt": prompt})
        yield {"done": True, "text": text, "source": "ai"}
