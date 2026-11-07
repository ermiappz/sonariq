"""Thin RAG over public sources only: MSC.1/Circ.1533, ADA 2010 Standards, the proposed PVAG (US Access Board),
COLREG (rules text), plus SonarIQ's own rule readings (rules/*.yaml) and Meyer Q&A notes (docs/meyer_qa1.md).
No SOLAS/FSS full text (not public); DNV only as links.

RAG never sets a verdict. It supplies 'Source text' with a citation for evidence cards, answers 'why' questions
with citations, and drafts rules from a clause for a human to approve.

Backends: Vertex AI RAG Engine corpus in europe-west4 (if SQ_RAG_CORPUS is set and answers), else a local
SQLite index with Vertex text embeddings (text-embedding-005, europe-west4) over the same chunks.

Build:  python -m sonariq.rag build  [--src data/rag/src]   ->  data/rag/chunks.jsonl, data/rag/index.sqlite
"""
from __future__ import annotations

import html
import json
import math
import os
import re
import sqlite3
import struct
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAG = ROOT / "data" / "rag"
CHUNKS = RAG / "chunks.jsonl"
INDEX = RAG / "index.sqlite"
EMBED_MODEL = os.getenv("SQ_EMBED_MODEL", "text-embedding-005")
EMBED_LOCATION = os.getenv("SQ_EMBED_LOCATION", "europe-west4")

SOURCES = {
    "circ1533": {"title": "IMO MSC.1/Circ.1533 (2016) Revised guidelines on evacuation analysis",
                 "url": "https://www.traffgo-ht.com/downloads/pedestrians/downloads/documents/MSC.1,Circ.1533,2016.pdf"},
    "ada2010": {"title": "2010 ADA Standards for Accessible Design", "url": "https://www.ada.gov/assets/pdfs/2010-design-standards.pdf"},
    "pvag": {"title": "US Access Board, proposed Passenger Vessels Accessibility Guidelines (PVAG)",
             "url": "https://www.access-board.gov/pvag/"},
    "colreg": {"title": "COLREG 1972, International Regulations for Preventing Collisions at Sea (rules text)",
               "url": "https://en.wikisource.org/wiki/International_Regulations_for_Preventing_Collisions_at_Sea"},
    "sonariq_rules": {"title": "SonarIQ rulebook: our readings of the rules (status verify until Meyer confirms)",
                      "url": "rules/seed_rules.yaml"},
    "meyer_qa": {"title": "SonarIQ notes for Meyer Q&A 1", "url": "docs/meyer_qa1.md"},
}
LINK_ONLY = [{"source": "dnv", "title": "DNV Rules for Classification of Ships (link only, terms do not allow copying)",
              "url": "https://www.dnv.com/rules-standards/"}]


# ------------------------------------------------------------------------------------------- chunking
def _pdftext(p: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, check=True).stdout


def _clean(t: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", t)).strip()


def chunk_circ1533(text: str) -> list[dict]:
    out, annex, app = [], None, None
    cur = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("https://edocs") or re.fullmatch(r"MSC\.1/Circ\.1533", s) or re.match(r"Annex \d, page", s):
            continue
        m = re.fullmatch(r"ANNEX (\d)", s)
        if m:
            annex, app = m.group(1), None
            continue
        m = re.fullmatch(r"APPENDIX (\d)", s)
        if m:
            app = m.group(1)
            continue
        m = re.match(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\s+([A-Z].{2,})$", s)
        if m and annex and not re.match(r"^\d+\s+(p|m|s|%)\b", s):
            if cur:
                out.append(cur)
            para = m.group(1)
            cite = f"MSC.1/Circ.1533 Annex {annex}" + (f" App.{app}" if app else "") + f" §{para}"
            cur = {"source": "circ1533", "citation": cite, "para": para, "text": s}
            continue
        if cur:
            cur["text"] += "\n" + s
    if cur:
        out.append(cur)
    return _merge_small(out)


def chunk_ada(text: str) -> list[dict]:
    out, cur = [], None
    started = False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(\d{3}(?:\.\d{1,2}){0,4})\s+([A-Z][^.]{2,80}\.)(.*)$", s)
        if m and not re.search(r"\s\d{1,3}$", s):   # skip table-of-contents lines ending in a page number
            started = True
            if cur:
                out.append(cur)
            cur = {"source": "ada2010", "citation": f"ADA 2010 §{m.group(1)}", "para": m.group(1), "text": s}
            continue
        if cur and started:
            cur["text"] += "\n" + s
    if cur:
        out.append(cur)
    return _merge_small([c for c in out if len(c["text"]) > 40])


def chunk_pvag(htmltext: str) -> list[dict]:
    body = htmltext
    i = body.find('itemprop="articleBody"')
    if i > 0:
        body = body[i:]
    parts = re.split(r"(<h[2-6][^>]*>.*?</h[2-6]>)", body, flags=re.S)
    out, cur = [], None
    for p in parts:
        hm = re.match(r"<h[2-6][^>]*>(.*?)</h[2-6]>", p, flags=re.S)
        if hm:
            title = html.unescape(re.sub(r"<[^>]+>", "", hm.group(1))).strip()
            m = re.match(r"^(V\d{3,4}(?:\.\d{1,2}){0,4})\s*(.*)$", title)
            if m:
                if cur:
                    out.append(cur)
                cur = {"source": "pvag", "citation": f"PVAG §{m.group(1)}", "para": m.group(1), "text": title}
            continue
        if cur:
            txt = html.unescape(re.sub(r"<[^>]+>", " ", p))
            cur["text"] += "\n" + re.sub(r"\s+", " ", txt).strip()
    if cur:
        out.append(cur)
    return _merge_small([c for c in out if len(c["text"]) > 30])


def chunk_colreg(htmltext: str) -> list[dict]:
    txt = html.unescape(re.sub(r"<[^>]+>", " ", htmltext))
    txt = re.sub(r"\s+", " ", txt)
    out = []
    for m in re.finditer(r"Rule (\d{1,2}) : (.*?)(?= Rule \d{1,2} : | ANNEX I\b|$)", txt):
        out.append({"source": "colreg", "citation": f"COLREG Rule {m.group(1)}", "para": f"Rule {m.group(1)}",
                    "text": f"Rule {m.group(1)}: {m.group(2)[:2500]}"})
    return out


def chunk_rules() -> list[dict]:
    out = []
    for p in sorted((ROOT / "rules").glob("*.yaml")):
        d = yaml.safe_load(p.read_text())
        for r in d.get("rules", d if isinstance(d, list) else []):
            ref = f"{r.get('source', '')} {r.get('clause', '')}".strip()
            out.append({"source": "sonariq_rules", "citation": f"SonarIQ {r['id']} (reading of {ref}, status {r.get('status')})",
                        "para": r["id"],
                        "text": f"{r['id']} {r.get('title')}. Clause {ref}: {r.get('clause_text')} Our reading: "
                                f"{r.get('reading')} Applies to: {r.get('applies_to')}. Inputs: {r.get('inputs')}. "
                                f"Parameters: {r.get('params')}. Status: {r.get('status')}."})
    return out


def chunk_md(p: Path, source: str, label: str) -> list[dict]:
    out, cur = [], None
    for line in p.read_text().splitlines():
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            if cur:
                out.append(cur)
            cur = {"source": source, "citation": f"{label} · {m.group(2).strip()}", "para": m.group(2).strip(), "text": line}
            continue
        if cur:
            cur["text"] += "\n" + line
    if cur:
        out.append(cur)
    return [c for c in out if len(c["text"]) > 40]


def _merge_small(chunks: list[dict], min_len: int = 120, max_len: int = 2400) -> list[dict]:
    out = []
    for c in chunks:
        c["text"] = _clean(c["text"])[:max_len]
        if out and len(out[-1]["text"]) < min_len and out[-1]["source"] == c["source"]:
            prev = out.pop()
            c["text"] = prev["text"] + "\n" + c["text"]
            c["citation"] = prev["citation"]
            c["para"] = prev["para"]
        out.append(c)
    return out


def build_chunks(src: Path) -> list[dict]:
    chunks = []
    if (src / "circ1533.pdf").exists():
        chunks += chunk_circ1533(_pdftext(src / "circ1533.pdf"))
    if (src / "ada2010.pdf").exists():
        chunks += chunk_ada(_pdftext(src / "ada2010.pdf"))
    for p in sorted(src.glob("pvag_v*.html")):
        chunks += chunk_pvag(p.read_text(errors="ignore"))
    if (src / "colregs_wiki.html").exists():
        chunks += chunk_colreg((src / "colregs_wiki.html").read_text(errors="ignore"))
    chunks += chunk_rules()
    if (ROOT / "docs" / "meyer_qa1.md").exists():
        chunks += chunk_md(ROOT / "docs" / "meyer_qa1.md", "meyer_qa", "Meyer Q&A 1 notes")
    for i, c in enumerate(chunks):
        c["id"] = f"{c['source']}-{i:05d}"
        c["title"] = SOURCES[c["source"]]["title"]
        c["url"] = SOURCES[c["source"]]["url"]
    return chunks


# ------------------------------------------------------------------------------------------- embeddings + index
def _embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    from google import genai
    from google.genai import types
    c = genai.Client(vertexai=True, project=os.getenv("GOOGLE_CLOUD_PROJECT", "fairway-379dc"), location=EMBED_LOCATION)
    out = []
    for i in range(0, len(texts), 100):
        batch = [t[:6000] for t in texts[i:i + 100]]
        r = c.models.embed_content(model=EMBED_MODEL, contents=batch, config=types.EmbedContentConfig(task_type=task))
        out += [e.values for e in r.embeddings]
    return out


def build_index(chunks: list[dict]) -> None:
    RAG.mkdir(parents=True, exist_ok=True)
    CHUNKS.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in chunks) + "\n")
    vecs = _embed([f"{c['citation']}\n{c['text']}" for c in chunks])
    if INDEX.exists():
        INDEX.unlink()
    db = sqlite3.connect(INDEX)
    db.execute("create table chunks (id text primary key, source text, citation text, para text, title text, url text, "
               "text text, dim int, vec blob)")
    for c, v in zip(chunks, vecs):
        db.execute("insert into chunks values (?,?,?,?,?,?,?,?,?)",
                   (c["id"], c["source"], c["citation"], c["para"], c["title"], c["url"], c["text"], len(v),
                    struct.pack(f"{len(v)}f", *v)))
    db.commit()
    db.close()


class LocalRAG:
    backend = f"local sqlite + {EMBED_MODEL} ({EMBED_LOCATION})"

    def __init__(self):
        import numpy as np
        db = sqlite3.connect(INDEX)
        rows = db.execute("select id, source, citation, para, title, url, text, dim, vec from chunks").fetchall()
        db.close()
        self.rows = [dict(zip(("id", "source", "citation", "para", "title", "url", "text"), r[:7])) for r in rows]
        m = np.array([struct.unpack(f"{r[7]}f", r[8]) for r in rows], dtype="float32")
        self.m = m / np.linalg.norm(m, axis=1, keepdims=True)
        self._qcache: dict[str, list] = {}

    def search(self, q: str, k: int = 3, source: str | None = None) -> list[dict]:
        import numpy as np
        from .llm import _key, cache_get, cache_put
        key = _key("embedq", EMBED_MODEL, q)
        v = cache_get(key)
        if v is None:
            try:
                v = _embed([q], "RETRIEVAL_QUERY")[0]
            except Exception:  # noqa: BLE001
                return self.keyword(q, k, source)
            cache_put(key, v)
        v = np.array(v, dtype="float32")
        v /= np.linalg.norm(v)
        s = self.m @ v
        # small lexical boost for exact paragraph or rule ids in the question
        for i, r in enumerate(self.rows):
            if r["para"] and len(r["para"]) > 2 and r["para"].lower() in q.lower():
                s[i] += 0.15
        order = np.argsort(-s)
        out, seen = [], set()
        for i in order:
            r = self.rows[int(i)]
            if source and r["source"] != source or r["citation"] in seen:
                continue
            seen.add(r["citation"])
            out.append({**r, "score": round(float(s[i]), 3), "text": r["text"][:900]})
            if len(out) >= k:
                break
        return out

    def keyword(self, q: str, k: int, source=None) -> list[dict]:
        words = {w for w in re.findall(r"[a-z0-9.§]{3,}", q.lower())}
        scored = []
        for r in self.rows:
            if source and r["source"] != source:
                continue
            t = (r["citation"] + " " + r["text"]).lower()
            scored.append((sum(t.count(w) for w in words), r))
        scored.sort(key=lambda x: -x[0])
        return [{**r, "score": float(s), "text": r["text"][:900]} for s, r in scored[:k] if s > 0]


MARK = re.compile(r"\[\[cite: ([^\]]+)\]\]")


def source_files() -> dict[str, str]:
    """One text file per source; every chunk starts with a [[cite: ...]] marker (maps retrieved text back)."""
    files: dict[str, list[str]] = {}
    for line in CHUNKS.read_text().splitlines():
        c = json.loads(line)
        files.setdefault(c["source"], []).append(f"[[cite: {c['citation']}]]\n{c['text']}\n")
    return {k: "\n".join(v) for k, v in files.items()}


def upload_vertex(corpus: str) -> list[dict]:
    """Upload the per-source files to a RAG Engine corpus (multipart upload, no bucket needed)."""
    import urllib.request
    import uuid
    loc = corpus.split("/")[3]
    tok = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True).stdout.strip()
    out = []
    for name, text in source_files().items():
        meta = {"rag_file": {"display_name": f"{name}.txt", "description": SOURCES[name]["title"]},
                "upload_rag_file_config": {"rag_file_transformation_config": {"rag_file_chunking_config": {
                    "fixed_length_chunking": {"chunk_size": 400, "chunk_overlap": 40}}}}}
        b = uuid.uuid4().hex
        body = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
                f"--{b}\r\nContent-Type: text/plain\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}.txt\"\r\n\r\n"
                ).encode() + text.encode() + f"\r\n--{b}--\r\n".encode()
        req = urllib.request.Request(f"https://{loc}-aiplatform.googleapis.com/upload/v1/{corpus}/ragFiles:upload",
                                     data=body, method="POST",
                                     headers={"Authorization": f"Bearer {tok}", "X-Goog-Upload-Protocol": "multipart",
                                              "Content-Type": f"multipart/related; boundary={b}"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                out.append({"file": name, "ok": True, "resp": json.loads(r.read())})
        except Exception as e:  # noqa: BLE001
            out.append({"file": name, "ok": False, "error": str(e)[:300],
                        "body": getattr(e, "read", lambda: b"")()[:300].decode(errors="ignore")})
    return out


class VertexRAG:
    """Vertex AI RAG Engine corpus (europe-west4). One file per source; [[cite: ...]] markers map hits to paragraphs."""
    def __init__(self, corpus: str, local: LocalRAG | None = None):
        self.corpus = corpus
        self.backend = f"Vertex AI RAG Engine ({corpus.split('/')[3]})"
        self.local = local
        self.files = source_files() if CHUNKS.exists() else {}
        self.by_cite = {}
        if CHUNKS.exists():
            for line in CHUNKS.read_text().splitlines():
                c = json.loads(line)
                self.by_cite[c["citation"]] = c

    def _cite_for(self, fname: str, text: str) -> str | None:
        m = MARK.findall(text)
        if m:
            return m[0] if text.find("[[cite:") < len(text) / 2 else m[-1] if len(m) == 1 else m[0]
        doc = self.files.get(fname, "")
        i = doc.find(text[:120].strip())
        if i < 0:
            return None
        prev = MARK.findall(doc[:i + 1])
        return prev[-1] if prev else None

    def _token(self):
        return subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True,
                              timeout=20).stdout.strip()

    def search(self, q: str, k: int = 3, source: str | None = None) -> list[dict]:
        import urllib.request
        loc = self.corpus.split("/")[3]
        proj = self.corpus.split("/")[1]
        body = {"vertex_rag_store": {"rag_resources": [{"rag_corpus": self.corpus}]},
                "query": {"text": q, "rag_retrieval_config": {"top_k": max(k * 3, 6)}}}
        req = urllib.request.Request(
            f"https://{loc}-aiplatform.googleapis.com/v1/projects/{proj}/locations/{loc}:retrieveContexts",
            data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.loads(r.read())
        except Exception:  # noqa: BLE001
            return self.local.search(q, k, source) if self.local else []
        out = []
        seen = set()
        for ctx in d.get("contexts", {}).get("contexts", []):
            fname = Path(ctx.get("sourceDisplayName") or ctx.get("sourceUri") or "").stem
            text = ctx.get("text", "")
            cites = MARK.findall(text)
            head = self._cite_for(fname, text) if not text.lstrip().startswith("[[cite:") else None
            for cite in ([head] if head else []) + cites:   # every paragraph the passage touches, in order
                c = self.by_cite.get(cite)
                if not c or cite in seen or (source and c["source"] != source):
                    continue
                seen.add(cite)
                out.append({**{k2: c[k2] for k2 in ("id", "source", "citation", "para", "title", "url")},
                            "text": c["text"][:900], "score": round(1 - float(ctx.get("distance", 0)), 3)})
            if len(out) >= k:
                break
        out = out[:k]
        return out or (self.local.search(q, k, source) if self.local else [])


_RAG = None


def get_rag():
    global _RAG
    if _RAG is None:
        local = LocalRAG() if INDEX.exists() else None
        corpus = os.getenv("SQ_RAG_CORPUS")
        _RAG = VertexRAG(corpus, local) if corpus else local
        if _RAG is None:
            raise ImportError("RAG index not built (python -m sonariq.rag build)")
    return _RAG


# ------------------------------------------------------------------------------------------- eval set (15)
RAG_EVAL = [
    ("How many simulations are needed for each benchmark case in an advanced evacuation analysis?", "circ1533", "§5.2"),
    ("What response duration distribution is used for the night cases?", "circ1533", "§3.2.2"),
    ("Walking speed on flat terrain for females older than 50", "circ1533", "§3.2.3"),
    ("What specific unit flow rate should an exit not exceed?", "circ1533", "§3.2.6"),
    ("Maximum specific flow for stairs going down", "circ1533", "Annex 2"),
    ("When is congestion considered significant in the advanced analysis?", "circ1533", "§3"),
    ("Initial passenger and crew distribution for the night case", "circ1533", "§4"),
    ("Minimum clear width of a door opening on an accessible route", "ada2010", "§404.2.3"),
    ("Clear width of an accessible route walking surface", "ada2010", "§403.5"),
    ("Door clear width on a passenger vessel accessible route", "pvag", "V404"),
    ("Which vessels must have an accessible route connecting decks?", "pvag", "V2"),
    ("What does a proper look-out require?", "colreg", "Rule 5"),
    ("How does SonarIQ compute the stair width from persons on each deck?", "sonariq_rules", "R-FLS-03"),
    ("What is SonarIQ's reading of the dead-end corridor rule?", "sonariq_rules", "R-FLS-02"),
    ("Must fire doors in main vertical zone bulkheads be self-closing?", "sonariq_rules", "R-FLS-10"),
]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        src = Path(sys.argv[sys.argv.index("--src") + 1]) if "--src" in sys.argv else RAG / "src"
        ch = build_chunks(src)
        from collections import Counter
        print(Counter(c["source"] for c in ch))
        build_index(ch)
        print("wrote", CHUNKS, INDEX)
    elif len(sys.argv) > 2 and sys.argv[1] == "upload":
        for r in upload_vertex(sys.argv[2]):
            print(r["file"], r["ok"], str(r.get("resp") or r.get("error"))[:200], r.get("body", ""))
    elif len(sys.argv) > 1 and sys.argv[1] == "ask":
        for h in get_rag().search(" ".join(sys.argv[2:]), 3):
            print(h["score"], h["citation"], "|", h["text"][:160].replace("\n", " "))


if __name__ == "__main__":
    main()
