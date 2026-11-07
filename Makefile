PY := .venv/bin/python
export PYTHONPATH := engine:.
# UTF-8 file I/O on every OS and locale
export PYTHONUTF8 := 1

.PHONY: setup deck test bench dev api api-sim mcp portal rcrv qa eval eval-quick sim-precompute rag

setup:
	uv sync --python 3.11
	cd portal && npm install

deck:
	$(PY) scripts/make_deck.py

test: deck
	$(PY) -m pytest -q

bench: deck
	$(PY) scripts/bench.py

api:
	$(PY) -m uvicorn sonariq.api:app --app-dir engine --port 8765 --reload

api-sim:
	SIMULATE_ENABLED=1 $(PY) -m uvicorn sonariq.api:app --app-dir engine --port 8765

eval: deck   # rules benchmark, sim sanity, AI evals, golden path v3 -> data/out/eval.json + docs/EVAL.md
	SIMULATE_ENABLED=1 $(PY) scripts/eval.py

eval-quick: deck
	SIMULATE_ENABLED=1 $(PY) scripts/eval.py --quick --runs 8 --no-append

sim-precompute:   # demo results: Rev A / Rev B / Rev B + fix 2 night, fire what-if near Stair 3A (500 runs each)
	SIMULATE_ENABLED=1 $(PY) scripts/sim_precompute.py

mcp:
	$(PY) engine/mcp_server.py

portal:
	cd portal && npm run dev

dev:
	$(MAKE) -j2 api portal

rcrv:
	$(PY) scripts/aps_translate.py && $(PY) scripts/rcrv_to_ifc.py

qa:
	$(PY) scripts/make_qa.py

fc-check:   # needs FreeCAD 1.x + xvfb; engine must be running (make api)
	mkdir -p data/out && SQ_OUT=$(CURDIR)/data/out SQ_IFC=$(CURDIR)/data/deck5_revA.ifc xvfb-run -a -s "-screen 0 1440x900x24" freecad tests/freecad_gui_check.py; cat data/out/fc_gui_test.log

fc-golden:   # panel v2 golden path in real FreeCAD (xvfb); engine on SONARIQ_ENGINE (default 127.0.0.1:8765)
	mkdir -p data/out && SQ_OUT=$(CURDIR)/data/out SQ_DATA=$(CURDIR)/data xvfb-run -a -s "-screen 0 1440x900x24" freecad tests/freecad_golden_v2.py; cat data/out/fc_golden.log

rag:   # rebuild the local RAG index from data/rag/src (public sources only)
	$(PY) -m sonariq.rag build
