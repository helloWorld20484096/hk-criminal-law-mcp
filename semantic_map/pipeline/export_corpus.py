"""Export current legislation sections and deduplicated embedding texts."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from .common import DATA, DB_PATH, WORK, now_iso, write_json

SQL = """
SELECT s.id, s.cap, s.doc_type, s.section_key, s.section_no, s.heading, s.text,
       s.part, s.division, s.language, s.version_date, s.source_url,
       d.title AS doc_title, d.long_title
FROM legislation_sections s
JOIN legislation_docs d ON d.id = s.doc_id
ORDER BY s.cap, s.section_no, s.language, s.id
"""


def clean(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def embedding_text(row: dict) -> str:
    parts = [
        clean(row.get("doc_title")),
        clean(row.get("heading")),
        clean(row.get("part")),
        clean(row.get("text")),
    ]
    text = "\n".join(part for part in parts if part)
    return text[:6000]


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"missing corpus database: {DB_PATH}")

    con = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(SQL, con)
    finally:
        con.close()

    df = df.fillna("")
    df["heading"] = df["heading"].map(clean)
    df["text"] = df["text"].map(clean)
    df["cap"] = df["cap"].astype(str)
    df["section_no"] = df["section_no"].astype(str)
    df["point_id"] = range(len(df))

    prepared: list[str] = []
    hashes: list[str] = []
    for row in df.to_dict("records"):
        text = embedding_text(row)
        prepared.append(text)
        hashes.append(hashlib.sha1(text.encode("utf-8")).hexdigest())

    df["text_hash"] = hashes
    df["embedding_text"] = prepared

    unique = (
        df.drop_duplicates("text_hash", keep="first")[["text_hash", "embedding_text", "language"]]
        .reset_index(drop=True)
        .rename(columns={"embedding_text": "text"})
    )
    unique["text_id"] = range(len(unique))
    lookup = dict(zip(unique["text_hash"], unique["text_id"]))
    df["text_id"] = df["text_hash"].map(lookup).astype("int64")

    columns = [
        "point_id", "text_id", "id", "cap", "doc_type", "section_key", "section_no",
        "heading", "text", "part", "division", "language", "version_date",
        "source_url", "doc_title", "long_title",
    ]
    sections = df[columns].copy()
    sections.to_parquet(WORK / "sections.parquet", index=False, compression="zstd")
    unique.to_parquet(WORK / "texts.parquet", index=False, compression="zstd")
    df[["point_id", "text_hash", "embedding_text"]].to_parquet(
        WORK / "embedding_texts.parquet", index=False, compression="zstd"
    )

    stats = {
        "generated_at": now_iso(),
        "sections": int(len(sections)),
        "unique_texts": int(len(unique)),
        "documents": int(sections["cap"].nunique()),
        "languages": sections["language"].value_counts().to_dict(),
        "duplicate_texts": int(len(sections) - len(unique)),
        "average_text_chars": float(sections["text"].str.len().mean()),
        "max_text_chars": int(sections["text"].str.len().max()),
    }
    write_json(DATA / "export_stats.json", stats)
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
