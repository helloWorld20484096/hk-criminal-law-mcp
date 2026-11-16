.PHONY: setup download ingest ingest-en ingest-zh sync-doj test serve stats skills \
	map-export map-embed map-reduce map-label map-diagnostics map-site map-check map-serve map-all map-smoke

setup:
	python3 -m venv .venv
	.venv/bin/pip install -e '.[dev]'

download:
	.venv/bin/hk-law download --data-dir data/raw

ingest-en:
	.venv/bin/hk-law ingest --data-dir data/raw --language en

ingest-zh:
	.venv/bin/hk-law ingest --data-dir data/raw --language zh-Hant

ingest: ingest-en ingest-zh

sync-doj:
	.venv/bin/hk-law sync-doj

test:
	.venv/bin/pytest -q

serve:
	.venv/bin/hk-law serve

stats:
	.venv/bin/hk-law stats

skills:
	bash scripts/link_skills.sh

# Semantic map (optional; requires the dependencies in semantic_map/requirements-semantic.txt)
PYTHON ?= python3
SEMANTIC_DIST ?= semantic_map/dist

map-export:
	$(PYTHON) -m semantic_map.pipeline.export_corpus

map-embed:
	$(PYTHON) -m semantic_map.pipeline.embed_texts

map-reduce:
	$(PYTHON) -m semantic_map.pipeline.reduce_cluster --align-bilingual --align-alpha 0.25 --cluster-method kmeans --clusters 19

map-label:
	$(PYTHON) -m semantic_map.pipeline.label_clusters

map-diagnostics:
	$(PYTHON) -m semantic_map.pipeline.diagnostics

map-site:
	$(PYTHON) -m semantic_map.pipeline.package_site --dist $(SEMANTIC_DIST)

map-check:
	$(PYTHON) -m semantic_map.pipeline.validate_site --dist $(SEMANTIC_DIST)

map-serve:
	$(PYTHON) -m http.server 8765 --directory $(SEMANTIC_DIST)

map-smoke:
	$(PYTHON) semantic_map/tests/smoke_test.py --dist $(SEMANTIC_DIST)

map-all: map-export map-embed map-reduce map-label map-diagnostics map-site map-check
