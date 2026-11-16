# Hong Kong Law Atlas

A static, responsive **semantic map** of the current Hong Kong legislation
corpus. Every English and Traditional Chinese provision is embedded, reduced
to two dimensions with UMAP, clustered into 19 topics with KMeans, and rendered in a WebGL
explorer that works on desktop and mobile.

This is a low-dimensional visualization of high-dimensional legal text: a map
for discovery, not a citator and not legal advice.

## What is in the map

- All current-version legislation sections/schedules indexed in `data/hk_law.db`.
- English and Traditional Chinese text, embedded together with a multilingual model.
- 19 topic clusters with bilingual, automatically generated labels.
- HDBSCAN remains available as an optional density-based clustering mode.
- Nearest-neighbour lists for every provision.
- Full provision text on demand, with a link to the official e-Legislation source.

Not in this map: historical versions, judgments, citation treatment, and a
citator graph. Those require additional ingestion and licensing review.

## Quick start

The pipeline needs `sentence-transformers`, `torch`, `umap-learn`, `scikit-learn`,
`pandas`, `pyarrow`, and `numpy`. Install the optional extras:

```bash
python3 -m pip install -e '.[semantic]'
```

Build the atlas from the local corpus:

```bash
python3 -m semantic_map.pipeline.export_corpus   # SQLite -> parquet
python3 -m semantic_map.pipeline.embed_texts     # multilingual embeddings
python3 -m semantic_map.pipeline.reduce_cluster --align-bilingual --align-alpha 0.25 --cluster-method kmeans --clusters 19  # PCA -> UMAP -> KMeans -> kNN
python3 -m semantic_map.pipeline.label_clusters  # bilingual cluster labels
python3 -m semantic_map.pipeline.diagnostics     # cluster/pair quality report
python3 -m semantic_map.pipeline.package_site    # static site -> semantic_map/dist
python3 -m semantic_map.pipeline.validate_site   # structural QA
```

The entry point is `semantic_map/dist/index.html`. It is a static HTML app,
not a single monolithic file: the 120k-point corpus is split into on-demand
data chunks. Serve the directory over HTTP (do not open `index.html` with
`file://`; browsers block `fetch()` for local files):

```bash
python3 -m http.server 8765 --directory semantic_map/dist
# open http://127.0.0.1:8765/
```

Or use the Makefile:

```bash
make map-all
make map-serve
```

If the pipeline dependencies live in `.venv`, point the targets at it:
`make PYTHON=.venv/bin/python map-all`.

The full embedding and UMAP stages are long-running on CPU. Run them in the
background or on a GPU machine. For a faster, non-deterministic UMAP pass, add
`--parallel-umap` to `reduce_cluster`; omit it (and use `--seed 42`) when you
need a reproducible projection. `make map-smoke` requires Playwright and a
Chrome/Chromium binary; pass `--chrome /path/to/chrome` if it is not at
`/usr/bin/google-chrome`.

## Why a semantic map

A node-link graph of 120,000 sections is a hairball. UMAP preserves local
neighbourhoods well enough to make topics, outliers, and related provisions
visible; KMeans gives a complete 19-cluster navigational partition (HDBSCAN
remains available for density-based runs). The result is a
map you can pan, zoom, search, lasso, and inspect — not a diagram of every
citation.

The map and a future citation graph are complementary:

- **Semantic map** — “what is similar to this provision?”
- **Citation graph** — “what cites, interprets, follows, or overrules this provision?”

Keep them as separate views over the same corpus.

## Pipeline

```text
legislation_sections (SQLite)
        │ export_corpus.py
        ▼
deduplicated texts (parquet)
        │ embed_texts.py
        ▼
384-dimensional embeddings (multilingual-e5-small)
        │ reduce_cluster.py
        ├─ bilingual alignment (alpha 0.25)
        ├─ PCA 50
        ├─ UMAP 2D (n_neighbors=30, min_dist=0.05, init=pca)
        ├─ KMeans (19 clusters; HDBSCAN optional)
        └─ 12 nearest neighbours per point
        │ label_clusters.py
        ▼
bilingual cluster labels + colours
        │ package_site.py
        ▼
semantic_map/dist/
```

### Data contract

`dist/data/meta-<n>.json` is split into chunks (four for the full corpus) and is column-oriented to keep each payload compact:

```json
{
  "i": [0, 1],
  "c": ["221", "221"],
  "s": ["9J", "9J"],
  "h": ["Review of refusal of bail...", "拒絕保釋..."],
  "l": ["en", "zh-Hant"],
  "cl": [4, 4],
  "d": ["Criminal Procedure Ordinance", "刑事訴訟程序條例"],
  "v": ["2026-05-14", "2026-05-14"],
  "p": ["Part 1A", "第1A部"],
  "k": ["s9J", "s9J"],
  "sn": ["A person may apply...", "任何人可申請..."]
}
```

`dist/data/points.bin` is `Float32` interleaved `x, y` in `[-1, 1]`.
`dist/data/knn.bin` is `Int32` with 12 neighbours per point.
`dist/data/clusters.json` contains labels, colours, sizes, and top terms.
`dist/data/caps/<cap>.json` contains full provision text, loaded on demand.
`dist/data/overview.json` contains counts, model/UMAP/clustering parameters, and
the coverage/legal disclaimer.

## Front-end

- WebGL scatter plot via vendored `regl-scatterplot` (no CDN, no server).
- Search across citations, headings, ordinance titles, and provision snippets.
- Filters for language, ordinance, and cluster.
- Lasso selection, nearest-neighbour focus, bilingual pair lookup.
- Cluster labels are drawn above cluster bounds and collision-tested.
- Desktop: three panes. Mobile: full-width map, filter drawer, detail sheet,
  and a table view fallback.
- Dark mode, reduced-motion support, keyboard shortcuts (`/`, `L`, `F`, `Esc`).
- Service worker caches the shell and visited data for offline use.

The CSP allows `'unsafe-eval'` because `regl` compiles shaders at runtime. All
scripts and libraries are vendored locally; there are no remote requests.

## Payload and performance

- `points.bin` is about 1 MB for 120k points.
- `knn.bin` is about 6 MB.
- `meta-<n>.json` is split into chunks; static hosts should gzip/Brotli them.
- Provision text is loaded per Cap. from `data/caps/<cap>.json`, so the full
  corpus is never downloaded at once.
- Rendering is WebGL; the app caps visible labels and uses a table fallback on
  small or slow devices.

## Deployment

The `dist/` directory is a static site. Deploy it to GitHub Pages, Cloudflare
Pages, Netlify, or any static host. Serve it over HTTP/HTTPS so `fetch()` and
the service worker work.

For GitHub Pages, publish the contents of `semantic_map/dist/` (for example on
a `gh-pages` branch or via a Pages workflow). The generated data is large
enough that it should be deployed as a build artifact, not committed to the
source tree.

## Reproducibility and limits

- Record the embedding model, max sequence length, bilingual alignment, PCA/UMAP
  parameters, clustering parameters, random seed, and corpus snapshot in
  `overview.json`.
- UMAP distances are semantic similarity, not legal authority, treatment, or
  hierarchy.
- Cluster labels are generated from frequent terms and the top ordinances in
  each cluster; they are provisional and should be reviewed by a lawyer.
- The map is current-version only. Historical versions remain available through
  the MCP `statute_history` tool; judgments remain demand-driven.
- Text is sourced from the Hong Kong Department of Justice e-Legislation XML on
  DATA.GOV.HK and is reproduced with attribution. Verify every provision against
  the official source.
