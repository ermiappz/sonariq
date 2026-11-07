"""Translate the RCRV Navisworks file to SVF with Autodesk APS, then download glTF.

Steps (Build plan, part B):
  1. two-legged token (APS_CLIENT_ID / APS_CLIENT_SECRET from .env)
  2. transient bucket
  3. signed-S3 multipart upload of the .nwd
  4. Model Derivative job, output "svf" (not svf2: svf-utils reads SVF)
  5. poll the manifest until success / failed
  6. npx svf-utils svf-to-gltf -> data/rcrv/gltf (+ properties.sqlite)

State is written to data/rcrv/aps_state.json so a re-run resumes instead of re-uploading.
Usage:  python scripts/aps_translate.py [--skip-gltf]
"""
from __future__ import annotations

import base64
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RCRV = ROOT / "data" / "rcrv"
STATE = RCRV / "aps_state.json"
BASE = "https://developer.api.autodesk.com"
CHUNK = 64 * 1024 * 1024


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def env() -> tuple[str, str]:
    load_dotenv(ROOT / ".env")
    load_dotenv(Path.home() / ".env")
    cid = os.getenv("APS_CLIENT_ID") or os.getenv("FORGE_CLIENT_ID") or os.getenv("AUTODESK_CLIENT_ID")
    sec = os.getenv("APS_CLIENT_SECRET") or os.getenv("FORGE_CLIENT_SECRET") or os.getenv("AUTODESK_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit("APS_CLIENT_ID / APS_CLIENT_SECRET missing in .env")
    os.environ["APS_CLIENT_ID"], os.environ["APS_CLIENT_SECRET"] = cid, sec
    return cid, sec


_tok: dict = {}


def token() -> str:
    if _tok and _tok["exp"] > time.time() + 60:
        return _tok["access_token"]
    cid, sec = env()
    r = requests.post(
        f"{BASE}/authentication/v2/token",
        auth=(cid, sec),
        data={"grant_type": "client_credentials",
              "scope": "data:read data:write data:create bucket:create bucket:read"},
        timeout=60,
    )
    r.raise_for_status()
    j = r.json()
    _tok.update(j, exp=time.time() + j["expires_in"])
    return j["access_token"]


def H(extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {token()}"}
    h.update(extra or {})
    return h


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(s: dict) -> None:
    STATE.write_text(json.dumps(s, indent=2))


def ensure_bucket(s: dict) -> str:
    if "bucket" in s:
        return s["bucket"]
    cid, _ = env()
    key = ("sonariq-rcrv-" + cid[:12]).lower()
    r = requests.post(f"{BASE}/oss/v2/buckets", headers=H({"Content-Type": "application/json"}),
                      json={"bucketKey": key, "policyKey": "transient"}, timeout=60)
    if r.status_code not in (200, 409):
        r.raise_for_status()
    log(f"bucket {key} ({r.status_code})")
    s["bucket"] = key
    save_state(s)
    return key


def upload(s: dict, path: Path) -> str:
    if "objectId" in s:
        return s["objectId"]
    bucket = s["bucket"]
    name = path.name
    size = path.stat().st_size
    parts = math.ceil(size / CHUNK)
    log(f"uploading {name} ({size/1e6:.1f} MB, {parts} parts)")
    url = f"{BASE}/oss/v2/buckets/{bucket}/objects/{name}/signeds3upload"
    r = requests.get(url, headers=H(), params={"parts": parts, "minutesExpiration": 60}, timeout=60)
    r.raise_for_status()
    j = r.json()
    with path.open("rb") as f:
        for i, u in enumerate(j["urls"]):
            data = f.read(CHUNK)
            for attempt in range(5):
                try:
                    pr = requests.put(u, data=data, timeout=600)
                    pr.raise_for_status()
                    break
                except Exception as e:  # noqa: BLE001
                    log(f"part {i+1} attempt {attempt+1} failed: {e}")
                    time.sleep(5)
            else:
                raise RuntimeError("upload failed")
            log(f"part {i+1}/{parts} done")
    r = requests.post(url, headers=H({"Content-Type": "application/json"}),
                      json={"uploadKey": j["uploadKey"]}, timeout=120)
    r.raise_for_status()
    oid = r.json()["objectId"]
    log(f"uploaded: {oid}")
    s["objectId"] = oid
    save_state(s)
    return oid


def urn_of(oid: str) -> str:
    return base64.urlsafe_b64encode(oid.encode()).decode().rstrip("=")


def start_job(s: dict) -> str:
    urn = urn_of(s["objectId"])
    s["urn"] = urn
    if s.get("job_started"):
        return urn
    body = {"input": {"urn": urn},
            "output": {"formats": [{"type": "svf", "views": ["2d", "3d"]}]}}
    r = requests.post(f"{BASE}/modelderivative/v2/designdata/job",
                      headers=H({"Content-Type": "application/json", "x-ads-force": "true"}),
                      json=body, timeout=120)
    log(f"job: {r.status_code} {r.text[:300]}")
    r.raise_for_status()
    s["job_started"] = True
    save_state(s)
    return urn


def poll(urn: str, max_minutes: int = 240) -> dict:
    t0 = time.time()
    while True:
        r = requests.get(f"{BASE}/modelderivative/v2/designdata/{urn}/manifest", headers=H(), timeout=60)
        if r.status_code == 200:
            m = r.json()
            (RCRV / "manifest.json").write_text(json.dumps(m, indent=1))
            log(f"manifest: status={m.get('status')} progress={m.get('progress')}")
            if m.get("status") in ("success", "failed", "timeout"):
                return m
        else:
            log(f"manifest http {r.status_code}")
        if time.time() - t0 > max_minutes * 60:
            raise TimeoutError("translation did not finish")
        time.sleep(60)


def to_gltf(urn: str) -> None:
    out = RCRV / "gltf"
    out.mkdir(parents=True, exist_ok=True)
    cmd = ["npx", "-y", "-p", "svf-utils", "svf-to-gltf", urn, "--output-folder", str(out),
           "--deduplicate", "--skip-unused-uvs", "--ignore-lines", "--ignore-points"]
    log("running: " + " ".join(cmd))
    subprocess.run(cmd, check=True, env=os.environ.copy())
    log("glTF done")


def main() -> None:
    env()
    nwd = next(RCRV.glob("*.nwd"), None)
    s = load_state()
    if not nwd and "objectId" not in s:
        sys.exit("no .nwd in data/rcrv")
    ensure_bucket(s)
    upload(s, nwd)
    urn = start_job(s)
    m = poll(urn)
    s["status"] = m.get("status")
    save_state(s)
    if m.get("status") != "success":
        sys.exit(f"translation {m.get('status')}")
    if "--skip-gltf" not in sys.argv:
        to_gltf(urn)
    log("ALL DONE")


if __name__ == "__main__":
    main()
