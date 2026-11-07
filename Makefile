PY := .venv/bin/python
export PYTHONPATH := engine:.

.PHONY: setup deck test bench dev api mcp portal rcrv qa

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
