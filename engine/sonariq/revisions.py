"""Model revisions (spec B11). A model is a line of revisions; a revision is a draft (the latest Analyse, replaced by
the next one) until an Export saves it as Rev A, B, C…; a saved revision never changes except its label (a trigger
refuses anything else). SQLite for the index, one folder per saved revision for its snapshot and exported files."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from .session import DATA

DB = Path(os.getenv("SONARIQ_REVISIONS", str(DATA / "revisions.sqlite")))
_LOCK = threading.RLock()   # FastAPI runs sync endpoints in a thread pool: one writer at a time
DEMO_MODEL = "Deck 5 demo"   # the three deck 5 demo files are revisions of one model
RCRV_MODEL = "RCRV whole ship"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS models (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS revisions (
  id INTEGER PRIMARY KEY, model_id INTEGER NOT NULL REFERENCES models(id), seq INTEGER NOT NULL, label TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('draft', 'saved')), run_id TEXT NOT NULL, file TEXT, file_sha TEXT,
  counts TEXT, created TEXT NOT NULL, saved_at TEXT, UNIQUE (model_id, seq));
CREATE TRIGGER IF NOT EXISTS saved_is_frozen BEFORE UPDATE ON revisions
  WHEN OLD.state = 'saved' AND (NEW.state IS NOT OLD.state OR NEW.run_id IS NOT OLD.run_id OR NEW.file IS NOT OLD.file
    OR NEW.file_sha IS NOT OLD.file_sha OR NEW.counts IS NOT OLD.counts OR NEW.saved_at IS NOT OLD.saved_at
    OR NEW.seq IS NOT OLD.seq OR NEW.model_id IS NOT OLD.model_id OR NEW.created IS NOT OLD.created)
  BEGIN SELECT RAISE(ABORT, 'a saved revision cannot be changed (only its label)'); END;
CREATE TRIGGER IF NOT EXISTS saved_is_kept BEFORE DELETE ON revisions WHEN OLD.state = 'saved'
  BEGIN SELECT RAISE(ABORT, 'a saved revision cannot be deleted'); END;
"""


def letter(seq: int) -> str:
    """1 → A, 26 → Z, 27 → AA."""
    s = ""
    while seq > 0:
        seq, r = divmod(seq - 1, 26)
        s = chr(65 + r) + s
    return s


@contextmanager
def _db():
    """A connection that commits on success and is always closed."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(_SCHEMA)
        with c:
            yield c
    finally:
        c.close()


def folder(rev: dict) -> Path:
    return DB.with_suffix("") / str(rev["model_id"]) / str(rev["seq"])


def _row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    d["counts"] = json.loads(d["counts"] or "null")
    d["letter"] = letter(d["seq"])
    return d


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def models() -> list[dict]:
    """Every model with its revisions (oldest first)."""
    with _db() as c:
        ms = [dict(m) for m in c.execute("SELECT * FROM models ORDER BY id")]
        for m in ms:
            m["revisions"] = [_row(r) for r in c.execute("SELECT * FROM revisions WHERE model_id = ? ORDER BY seq", (m["id"],))]
        return ms


def get(rid: int) -> dict | None:
    with _db() as c:
        return _row(c.execute("SELECT * FROM revisions WHERE id = ?", (rid,)).fetchone())


def by_run(run_id: str) -> dict | None:
    with _db() as c:
        return _row(c.execute("SELECT * FROM revisions WHERE run_id = ? ORDER BY state = 'saved' DESC LIMIT 1", (run_id,)).fetchone())


def _model_for(c: sqlite3.Connection, meta: dict, model_id: int | None, new_model: str | None) -> int:
    if model_id is not None:
        if c.execute("SELECT 1 FROM models WHERE id = ?", (model_id,)).fetchone() is None:
            raise KeyError(f"no model {model_id}")
        return model_id
    name = new_model
    if not name:
        if meta.get("revision") in ("A", "B", "Bfix2"):
            name = DEMO_MODEL
        elif meta.get("revision") == "RCRV":
            name = RCRV_MODEL
        else:   # an upload: the model whose latest revision read a file of that name, else a new one
            hit = c.execute("SELECT r.model_id FROM revisions r WHERE r.file = ? ORDER BY r.id DESC LIMIT 1",
                            (meta.get("file"),)).fetchone()
            if hit:
                return hit[0]
            name = re.sub(r"\.ifc$", "", meta.get("file") or "Model", flags=re.I)
        hit = c.execute("SELECT id FROM models WHERE name = ? ORDER BY id LIMIT 1", (name,)).fetchone()
        if hit:
            return hit[0]
    return c.execute("INSERT INTO models (name, created) VALUES (?, ?)", (name[:120], _now())).lastrowid


def attach(meta: dict, model_id: int | None = None, new_model: str | None = None) -> dict:
    """Make this run the model's draft: replace the open draft's run, or open the next draft after a saved one."""
    with _LOCK, _db() as c:
        mid = _model_for(c, meta, model_id, new_model)
        draft = c.execute("SELECT id FROM revisions WHERE model_id = ? AND state = 'draft'", (mid,)).fetchone()
        counts = json.dumps(meta.get("counts"))
        if draft:
            c.execute("UPDATE revisions SET run_id = ?, file = ?, counts = ? WHERE id = ?", (meta["id"], meta.get("file"), counts, draft[0]))
            rid = draft[0]
        else:
            seq = 1 + (c.execute("SELECT MAX(seq) FROM revisions WHERE model_id = ?", (mid,)).fetchone()[0] or 0)
            rid = c.execute("INSERT INTO revisions (model_id, seq, label, state, run_id, file, counts, created) VALUES (?,?,?,?,?,?,?,?)",
                            (mid, seq, f"Rev {letter(seq)}", "draft", meta["id"], meta.get("file"), counts, _now())).lastrowid
        return _row(c.execute("SELECT * FROM revisions WHERE id = ?", (rid,)).fetchone())


def save(meta: dict, write: Callable[[Path], str]) -> dict:
    """Freeze the revision holding this run. `write(folder)` writes the snapshot and the exported files and returns the
    model file hash. Exporting a run that is already saved returns that revision unchanged; a run no revision holds
    (e.g. an older run exported after a newer Analyse) becomes the model's draft first."""
    with _LOCK:
        rev = by_run(meta["id"]) or attach(meta)
        if rev["state"] == "saved":
            return rev
        out = folder(rev)
        out.mkdir(parents=True, exist_ok=True)
        sha = write(out)
        for p in out.iterdir():
            p.chmod(0o444)
        with _db() as c:
            c.execute("UPDATE revisions SET state = 'saved', saved_at = ?, file_sha = ? WHERE id = ?", (_now(), sha, rev["id"]))
        return get(rev["id"])


def relabel(rid: int, label: str) -> dict:
    with _LOCK, _db() as c:
        if c.execute("UPDATE revisions SET label = ? WHERE id = ?", (label, rid)).rowcount == 0:
            raise KeyError(rid)
        return _row(c.execute("SELECT * FROM revisions WHERE id = ?", (rid,)).fetchone())
