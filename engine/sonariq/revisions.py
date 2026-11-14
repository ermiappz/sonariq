"""Projects -> models -> revisions (spec B11 + Studio reliability, DECISIONS M15). A project has models; a model is a
line of revisions; a revision is one file version (`source`: demo:<A|B|Bfix2>, rcrv, path:<file>) plus its analysis
state. It is a draft (its latest Analyse replaces the run) until Save / Export freezes it; a saved revision never
changes except its label (a trigger refuses anything else). Analysing a saved revision opens a new draft of the same
file. SQLite for the index, one folder per saved revision for its snapshot and exported files. Demo projects (the
demo run-through's throwaway copy) are the only ones whose saved revisions may be deleted."""
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
DEMO_MODEL = "Deck 5"        # the three deck 5 demo files are revisions of one model
RCRV_MODEL = "RCRV whole ship"
DEMO_PROJECT = "Demo ship"
DECK5 = [("Rev A", "demo:A", "deck5_revA.ifc"), ("Rev B", "demo:B", "deck5_revB.ifc"), ("Fix 2", "demo:Bfix2", "deck5_revB_fix2.ifc")]
DEMO_TTL_S = 3600            # a demo run-through's throwaway project is deleted after an hour at the latest

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL,
  demo INTEGER NOT NULL DEFAULT 0, shared INTEGER NOT NULL DEFAULT 0, guide_done INTEGER NOT NULL DEFAULT 0, expires TEXT);
CREATE TABLE IF NOT EXISTS models (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL,
  project_id INTEGER REFERENCES projects(id));
CREATE TABLE IF NOT EXISTS revisions (
  id INTEGER PRIMARY KEY, model_id INTEGER NOT NULL REFERENCES models(id), seq INTEGER NOT NULL, label TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('draft', 'saved')), run_id TEXT, file TEXT, file_sha TEXT, source TEXT,
  counts TEXT, created TEXT NOT NULL, saved_at TEXT, UNIQUE (model_id, seq));
CREATE TRIGGER IF NOT EXISTS saved_is_frozen BEFORE UPDATE ON revisions
  WHEN OLD.state = 'saved' AND (NEW.state IS NOT OLD.state OR NEW.run_id IS NOT OLD.run_id OR NEW.file IS NOT OLD.file
    OR NEW.file_sha IS NOT OLD.file_sha OR NEW.counts IS NOT OLD.counts OR NEW.saved_at IS NOT OLD.saved_at
    OR NEW.seq IS NOT OLD.seq OR NEW.model_id IS NOT OLD.model_id OR NEW.created IS NOT OLD.created)
  BEGIN SELECT RAISE(ABORT, 'a saved revision cannot be changed (only its label)'); END;
CREATE TRIGGER IF NOT EXISTS saved_is_kept BEFORE DELETE ON revisions WHEN OLD.state = 'saved' AND NOT EXISTS
  (SELECT 1 FROM models m JOIN projects p ON p.id = m.project_id WHERE m.id = OLD.model_id AND p.demo = 1)
  BEGIN SELECT RAISE(ABORT, 'a saved revision cannot be deleted'); END;
"""


def letter(seq: int) -> str:
    """1 → A, 26 → Z, 27 → AA."""
    s = ""
    while seq > 0:
        seq, r = divmod(seq - 1, 26)
        s = chr(65 + r) + s
    return s


def _migrate(c: sqlite3.Connection) -> None:
    """Step 7 store (models -> revisions, no projects) -> projects. The deck 5 and RCRV revisions so far were made by
    demo runs and tests: the old index and their folders are archived (data/archive/<ts>-projects/, never deleted)
    and re-seeded. Any other model (an upload) keeps its revisions, in a project "Earlier uploads"."""
    import shutil
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    arch = DB.parent / "archive" / f"{ts}-projects"
    arch.mkdir(parents=True, exist_ok=True)
    c.commit()
    c.execute("VACUUM INTO ?", (str(arch / DB.name),))
    old = [dict(m) for m in c.execute("SELECT * FROM models")]
    keep = [m for m in old if m["name"] not in ("Deck 5 demo", RCRV_MODEL)]
    for m in old:
        if m not in keep and (DB.with_suffix("") / str(m["id"])).exists():
            shutil.move(str(DB.with_suffix("") / str(m["id"])), str(arch / f"model-{m['id']}"))
    c.executescript("""
      DROP TRIGGER IF EXISTS saved_is_frozen; DROP TRIGGER IF EXISTS saved_is_kept;
      ALTER TABLE revisions RENAME TO revisions_old; ALTER TABLE models RENAME TO models_old;""")
    c.executescript(_SCHEMA)
    if keep:
        pid = c.execute("INSERT INTO projects (name, created) VALUES ('Earlier uploads', ?)", (_now(),)).lastrowid
        for m in keep:
            c.execute("INSERT INTO models (id, name, created, project_id) VALUES (?,?,?,?)", (m["id"], m["name"], m["created"], pid))
        c.execute(f"""INSERT INTO revisions (id, model_id, seq, label, state, run_id, file, file_sha, counts, created, saved_at)
                      SELECT id, model_id, seq, label, state, run_id, file, file_sha, counts, created, saved_at
                      FROM revisions_old WHERE model_id IN ({",".join(str(m["id"]) for m in keep)})""")
    c.executescript("DROP TABLE revisions_old; DROP TABLE models_old;")
    _seed_demo_ship(c)       # after the kept models, so their ids (and saved folders) stay as they were
    c.commit()


def _seed_demo_ship(c: sqlite3.Connection) -> None:
    """The shared project every visitor starts in: Deck 5 (Rev A, Rev B, Fix 2) and the RCRV whole ship (Rev 1),
    not analysed yet. Re-created after Reset all data."""
    pid = c.execute("INSERT INTO projects (name, created, shared) VALUES (?, ?, 1)", (DEMO_PROJECT, _now())).lastrowid
    _add_model(c, pid, DEMO_MODEL, DECK5)
    if (DATA / "rcrv" / "gltf").exists():
        _add_model(c, pid, RCRV_MODEL, [("Rev 1", "rcrv", "RCRV whole ship")])


def _add_model(c: sqlite3.Connection, pid: int, name: str, revs: list[tuple[str, str, str]]) -> int:
    mid = c.execute("INSERT INTO models (name, created, project_id) VALUES (?, ?, ?)", (name[:120], _now(), pid)).lastrowid
    for seq, (label, source, file) in enumerate(revs, 1):
        c.execute("INSERT INTO revisions (model_id, seq, label, state, source, file, created) VALUES (?,?,?,?,?,?,?)",
                  (mid, seq, label, "draft", source, file, _now()))
    return mid


@contextmanager
def _db():
    """A connection that commits on success and is always closed. Migrates a step 7 store and seeds an empty one."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        with _LOCK:
            cols = {r[1] for r in c.execute("PRAGMA table_info(revisions)")}
            if cols and "source" not in cols:
                _migrate(c)
            c.executescript(_SCHEMA)
            if c.execute("SELECT 1 FROM projects LIMIT 1").fetchone() is None:
                _seed_demo_ship(c)
                c.commit()
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


def models(project_id: int | None = None) -> list[dict]:
    """Every model (of one project) with its revisions (oldest first)."""
    with _db() as c:
        q, args = ("SELECT * FROM models WHERE project_id = ? ORDER BY id", (project_id,)) if project_id else ("SELECT * FROM models ORDER BY id", ())
        ms = [dict(m) for m in c.execute(q, args)]
        for m in ms:
            m["revisions"] = [_row(r) for r in c.execute("SELECT * FROM revisions WHERE model_id = ? ORDER BY seq", (m["id"],))]
        return ms


def get(rid: int) -> dict | None:
    with _db() as c:
        return _row(c.execute("SELECT * FROM revisions WHERE id = ?", (rid,)).fetchone())


def by_run(run_id: str) -> dict | None:
    with _db() as c:
        return _row(c.execute("SELECT * FROM revisions WHERE run_id = ? ORDER BY state = 'saved' DESC LIMIT 1", (run_id,)).fetchone())


def scope_of(rid: int) -> dict | None:
    """revision -> {revision, model, project} (ids and names), for links that name only a run or a revision."""
    with _db() as c:
        r = c.execute("""SELECT r.id rid, m.id mid, m.name mname, p.id pid, p.name pname FROM revisions r
                         JOIN models m ON m.id = r.model_id LEFT JOIN projects p ON p.id = m.project_id WHERE r.id = ?""", (rid,)).fetchone()
        return dict(r) if r else None


# ------------------------------------------------------------------------------------------------ projects
def _project(c: sqlite3.Connection, pid: int) -> dict | None:
    p = c.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None:
        return None
    d = dict(p)
    d["models"] = [dict(m) for m in c.execute("SELECT * FROM models WHERE project_id = ? ORDER BY id", (pid,))]
    for m in d["models"]:
        m["revisions"] = [_row(r) for r in c.execute("SELECT * FROM revisions WHERE model_id = ? ORDER BY seq", (m["id"],))]
    return d


def projects() -> list[dict]:
    """Every project people work in (not the demo's throwaway ones), with models and revisions."""
    with _db() as c:
        return [_project(c, r[0]) for r in c.execute("SELECT id FROM projects WHERE demo = 0 ORDER BY id")]


def project(pid: int) -> dict | None:
    with _db() as c:
        return _project(c, pid)


def default_project() -> int:
    """Where runs without a project go (the FreeCAD panel): the shared demo project, else the first one."""
    with _db() as c:
        r = c.execute("SELECT id FROM projects WHERE demo = 0 ORDER BY shared DESC, id LIMIT 1").fetchone()
        return r[0] if r else c.execute("INSERT INTO projects (name, created, shared) VALUES (?, ?, 1)", (DEMO_PROJECT, _now())).lastrowid


def create_project(name: str, demo: bool = False) -> dict:
    with _LOCK, _db() as c:
        exp = (dt.datetime.now() + dt.timedelta(seconds=DEMO_TTL_S)).isoformat(timespec="seconds") if demo else None
        pid = c.execute("INSERT INTO projects (name, created, demo, expires) VALUES (?, ?, ?, ?)", (name[:80], _now(), int(demo), exp)).lastrowid
        if demo:
            _add_model(c, pid, DEMO_MODEL, DECK5[:2])
        return _project(c, pid)


def update_project(pid: int, name: str | None = None, guide_done: bool | None = None) -> dict:
    with _LOCK, _db() as c:
        if c.execute("SELECT 1 FROM projects WHERE id = ?", (pid,)).fetchone() is None:
            raise KeyError(pid)
        if name is not None:
            c.execute("UPDATE projects SET name = ? WHERE id = ?", (name[:80], pid))
        if guide_done is not None:
            c.execute("UPDATE projects SET guide_done = ? WHERE id = ?", (int(guide_done), pid))
        return _project(c, pid)


def delete_demo_project(pid: int) -> list[dict]:
    """Delete a demo project with everything in it. Returns its revisions (the caller drops their runs and marks).
    Only demo projects: a real project's saved revisions are never deleted."""
    import shutil
    with _LOCK, _db() as c:
        p = c.execute("SELECT demo FROM projects WHERE id = ?", (pid,)).fetchone()
        if p is None:
            raise KeyError(pid)
        if not p[0]:
            raise PermissionError("only a demo project can be deleted")
        revs = [_row(r) for r in c.execute("SELECT r.* FROM revisions r JOIN models m ON m.id = r.model_id WHERE m.project_id = ?", (pid,))]
        for r in revs:
            shutil.rmtree(folder(r), ignore_errors=True)
        c.execute("DELETE FROM revisions WHERE model_id IN (SELECT id FROM models WHERE project_id = ?)", (pid,))
        for m in c.execute("SELECT id FROM models WHERE project_id = ?", (pid,)).fetchall():
            shutil.rmtree(DB.with_suffix("") / str(m[0]), ignore_errors=True)
        c.execute("DELETE FROM models WHERE project_id = ?", (pid,))
        c.execute("DELETE FROM projects WHERE id = ?", (pid,))
        return revs


def expired_demo_projects() -> list[int]:
    with _db() as c:
        return [r[0] for r in c.execute("SELECT id FROM projects WHERE demo = 1 AND expires < ?", (_now(),))]


def add_model(pid: int, name: str, source: str, file: str) -> dict:
    """Upload "New model in this project": the model and its first revision (not analysed yet)."""
    with _LOCK, _db() as c:
        if c.execute("SELECT 1 FROM projects WHERE id = ?", (pid,)).fetchone() is None:
            raise KeyError(f"no project {pid}")
        mid = _add_model(c, pid, name, [("Rev A", source, file)])
        return _row(c.execute("SELECT * FROM revisions WHERE model_id = ?", (mid,)).fetchone())


def add_revision(model_id: int, source: str, file: str) -> dict:
    """Upload "New revision of <model>": the next revision, not analysed yet."""
    with _LOCK, _db() as c:
        if c.execute("SELECT 1 FROM models WHERE id = ?", (model_id,)).fetchone() is None:
            raise KeyError(f"no model {model_id}")
        return _new_rev(c, model_id, source, file)


def _new_rev(c: sqlite3.Connection, mid: int, source: str | None, file: str | None, run_id: str | None = None,
             counts: str | None = None) -> dict:
    seq = 1 + (c.execute("SELECT MAX(seq) FROM revisions WHERE model_id = ?", (mid,)).fetchone()[0] or 0)
    rid = c.execute("INSERT INTO revisions (model_id, seq, label, state, run_id, file, source, counts, created) VALUES (?,?,?,?,?,?,?,?,?)",
                    (mid, seq, f"Rev {letter(seq)}", "draft", run_id, file, source, counts, _now())).lastrowid
    return _row(c.execute("SELECT * FROM revisions WHERE id = ?", (rid,)).fetchone())


def source_of(meta: dict) -> str | None:
    """The file a run read, as a revision source."""
    rv = meta.get("revision")
    if rv in ("A", "B", "Bfix2"):
        return f"demo:{rv}"
    if rv == "RCRV":
        return "rcrv"
    return f"path:{meta['path']}" if meta.get("path") else None


def _model_for(c: sqlite3.Connection, meta: dict, model_id: int | None, new_model: str | None, pid: int) -> int:
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
            hit = c.execute("""SELECT r.model_id FROM revisions r JOIN models m ON m.id = r.model_id
                               WHERE r.file = ? AND m.project_id = ? ORDER BY r.id DESC LIMIT 1""", (meta.get("file"), pid)).fetchone()
            if hit:
                return hit[0]
            name = re.sub(r"\.ifc$", "", meta.get("file") or "Model", flags=re.I)
        hit = c.execute("SELECT id FROM models WHERE name = ? AND project_id = ? ORDER BY id LIMIT 1", (name, pid)).fetchone()
        if hit:
            return hit[0]
    return c.execute("INSERT INTO models (name, created, project_id) VALUES (?, ?, ?)", (name[:120], _now(), pid)).lastrowid


def attach(meta: dict, model_id: int | None = None, new_model: str | None = None, revision_id: int | None = None) -> dict:
    """File this run under a revision and return it. With `revision_id` (the Studio): that revision's draft takes the
    run; a saved one opens a new draft of the same file. Without (the FreeCAD panel): the model's draft that read the
    same file takes it, else a new draft. A newly opened draft carries `from_revision` (its marks and tasks are
    copied from there by the caller)."""
    counts = json.dumps(meta.get("counts"))
    with _LOCK:
        pid = None if revision_id else default_project()
        with _db() as c:
            if revision_id is not None:
                r = _row(c.execute("SELECT * FROM revisions WHERE id = ?", (revision_id,)).fetchone())
                if r is None:
                    raise KeyError(f"no revision {revision_id}")
                if r["state"] == "draft":
                    c.execute("UPDATE revisions SET run_id = ?, counts = ? WHERE id = ?", (meta["id"], counts, r["id"]))
                    return _row(c.execute("SELECT * FROM revisions WHERE id = ?", (r["id"],)).fetchone())
                return {**_new_rev(c, r["model_id"], r["source"], r["file"], meta["id"], counts), "from_revision": r["id"]}
            mid = _model_for(c, meta, model_id, new_model, pid)
            src = source_of(meta)
            draft = c.execute("SELECT id FROM revisions WHERE model_id = ? AND state = 'draft' AND (source = ? OR (source IS NULL AND file = ?)) "
                              "ORDER BY seq DESC LIMIT 1", (mid, src, meta.get("file"))).fetchone()
            if draft:
                c.execute("UPDATE revisions SET run_id = ?, counts = ? WHERE id = ?", (meta["id"], counts, draft[0]))
                return _row(c.execute("SELECT * FROM revisions WHERE id = ?", (draft[0],)).fetchone())
            prev = c.execute("SELECT id FROM revisions WHERE model_id = ? AND (source = ? OR file = ?) ORDER BY seq DESC LIMIT 1",
                             (mid, src, meta.get("file"))).fetchone()
            r = _new_rev(c, mid, src, meta.get("file"), meta["id"], counts)
            return {**r, "from_revision": prev[0]} if prev else r


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
