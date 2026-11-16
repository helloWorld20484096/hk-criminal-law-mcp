"""Reduce embeddings, build the 2D map, cluster it, and compute neighbours."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors

from .common import WORK, now_iso, write_json

os.environ.setdefault("NUMBA_NUM_THREADS", str(os.cpu_count() or 8))


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--embeddings", default="")
    parser.add_argument("--suffix", default="")
    parser.add_argument("--skip-umap", action="store_true")
    parser.add_argument("--reuse-umap", action="store_true", help="reuse pca50/umap2d and only rerun clustering/kNN")
    parser.add_argument("--skip-knn", action="store_true")
    parser.add_argument("--3d", dest="three_d", action="store_true")
    parser.add_argument("--align-bilingual", action="store_true", help="pull EN/ZH translations of the same provision together")
    parser.add_argument("--align-alpha", type=float, default=0.25, help="weight on the provision's own embedding; 1-alpha goes to the bilingual centroid")
    parser.add_argument("--neighbors", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--parallel-umap", action="store_true", help="drop the fixed seed so UMAP can use multiple threads")
    parser.add_argument("--min-cluster-size", type=int, default=350)
    parser.add_argument("--min-samples", type=int, default=35)
    parser.add_argument("--cluster-method", choices=["hdbscan", "kmeans"], default="hdbscan")
    parser.add_argument("--clusters", type=int, default=19, help="number of clusters for --cluster-method kmeans")
    args = parser.parse_args()

    suffix = f"_{args.suffix}" if args.suffix else ""
    existing_meta = {}
    if args.reuse_umap:
        meta_file = WORK / f"reduce_meta{suffix}.json"
        if meta_file.exists():
            existing_meta = json.loads(meta_file.read_text(encoding="utf-8"))
    sections_path = WORK / "sections.parquet"
    texts_path = WORK / "texts.parquet"
    embeddings_path = Path(args.embeddings) if args.embeddings else WORK / "embeddings.npy"
    if not embeddings_path.exists():
        raise SystemExit(f"missing embeddings: {embeddings_path}")
    log(f"loading {embeddings_path}")
    embeddings = np.load(embeddings_path).astype(np.float32, copy=False)
    frame = pd.read_parquet(sections_path).sort_values("point_id").reset_index(drop=True)
    if args.limit:
        frame = frame[frame["text_id"] < args.limit].reset_index(drop=True)
    frame["point_id"] = range(len(frame))
    log(f"points={len(frame)} embeddings={embeddings.shape}")

    text_ids = frame["text_id"].to_numpy()
    if text_ids.max() >= len(embeddings):
        raise SystemExit("text_id exceeds embedding rows; wrong embedding file?")
    x = embeddings[text_ids].astype(np.float32, copy=True)
    if args.align_bilingual and not args.reuse_umap:
        from collections import defaultdict
        groups: dict[tuple[str, str], list[int]] = defaultdict(list)
        for row_index, (cap, key) in enumerate(zip(frame["cap"].astype(str), frame["section_key"].astype(str))):
            groups[(cap, key)].append(row_index)
        aligned = 0
        for group in groups.values():
            languages = {str(frame["language"].iloc[i]) for i in group}
            if len(languages) < 2 or len(group) < 2:
                continue
            mean = x[group].mean(axis=0)
            norm = np.linalg.norm(mean)
            if not norm:
                continue
            mean = mean / norm
            for i in group:
                blended = args.align_alpha * x[i] + (1.0 - args.align_alpha) * mean
                length = np.linalg.norm(blended)
                if length:
                    x[i] = blended / length
            aligned += len(group)
        log(f"bilingual alignment applied to {aligned} points")
    frame.to_parquet(WORK / f"sections_reduced{suffix}.parquet", index=False, compression="zstd")

    if args.reuse_umap:
        pca_path = WORK / f"pca50{suffix}.npy"
        umap_path = WORK / f"umap2d{suffix}.npy"
        if not pca_path.exists() or not umap_path.exists():
            raise SystemExit("--reuse-umap requires existing pca50/umap2d files")
        x_pca = np.load(pca_path).astype(np.float32, copy=False)
        umap2d = np.load(umap_path).astype(np.float32, copy=False)
        explained = None
        log("reusing existing PCA/UMAP")
    else:
        started = time.time()
        pca = PCA(n_components=50, svd_solver="randomized", random_state=42)
        x_pca = pca.fit_transform(x).astype(np.float32)
        np.save(WORK / f"pca50{suffix}.npy", x_pca)
        np.save(WORK / f"pca_explained{suffix}.npy", pca.explained_variance_ratio_.astype(np.float32))
        explained = float(pca.explained_variance_ratio_.sum())
        log(f"pca done in {time.time()-started:.1f}s, explained={explained:.3f}")

    if args.reuse_umap:
        pass
    elif args.skip_umap:
        umap2d = x_pca[:, :2].copy()
    else:
        import umap
        started = time.time()
        log(f"umap 2d n_neighbors={args.neighbors}")
        reducer = umap.UMAP(
            n_components=2,
            n_neighbors=args.neighbors,
            min_dist=0.05,
            metric="euclidean",
            init="pca",
            random_state=None if args.parallel_umap else args.seed,
            n_jobs=-1 if args.parallel_umap else 1,
            verbose=True,
            low_memory=False,
        )
        umap2d = reducer.fit_transform(x_pca).astype(np.float32)
        log(f"umap 2d done in {time.time()-started:.1f}s")
    np.save(WORK / f"umap2d{suffix}.npy", umap2d)

    if args.three_d:
        import umap
        started = time.time()
        log("umap 3d")
        reducer3 = umap.UMAP(
            n_components=3,
            n_neighbors=args.neighbors,
            min_dist=0.05,
            metric="euclidean",
            init="pca",
            random_state=None if args.parallel_umap else args.seed,
            n_jobs=-1 if args.parallel_umap else 1,
            verbose=True,
            low_memory=False,
        )
        umap3d = reducer3.fit_transform(x_pca).astype(np.float32)
        np.save(WORK / f"umap3d{suffix}.npy", umap3d)
        log(f"umap 3d done in {time.time()-started:.1f}s")

    started = time.time()
    if args.cluster_method == "kmeans":
        from sklearn.cluster import KMeans
        log(f"kmeans k={args.clusters}")
        clusterer = KMeans(
            n_clusters=max(2, args.clusters),
            random_state=args.seed,
            n_init=10,
        )
        labels = clusterer.fit_predict(umap2d).astype(np.int32)
        clustering_meta = {
            "method": "kmeans",
            "clusters": int(args.clusters),
            "random_state": args.seed,
            "noise": 0,
        }
        log(f"kmeans done in {time.time()-started:.1f}s, clusters={len(set(labels))}")
    else:
        log(f"hdbscan min_cluster_size={args.min_cluster_size} min_samples={args.min_samples}")
        clusterer = HDBSCAN(
            min_cluster_size=args.min_cluster_size,
            min_samples=args.min_samples,
            metric="euclidean",
            cluster_selection_method="eom",
            allow_single_cluster=False,
            n_jobs=int(os.environ.get("HK_LAW_JOBS", os.cpu_count() or 8)),
        )
        labels = clusterer.fit_predict(umap2d).astype(np.int32)
        clustering_meta = {
            "method": "hdbscan",
            "min_cluster_size": args.min_cluster_size,
            "min_samples": args.min_samples,
            "clusters": int(len(set(labels)) - 1),
            "noise": int((labels == -1).sum()),
        }
        log(f"hdbscan done in {time.time()-started:.1f}s, clusters={len(set(labels))-1}, noise={(labels==-1).sum()}")
    np.save(WORK / f"clusters{suffix}.npy", labels)

    if not args.skip_knn:
        started = time.time()
        k = 13
        log(f"knn k={k}")
        nn = NearestNeighbors(n_neighbors=k, metric="euclidean", n_jobs=-1)
        nn.fit(x_pca)
        neighbors = np.empty((len(x_pca), k - 1), dtype=np.int32)
        batch = 5000
        for start in range(0, len(x_pca), batch):
            end = min(len(x_pca), start + batch)
            idx = nn.kneighbors(x_pca[start:end], return_distance=False)
            for row_i, row in enumerate(idx):
                self_id = start + row_i
                without_self = [int(v) for v in row if int(v) != self_id][: k - 1]
                if len(without_self) < k - 1:
                    for v in row:
                        if int(v) != self_id and int(v) not in without_self:
                            without_self.append(int(v))
                neighbors[self_id] = without_self[: k - 1]
            if start and start % 20000 == 0:
                log(f"knn {start}/{len(x_pca)}")
        np.save(WORK / f"knn{suffix}.npy", neighbors)
        log(f"knn done in {time.time()-started:.1f}s")

    centroids = []
    for cluster in sorted(set(labels)):
        if cluster < 0:
            continue
        pts = umap2d[labels == cluster]
        centroids.append([cluster, float(pts[:, 0].mean()), float(pts[:, 1].mean()), int(len(pts))])
    np.save(WORK / f"cluster_centroids{suffix}.npy", np.asarray(centroids, dtype=np.float32))
    write_json(
        WORK / f"reduce_meta{suffix}.json",
        {
            "generated_at": now_iso(),
            "points": int(len(frame)),
            "embedding_dimension": int(x.shape[1]),
            "pca_components": 50,
            "pca_explained": explained if explained is not None else existing_meta.get("pca_explained"),
            "umap": (
                existing_meta.get("umap")
                if args.reuse_umap
                else {
                    "n_neighbors": args.neighbors,
                    "min_dist": 0.05,
                    "metric": "euclidean",
                    "init": "pca",
                    "random_state": None if args.parallel_umap else args.seed,
                }
            ),
            "clustering": clustering_meta,
            "hdbscan": clustering_meta if args.cluster_method == "hdbscan" else None,
            "knn": 12,
            "bilingual_alignment": (
                existing_meta.get("bilingual_alignment")
                if args.reuse_umap
                else {
                    "enabled": bool(args.align_bilingual),
                    "alpha": float(args.align_alpha),
                }
            ),
        },
    )
    log("done")


if __name__ == "__main__":
    main()
