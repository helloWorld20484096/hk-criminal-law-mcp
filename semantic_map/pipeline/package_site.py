"""Package the reduced map into a static HTML data bundle."""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .common import DATA, DIST, WEB, WORK, now_iso, write_json


def normalize(values: np.ndarray) -> tuple[np.ndarray, dict]:
    lo = values.min(axis=0)
    hi = values.max(axis=0)
    span = np.where(hi - lo == 0, 1, hi - lo)
    pad = span * 0.02
    lo = lo - pad
    hi = hi + pad
    span = hi - lo
    out = ((values - lo) / span * 2 - 1).astype(np.float32)
    bounds = {
        "min": [float(v) for v in lo],
        "max": [float(v) for v in hi],
    }
    return out, bounds


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suffix", default="")
    parser.add_argument("--dist", default="")
    args = parser.parse_args()
    suffix = f"_{args.suffix}" if args.suffix else ""
    dist = Path(args.dist) if args.dist else DIST
    data_dir = dist / "data"
    cap_dir = data_dir / "caps"
    data_dir.mkdir(parents=True, exist_ok=True)
    cap_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.read_parquet(WORK / f"sections_reduced{suffix}.parquet")
    points = np.load(WORK / f"umap2d{suffix}.npy").astype(np.float32)
    clusters = np.load(WORK / f"clusters{suffix}.npy").astype(np.int32)
    knn_path = WORK / f"knn{suffix}.npy"
    knn = np.load(knn_path).astype(np.int32) if knn_path.exists() else np.zeros((len(frame), 0), dtype=np.int32)
    labels = json.loads((WORK / f"cluster_labels{suffix}.json").read_text(encoding="utf-8"))
    reduce_meta = json.loads((WORK / f"reduce_meta{suffix}.json").read_text(encoding="utf-8"))
    embed_meta_path = WORK / "embed_meta.json"
    embed_meta = json.loads(embed_meta_path.read_text(encoding="utf-8")) if embed_meta_path.exists() else {}
    export_stats_path = DATA / "export_stats.json"
    export_stats = json.loads(export_stats_path.read_text(encoding="utf-8")) if export_stats_path.exists() else {}

    if len(frame) != len(points) or len(frame) != len(clusters):
        raise SystemExit("frame/points/clusters length mismatch")

    normalized, bounds = normalize(points)
    normalized.astype("<f4").tofile(data_dir / "points.bin")
    knn.astype("<i4").tofile(data_dir / "knn.bin")

    def clean(value: object) -> str:
        return " ".join(str(value or "").split())

    meta = {
        "i": list(range(len(frame))),
        "c": [str(v) for v in frame["cap"].tolist()],
        "s": [str(v) for v in frame["section_no"].tolist()],
        "h": [clean(v) for v in frame["heading"].tolist()],
        "l": [str(v) for v in frame["language"].tolist()],
        "cl": [int(v) for v in clusters.tolist()],
        "d": [clean(v) for v in frame["doc_title"].tolist()],
        "v": [str(v)[:10] for v in frame["version_date"].tolist()],
        "p": [clean(v) for v in frame["part"].tolist()],
        "k": [clean(v) for v in frame["section_key"].tolist()],
        "sn": [clean(v)[:160] for v in frame["text"].tolist()],
    }
    meta_chunks = 1 if len(frame) < 5000 else 4
    chunk_size = math.ceil(len(frame) / meta_chunks)
    for chunk_index in range(meta_chunks):
        start = chunk_index * chunk_size
        end = min(len(frame), start + chunk_size)
        chunk = {key: values[start:end] for key, values in meta.items()}
        write_json(data_dir / f"meta-{chunk_index}.json", chunk)
    write_json(data_dir / "clusters.json", labels)

    docs = (
        frame.groupby("cap")
        .agg(
            title=("doc_title", "first"),
            long_title=("long_title", "first"),
            version_date=("version_date", "first"),
            source_url=("source_url", "first"),
        )
        .reset_index()
    )
    doc_lookup = {str(row["cap"]): row for row in docs.to_dict("records")}
    for cap, group in frame.groupby("cap"):
        doc = doc_lookup.get(str(cap), {})
        sections = []
        for row in group.sort_values(["section_no", "language"]).to_dict("records"):
            sections.append({
                "i": int(row["point_id"]),
                "s": clean(row["section_no"]),
                "k": clean(row["section_key"]),
                "h": clean(row["heading"]),
                "l": clean(row["language"]),
                "p": clean(row["part"]),
                "d": clean(row["division"]),
                "t": str(row["text"]),
                "v": str(row["version_date"])[:10],
                "u": clean(row["source_url"]),
                "cl": int(clusters[int(row["point_id"])]),
            })
        write_json(cap_dir / f"{cap}.json", {
            "cap": str(cap),
            "title": clean(doc.get("title")),
            "long_title": clean(doc.get("long_title")),
            "version_date": str(doc.get("version_date") or "")[:10],
            "source_url": clean(doc.get("source_url")),
            "sections": sections,
        })

    language_counts = frame["language"].value_counts().to_dict()
    coverage = {
        "legislation": "current-version corpus, English and Traditional Chinese",
        "historical": "not included in this map; available through statute_history",
        "judgments": "cached judgments only; the case-law graph is demand-driven",
        "citation_treatment": "not included in this map",
    }
    overview = {
        "title": "Hong Kong Law Atlas",
        "subtitle": "A semantic map of the current Hong Kong legislation corpus",
        "generated_at": now_iso(),
        "snapshot": export_stats.get("generated_at"),
        "points": int(len(frame)),
        "meta_chunks": int(meta_chunks),
        "documents": int(frame["cap"].nunique()),
        "languages": {k: int(v) for k, v in language_counts.items()},
        "sections": int(len(frame)),
        "clusters": int(len([c for c in labels["clusters"] if c["id"] >= 0])),
        "noise": int((clusters == -1).sum()),
        "model": embed_meta.get("model") or "intfloat/multilingual-e5-small",
        "embedding_dimension": embed_meta.get("dimension", 384),
        "max_seq_length": embed_meta.get("max_seq_length"),
        "pca_explained": reduce_meta.get("pca_explained"),
        "umap": reduce_meta.get("umap"),
        "clustering": reduce_meta.get("clustering"),
        "hdbscan": reduce_meta.get("hdbscan"),
        "bilingual_alignment": reduce_meta.get("bilingual_alignment"),
        "bounds": bounds,
        "coverage": coverage,
        "disclaimer": (
            "Research aid, not legal advice. Proximity in this map is semantic similarity, "
            "not legal authority or treatment. Verify every provision against the official "
            "source before relying on it."
        ),
    }
    write_json(data_dir / "overview.json", overview)

    assets = ["index.html", "app.js", "styles.css", "sw.js", "favicon.svg", "manifest.webmanifest"]
    build_id = "".join(ch for ch in str(overview.get("generated_at") or now_iso()) if ch.isalnum())[:24]
    for name in assets:
        src = WEB / name
        if not src.exists():
            continue
        if name == "sw.js":
            text = src.read_text(encoding="utf-8").replace("__BUILD_ID__", build_id)
            (dist / name).write_text(text, encoding="utf-8")
        else:
            shutil.copy2(src, dist / name)
    vendor = WEB / "vendor"
    if vendor.exists():
        (dist / "vendor").mkdir(parents=True, exist_ok=True)
        for src in vendor.iterdir():
            if src.is_file():
                shutil.copy2(src, dist / "vendor" / src.name)

    manifest = {
        "generated_at": now_iso(),
        "files": {},
    }
    for path in sorted(dist.rglob("*")):
        if path.is_file():
            manifest["files"][str(path.relative_to(dist))] = path.stat().st_size
    write_json(dist / "manifest.json", manifest)
    print(json.dumps({
        "dist": str(dist),
        "points": int(len(frame)),
        "meta_chunks": int(meta_chunks),
        "caps": int(frame["cap"].nunique()),
        "clusters": overview["clusters"],
        "noise": overview["noise"],
        "files": len(manifest["files"]),
        "bytes": sum(manifest["files"].values()),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
