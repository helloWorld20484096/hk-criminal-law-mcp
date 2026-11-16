#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PYTHON="${PYTHON:-python3}"
"$PYTHON" -m semantic_map.pipeline.export_corpus
"$PYTHON" -m semantic_map.pipeline.embed_texts
"$PYTHON" -m semantic_map.pipeline.reduce_cluster --align-bilingual --align-alpha 0.25 --cluster-method kmeans --clusters 19
"$PYTHON" -m semantic_map.pipeline.label_clusters
"$PYTHON" -m semantic_map.pipeline.diagnostics
"$PYTHON" -m semantic_map.pipeline.package_site
"$PYTHON" -m semantic_map.pipeline.validate_site
