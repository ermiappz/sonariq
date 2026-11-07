# Blockers

| # | Since (EET) | Blocker | Impact | What unblocks it |
|---|---|---|---|---|
| 1 | 05:40 | Qwen on Vertex AI returns 404 / "not available in region" for project `fairway-379dc` (tried `qwen/qwen3-235b-a22b-instruct-2507-maas` and `qwen/qwen3-next-80b-a3b-instruct-maas` on us-south1, global and us-central1). The model has not been enabled in Model Garden for this project. | `explain()` falls back to the engine's own wording (badge "Rule engine text"). Verdicts, fixes and edits do not need the AI, so nothing else is blocked. | In the console: Vertex AI → Model Garden → Qwen3 235B (MaaS) → Enable. Then put `LLM_BASE_URL=https://us-south1-aiplatform.googleapis.com/v1/projects/fairway-379dc/locations/us-south1/endpoints/openapi` and `LLM_MODEL=qwen/qwen3-235b-a22b-instruct-2507-maas` in `.env`. The key is fetched with `gcloud auth print-access-token`. |
