"""Quality diagnostics for the semantic map."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .common import WORK


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suffix", default="")
    args = parser.parse_args()
    suffix = f"_{args.suffix}" if args.suffix else ""
    frame = pd.read_parquet(WORK / f"sections_reduced{suffix}.parquet")
    points = np.load(WORK / f"umap2d{suffix}.npy")
    clusters = np.load(WORK / f"clusters{suffix}.npy")
    labels_payload = json.loads((WORK / f"cluster_labels{suffix}.json").read_text(encoding="utf-8"))
    labels = {c["id"]: c for c in labels_payload["clusters"]}
    knn_path = WORK / f"knn{suffix}.npy"
    knn = np.load(knn_path) if knn_path.exists() else None

    cluster_ids = {int(v) for v in clusters}
    report = {"points": int(len(frame)), "clusters": len(cluster_ids - {-1}), "noise": int((clusters == -1).sum())}

    # Bilingual pair distances vs nearest-neighbour distances.
    pair_distances = []
    for (cap, key), group in frame.groupby(["cap", "section_key"]):
        if group["language"].nunique() > 1 and len(group) >= 2:
            a = int(group.iloc[0]["point_id"])
            b = int(group.iloc[1]["point_id"])
            pair_distances.append(float(np.linalg.norm(points[a] - points[b])))
    knn_distances = []
    if knn is not None:
        for i in range(0, len(points), max(1, len(points) // 5000)):
            for j in knn[i]:
                if 0 <= j < len(points):
                    knn_distances.append(float(np.linalg.norm(points[i] - points[j])))
    report["bilingual_pairs"] = len(pair_distances)
    report["bilingual_pair_distance_median"] = float(np.median(pair_distances)) if pair_distances else None
    report["knn_distance_median"] = float(np.median(knn_distances)) if knn_distances else None
    report["bilingual_ratio"] = (
        float(np.median(pair_distances) / np.median(knn_distances))
        if pair_distances and knn_distances and np.median(knn_distances)
        else None
    )

    # Cluster composition.
    rows = []
    language_purity = []
    cap_purity = []
    for cluster_id in sorted(set(int(v) for v in clusters)):
        if cluster_id < 0:
            continue
        mask = clusters == cluster_id
        group = frame[mask]
        langs = Counter(group["language"].astype(str))
        caps = Counter(group["cap"].astype(str))
        language_purity.append(max(langs.values()) / len(group))
        cap_purity.append(max(caps.values()) / len(group))
        rows.append({
            "id": cluster_id,
            "size": int(mask.sum()),
            "label": labels.get(cluster_id, {}).get("label"),
            "label_zh": labels.get(cluster_id, {}).get("label_zh"),
            "languages": dict(langs),
            "top_caps": caps.most_common(3),
        })
    report["language_purity_weighted"] = (
        float(np.average(language_purity, weights=[r["size"] for r in rows])) if rows else None
    )
    report["cap_purity_weighted"] = (
        float(np.average(cap_purity, weights=[r["size"] for r in rows])) if rows else None
    )
    rows.sort(key=lambda row: row["size"], reverse=True)
    report["top_clusters"] = rows[:20]
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
