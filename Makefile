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
