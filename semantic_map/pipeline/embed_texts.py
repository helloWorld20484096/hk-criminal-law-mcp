"""Embed deduplicated legislation texts with a multilingual sentence model.

The job is resumable: partial embeddings are checkpointed every CHECKPOINT
texts so a long CPU run can be interrupted without starting over.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer

from .common import WORK, now_iso, write_json

MODEL_NAME = os.environ.get("HK_LAW_EMBED_MODEL", "intfloat/multilingual-e5-small")
MAX_EN_CHARS = int(os.environ.get("HK_LAW_EMBED_MAX_EN_CHARS", "2600"))
MAX_ZH_CHARS = int(os.environ.get("HK_LAW_EMBED_MAX_ZH_CHARS", "1200"))
BATCH_SIZE = int(os.environ.get("HK_LAW_EMBED_BATCH", "128"))
CHECKPOINT = int(os.environ.get("HK_LAW_EMBED_CHECKPOINT", "10000"))


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="embed only the first N texts")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args()
    if args.shards < 1 or not (0 <= args.shard < args.shards):
        raise SystemExit("invalid shard configuration")

    threads = int(os.environ.get("HK_LAW_EMBED_THREADS", os.cpu_count() or 8))
    torch.set_num_threads(max(1, threads))
    log(f"threads={threads} model={MODEL_NAME} batch={BATCH_SIZE}")

    texts_path = WORK / "texts.parquet"
    if not texts_path.exists():
        raise SystemExit(f"missing {texts_path}; run export_corpus.py first")

    frame = pd.read_parquet(texts_path).sort_values("text_id").reset_index(drop=True)
    if args.limit:
        frame = frame.head(args.limit).copy()
    if args.shards > 1:
        import math
        chunk_size = math.ceil(len(frame) / args.shards)
        start = args.shard * chunk_size
        end = min(len(frame), start + chunk_size)
        frame = frame.iloc[start:end].reset_index(drop=True)
    total = len(frame)
    log(f"texts={total} shard={args.shard}/{args.shards}")

    model = SentenceTransformer(MODEL_NAME)
    model.max_seq_length = int(os.environ.get("HK_LAW_EMBED_MAX_SEQ", "512"))
    dim = int(
        model.get_embedding_dimension()
        if hasattr(model, "get_embedding_dimension")
        else model.get_sentence_embedding_dimension()
    )

    suffix = f"shard{args.shard}" if args.shards > 1 else ""
    if args.limit:
        stem = f"embeddings_test_{args.limit}" + (f"_{suffix}" if suffix else "")
    else:
        stem = "embeddings" + (f".{suffix}" if suffix else "")
    final_path = WORK / f"{stem}.npy"
    partial_path = WORK / f"{stem}.partial.npy"
    meta_path = WORK / (f"embed_meta_{suffix}.json" if suffix else "embed_meta.json")
    if args.limit:
        meta_path = WORK / (f"embed_test_meta_{args.limit}" + (f"_{suffix}.json" if suffix else ".json"))

    if final_path.exists():
        try:
            existing = np.load(final_path, mmap_mode="r")
            if existing.shape == (total, dim):
                log(f"already complete: {final_path} shape={existing.shape}")
                return
        except Exception:
            pass

    count = 0
    embeddings = np.empty((total, dim), dtype=np.float32)
    if partial_path.exists():
        compatible = True
        if meta_path.exists():
            try:
                previous_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                compatible = (
                    previous_meta.get("model") == MODEL_NAME
                    and int(previous_meta.get("dimension", dim)) == dim
                    and int(previous_meta.get("max_seq_length", model.max_seq_length)) == model.max_seq_length
                )
            except Exception:
                compatible = False
        if compatible:
            try:
                previous = np.load(partial_path)
                if previous.ndim == 2 and previous.shape[1] == dim and previous.shape[0] <= total:
                    count = int(previous.shape[0])
                    embeddings[:count] = previous
                    log(f"resuming at {count}")
            except Exception as exc:
                log(f"ignoring unreadable checkpoint: {exc}")
        else:
            log("checkpoint settings differ; starting a fresh embedding run")

    started = time.time()
    while count < total:
        end = min(count + CHECKPOINT, total)
        chunk = frame.iloc[count:end]
        batch_texts = []
        for text, language in zip(chunk["text"].astype(str), chunk["language"].astype(str)):
            limit = MAX_ZH_CHARS if language.startswith("zh") else MAX_EN_CHARS
            batch_texts.append("passage: " + text[:limit])
        vectors = model.encode(
            batch_texts,
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).astype(np.float32)
        embeddings[count:end] = vectors
        count = end
        tmp = partial_path.with_suffix(".tmp.npy")
        np.save(tmp, embeddings[:count])
        tmp.replace(partial_path)
        elapsed = time.time() - started
        rate = count / elapsed if elapsed else 0
        remaining = (total - count) / rate if rate else 0
        log(f"{count}/{total} ({rate:.1f}/s, eta {remaining/60:.1f} min)")
        write_json(
            meta_path,
            {
                "model": MODEL_NAME,
                "dimension": dim,
                "count": count,
                "total": total,
                "max_en_chars": MAX_EN_CHARS,
                "max_zh_chars": MAX_ZH_CHARS,
                "max_seq_length": model.max_seq_length,
                "batch_size": BATCH_SIZE,
                "updated_at": now_iso(),
            },
        )

    np.save(final_path, embeddings)
    if partial_path.exists():
        partial_path.unlink()
    write_json(
        meta_path,
        {
            "model": MODEL_NAME,
            "dimension": dim,
            "count": total,
            "total": total,
            "max_en_chars": MAX_EN_CHARS,
            "max_zh_chars": MAX_ZH_CHARS,
            "max_seq_length": model.max_seq_length,
            "batch_size": BATCH_SIZE,
            "elapsed_seconds": round(time.time() - started, 1),
            "updated_at": now_iso(),
        },
    )
    log(f"done: {final_path} shape={embeddings.shape}")


if __name__ == "__main__":
    main()
