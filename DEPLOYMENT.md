# Deploying SonarIQ

SonarIQ is one Python service (the rule engine + API), a static web portal, and optional pieces (AI gateway,
evacuation simulation, FreeCAD add-on). Nothing needs a GPU, and nothing needs the internet unless you turn the
cloud AI on.

| Part | What it is | Port / path |
|---|---|---|
| Engine API | FastAPI (`engine/sonariq/api.py`), Python 3.11 | 127.0.0.1:8780 (hosted) or 8765 (dev) |
| Portal | static build of `portal/` (Vite) | served by the web server at `/` |
| Downloads | FreeCAD add-on zip, demo models, Mac setup script | `/downloads` |
| Data | runs, reports, tasks, uploads, caches | `data/` (or `SONARIQ_DATA`) |

## 1. Single VM (what the live demo runs)

Tested on Debian 13, 4 vCPU, 16 GB. Requires `git`, `uv`, Node.js 20+, `caddy`, `zip`.

```bash
git clone https://github.com/ermiappz/sonariq ~/sonariq && cd ~/sonariq
scripts/deploy_vm.sh                 # deploys branch main (BRANCH=... for another)
```

The script:

- checks out the branch into a separate worktree (`~/sonariq-deploy`), so development never touches the running site;
- installs Python deps (`uv sync`) and builds the portal;
- runs the engine as a systemd user service `sonariq-api` on 127.0.0.1:8780 with `SONARIQ_HOSTED=1` (only files
  under `data/` can be opened) and `SIMULATE_ENABLED=1`;
- copies the portal and downloads to `/srv/sonariq`;
- writes the Caddyfile (`scripts/caddy_write.sh`): HTTPS with a Let's Encrypt certificate on `<ip>.sslip.io`,
  public portal and downloads, `/api` open to the portal's key (`X-SonarIQ-Key`) or basic auth (FreeCAD panel).

Credentials (`SQ_USER`, `SQ_PASS`, `SQ_PORTAL_KEY`) are generated once into `~/.sonariq_deploy` (mode 600, never in
git). The portal key is compiled into the browser bundle (`VITE_SQ_KEY`); it keeps the API off the open internet but
is not a secret. Real deployments put the portal behind your SSO instead.

Operations:

```bash
journalctl --user -u sonariq-api -f      # engine log
sudo journalctl -u caddy -f              # web server log
scripts/demo_reset.sh                    # archive all runs/reports/tasks to data/archive/<ts>, fresh start
scripts/demo_restore.sh <ts>             # put an archive back
```

The portal's **Settings → Reset all data** does the same as `demo_reset.sh` without a restart (`POST /admin/reset`).

## 2. On-premises (no cloud at all)

1. Same as above on an internal VM; replace the Caddy site name with your internal host and certificate
   (or put the engine behind your existing reverse proxy: proxy `/api/*` to 127.0.0.1:8780 with the prefix stripped,
   serve `portal/dist` as static files).
2. AI off: `SONARIQ_AI=off` in the service environment. Verdicts, evidence, BCF, simulation and the FreeCAD panel work
   unchanged; explanations show the engine's own wording.
3. RAG: the local index (`data/rag/index.sqlite`) works offline for retrieval; rebuilding it with new documents needs an
   embedding model (see below).
4. Data stays in `data/`. Back it up like any application folder.

### Switching the AI to a self-hosted model

The AI gateway (`engine/sonariq/llm.py`) is chosen by environment:

| Setting | Gateway |
|---|---|
| `SONARIQ_AI_GATEWAY=gemini` (default) | Gemini on Vertex AI: `GEMINI_MODEL`, `GEMINI_LOCATION=eu`, `GOOGLE_CLOUD_PROJECT`, Application Default Credentials |
| `SONARIQ_AI_GATEWAY=openai` | any OpenAI-compatible server: `SONARIQ_AI_URL=http://<host>:8000/v1`, `SONARIQ_AI_MODEL=<served model>`, optional `SONARIQ_AI_KEY` |
| `SONARIQ_AI=off` | no AI |

Example with vLLM on a GPU server inside your network:

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct --port 8000          # on the GPU host
# in the engine's service environment:
SONARIQ_AI_GATEWAY=openai
SONARIQ_AI_URL=http://gpu-host:8000/v1
SONARIQ_AI_MODEL=Qwen/Qwen2.5-7B-Instruct
```

Whatever the model, every answer passes the number guard: a sentence with a number the engine did not produce is
thrown away and the engine's wording is shown. Answers slower than 8 s fall back the same way. The OpenAI-compatible
path is covered by unit tests against a stub server; it has not yet been run against a live vLLM.

## 3. Containers

No container image ships yet. The service is a plain ASGI app, so a minimal image is:

```dockerfile
FROM python:3.11-slim
RUN pip install uv
WORKDIR /app
COPY . .
RUN uv sync --frozen
ENV PYTHONPATH=engine:. SONARIQ_HOSTED=1
CMD [".venv/bin/python", "-m", "uvicorn", "sonariq.api:app", "--app-dir", "engine", "--host", "0.0.0.0", "--port", "8780"]
```

Mount `data/` as a volume and serve the portal build from any static web server or a second nginx container.

## Red Hat OpenShift AI

- Engine: the image above as a Deployment + Service; `data/` on a PersistentVolumeClaim; a Route for `/api`.
- Portal: static build in an nginx (UBI) image, Route for `/`.
- AI: serve an open model with the vLLM ServingRuntime in OpenShift AI (KServe) and point
  `SONARIQ_AI_GATEWAY=openai`, `SONARIQ_AI_URL=<inference service URL>/v1` at it. Everything stays in the cluster.
- Simulation runs on CPU in the engine pod (`SQ_SIM_WORKERS`, default 3); give the pod 2–4 cores.

## 4. FreeCAD add-on

Users get it from `/downloads`: `setup_freecad_mac.sh` (macOS one-liner) or `SonarIQ-addon.zip` (any OS, unzip into
FreeCAD's `Mod` folder). The panel reads `~/.sonariq.json` (`engine`, `user`, `password`); without it, it talks to a
local engine on 127.0.0.1:8765 and sends file paths instead of uploading.

## 5. Environment reference

| Variable | Default | Meaning |
|---|---|---|
| `SONARIQ_DATA` | `data/` | data folder (runs, uploads, caches) |
| `SONARIQ_HOSTED` | `0` | `1`: clients may only open files under the data folder |
| `SIMULATE_ENABLED` | `0` | evacuation simulation endpoints |
| `SONARIQ_RATE_LIMIT` | on | `0` disables the per-IP limits (chat 20, analyse 30, upload 10, simulate 10 per minute) |
| `SONARIQ_UPLOAD_MB` | `400` | upload limit on the engine (the web Studio limits to 60 MB) |
| `SONARIQ_AI`, `SONARIQ_AI_GATEWAY`, `SONARIQ_AI_URL`, `SONARIQ_AI_MODEL`, `SONARIQ_AI_KEY` | | AI, see above |
| `GEMINI_MODEL`, `GEMINI_LOCATION`, `GOOGLE_CLOUD_PROJECT` | | Gemini gateway |
| `SQ_RAG_CORPUS` | | use a Vertex AI RAG Engine corpus instead of the local index |
| `SQ_SIM_WORKERS` | `3` | simulation worker processes |
