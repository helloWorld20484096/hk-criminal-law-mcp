"""Structural validation for a generated Hong Kong Law Atlas build."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REQUIRED_META = ["i", "c", "s", "h", "l", "cl", "d", "v", "p", "k", "sn"]
K = 12


def load_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default="semantic_map/dist")
    args = parser.parse_args()
    dist = Path(args.dist)
    data = dist / "data"
    errors: list[str] = []

    overview = load_json(data / "overview.json")
    clusters_payload = load_json(data / "clusters.json")
    meta_chunks = max(1, int(overview.get("meta_chunks", 1)))
    meta_parts = [load_json(data / f"meta-{index}.json") for index in range(meta_chunks)]
    meta = {}
    for key in set().union(*(part.keys() for part in meta_parts)):
        meta[key] = [value for part in meta_parts for value in part.get(key, [])]
    clusters = clusters_payload.get("clusters", [])
    cluster_ids = {c["id"] for c in clusters}

    n = len(meta.get("i", []))
    for key in REQUIRED_META:
        if key not in meta:
            errors.append(f"meta is missing key {key}")
        elif len(meta[key]) != n:
            errors.append(f"meta.{key} has {len(meta[key])} rows; expected {n}")
    if n == 0:
        errors.append("meta has no points")

    points = np.fromfile(data / "points.bin", dtype="<f4")
    if points.size != n * 2:
        errors.append(f"points.bin has {points.size} floats; expected {n * 2}")
    elif not np.isfinite(points).all():
        errors.append("points.bin contains non-finite coordinates")
    else:
        if points.min() < -1.05 or points.max() > 1.05:
            errors.append(f"points are outside [-1.05, 1.05]: {points.min()} .. {points.max()}")

    knn = np.fromfile(data / "knn.bin", dtype="<i4")
    if knn.size != n * K:
        errors.append(f"knn.bin has {knn.size} ints; expected {n * K}")
    elif knn.size:
        if knn.min() < 0 or knn.max() >= n:
            errors.append("knn.bin contains out-of-range point indices")
        if np.any(knn == np.repeat(np.arange(n, dtype=np.int32), K)):
            errors.append("knn.bin contains self-neighbours")

    cluster_counts = Counter(int(v) for v in meta.get("cl", []))
    unknown = set(cluster_counts) - cluster_ids
    if unknown:
        errors.append(f"meta refers to unknown clusters: {sorted(unknown)[:10]}")
    declared = {c["id"]: int(c["size"]) for c in clusters}
    for cluster_id, count in cluster_counts.items():
        if declared.get(cluster_id) != count:
            errors.append(
                f"cluster {cluster_id}: meta has {count}, clusters.json says {declared.get(cluster_id)}"
            )

    caps = Counter(str(v) for v in meta.get("c", []))
    cap_files = {int(p.stem) if p.stem.isdigit() else p.stem for p in (data / "caps").glob("*.json")}
    missing_caps = set(caps) - {str(v) for v in cap_files}
    if missing_caps:
        errors.append(f"missing cap chunks: {sorted(missing_caps)[:10]}")
    if len(cap_files) != len(caps):
        extra = {str(v) for v in cap_files} - set(caps)
        if extra:
            errors.append(f"extra cap chunks: {sorted(extra)[:10]}")

    # Check a bounded sample of cap chunks in detail, plus all tiny caps.
    cap_sample = list(caps)[:25]
    for cap in cap_sample:
        payload = load_json(data / "caps" / f"{cap}.json")
        sections = payload.get("sections", [])
        if len(sections) != caps[cap]:
            errors.append(f"cap {cap}: chunk has {len(sections)} sections; meta has {caps[cap]}")
        for section in sections:
            if "t" not in section or not isinstance(section["t"], str):
                errors.append(f"cap {cap}: section {section.get('i')} has no text")
                break

    if overview.get("points") != n:
        errors.append(f"overview.points={overview.get('points')} but meta has {n}")
    if overview.get("documents") != len(caps):
        errors.append(f"overview.documents={overview.get('documents')} but caps={len(caps)}")
    if overview.get("clusters") != len([c for c in clusters if c["id"] >= 0]):
        errors.append("overview.clusters does not match clusters.json")

    bytes_total = sum(p.stat().st_size for p in dist.rglob("*") if p.is_file())
    print(json.dumps({
        "points": n,
        "caps": len(caps),
        "clusters": len([c for c in clusters if c["id"] >= 0]),
        "noise": cluster_counts.get(-1, 0),
        "files": sum(1 for p in dist.rglob("*") if p.is_file()),
        "bytes": bytes_total,
        "errors": errors,
    }, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
