PY ?= .venv/bin/python
PIP ?= .venv/bin/pip
PORT ?= 8787

.PHONY: setup test lint collect intraday reddit daily backfill site serve secrets fixtures db compact

setup:            ## create venv and install moonape in editable mode
	test -d .venv || python3.12 -m venv .venv || /opt/anaconda3/bin/python3 -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -e ".[dev]"

test:             ## unit tests on fixtures (no network, no keys)
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tests

collect:          ## run every collector once with real keys from .env
	$(PY) -m moonape collect all --force

intraday:
	$(PY) -m moonape collect intraday

reddit:
	$(PY) -m moonape collect reddit

daily:
	$(PY) -m moonape collect daily

backfill:         ## history: GME/SPY bars, treasury, FRED, EDGAR, Superstonk DD, FINRA, OCC
	$(PY) -m moonape backfill

site:             ## rebuild site/data/*.json from data/
	$(PY) -m moonape site

serve: site       ## preview the dashboard at http://localhost:$(PORT)
	cd site && ../$(PY) -m http.server $(PORT)

fixtures:         ## regenerate the synthetic Alpaca fixtures (keyless sources are recorded, not generated)
	$(PY) tests/fixtures/make_alpaca_fixtures.py

fixture-run:      ## the whole pipeline on fixtures, as CI runs it
	MOONAPE_FIXTURE=1 MOONAPE_DATA=out/fixture-data $(PY) -m moonape collect all --force
	MOONAPE_FIXTURE=1 MOONAPE_DATA=out/fixture-data $(PY) -m moonape site --out out/fixture-site

db:               ## dataset row counts and freshness
	$(PY) -m moonape db

compact:
	$(PY) -m moonape compact

secrets:          ## push .env to GitHub Actions secrets
	gh secret set -f .env
