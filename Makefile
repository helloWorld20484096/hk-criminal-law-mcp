.PHONY: setup download ingest ingest-en ingest-zh test serve stats skills

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

test:
	.venv/bin/pytest -q

serve:
	.venv/bin/hk-law serve

stats:
	.venv/bin/hk-law stats

skills:
	bash scripts/link_skills.sh
