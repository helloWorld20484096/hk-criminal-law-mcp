"""Generate readable bilingual labels for HDBSCAN clusters."""
from __future__ import annotations

import argparse
import colorsys
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer

from .common import WORK, now_iso, write_json

EN_STOP = {
    "section", "sections", "subsection", "subsections", "paragraph", "paragraphs",
    "ordinance", "ordinances", "regulation", "regulations", "schedule", "schedules",
    "cap", "hong", "kong", "shall", "may", "person", "persons", "unless", "otherwise",
    "including", "means", "deemed", "specified", "prescribed", "notice", "application",
    "made", "make", "under", "within", "without", "thereof", "therein", "hereto",
    "herein", "aforesaid", "where", "which", "this", "that", "with", "from", "have",
    "been", "such", "other", "any", "all", "and", "the", "for", "not", "are", "was",
    "has", "had", "its", "his", "her", "their", "they", "who", "whom", "would",
    "could", "should", "also", "only", "time", "date", "day", "days", "year", "years",
    "number", "part", "division", "item", "items", "matter", "matters", "case", "cases",
    "legislation", "subsidiary", "subordinate", "instrument", "instruments", "chapter",
    "chapters", "provision", "provisions", "principal", "general", "miscellaneous",
    "short", "title", "citation", "commencement", "interpretation", "sub", "leg",
    "ch", "appendix", "index", "schedule",
}

ZH_STOP = {
    "條例", "香港", "規定", "任何人", "的人", "本條", "作出", "包括", "有關", "根據",
    "可以", "必須", "政府", "法院", "裁判", "上訴", "法官", "程序", "條文", "附表",
    "以及", "或者", "並且", "但是", "如果", "由於", "對於", "關於", "根據", "按照",
    "本法", "本規例", "本命令", "本附表", "行政", "當局", "人員", "權力", "責任",
    "罪行", "罰款", "監禁", "定罪", "判處", "最高", "不少於", "不超過", "另有",
    "訂明", "指明的", "所指", "該等", "任何", "其他", "以上", "以下", "期間",
    "法例", "附屬", "文書", "一般", "雜項", "主體", "條款", "條文",
    "簡稱", "引稱", "生效", "釋義", "附屬法例", "第",
}

# Okabe-Ito-inspired categorical palette, extended with distinct hues.
PALETTE = [
    "#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9",
    "#8B2E2E", "#6A3D9A", "#1B9E77", "#B15928", "#332288", "#2E86AB",
    "#A6761D", "#117733", "#AA4499", "#44AA99", "#999933", "#882255",
    "#661100", "#6699CC", "#4D4D4D", "#E6AB02", "#7F3C8D", "#11A579",
]


def make_unique_labels(clusters: list[dict]) -> list[dict]:
    """Disambiguate repeated auto-labels using the next distinctive term."""
    used = Counter()
    for cluster in clusters:
        if cluster["id"] >= 0 and cluster.get("label_en"):
            used[cluster["label_en"]] += 1
    for cluster in clusters:
        if cluster["id"] < 0 or not cluster.get("label_en"):
            continue
        label = cluster["label_en"]
        if used[label] <= 1:
            continue
        used[label] -= 1
        base = label.split(" · ")[0]
        candidates = [
            term for term in cluster.get("top_terms_en", [])
            if term.lower() not in EN_STOP and term.lower() not in label.lower()
        ]
        for term in candidates:
            candidate = f"{base} · {term}"
            if used[candidate] == 0:
                cluster["label_en"] = candidate
                used[candidate] += 1
                break
        else:
            cap = (cluster.get("top_caps") or [{}])[0].get("cap")
            if cap:
                candidate = f"{base} · Cap. {cap}"
                cluster["label_en"] = candidate
                used[candidate] += 1
        cluster["label"] = cluster["label_en"] or cluster["label_zh"] or cluster["label"]

    used_zh = Counter()
    for cluster in clusters:
        if cluster["id"] >= 0 and cluster.get("label_zh"):
            used_zh[cluster["label_zh"]] += 1
    for cluster in clusters:
        if cluster["id"] < 0 or not cluster.get("label_zh"):
            continue
        label = cluster["label_zh"]
        if used_zh[label] <= 1:
            continue
        used_zh[label] -= 1
        base = label.split(" · ")[0]
        candidates = [
            term for term in cluster.get("top_terms_zh", [])
            if term not in ZH_STOP and term not in label
        ]
        for term in candidates:
            candidate = f"{base} · {term}"
            if used_zh[candidate] == 0:
                cluster["label_zh"] = candidate
                used_zh[candidate] += 1
                break
        else:
            cap = (cluster.get("top_caps") or [{}])[0].get("cap")
            if cap:
                candidate = f"{base} · 第{cap}章"
                cluster["label_zh"] = candidate
                used_zh[candidate] += 1
        if not cluster.get("label_en"):
            cluster["label"] = cluster["label_zh"] or cluster["label"]
    return clusters


def color_for(index: int) -> str:
    if index < len(PALETTE):
        return PALETTE[index]
    hue = ((index * 137.508) % 360) / 360.0
    red, green, blue = colorsys.hls_to_rgb(hue, 0.42, 0.58)
    return "#{:02X}{:02X}{:02X}".format(
        round(red * 255), round(green * 255), round(blue * 255)
    )


def top_terms(docs: list[str], language: str, top_n: int = 6) -> list[str]:
    nonempty = [(i, d) for i, d in enumerate(docs) if d.strip()]
    if not nonempty:
        return []
    rows = [i for i, _ in nonempty]
    texts = [d[:24000] for _, d in nonempty]
    if language == "en":
        vectorizer = CountVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=6000,
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]{2,}\b",
            lowercase=True,
        )
    else:
        vectorizer = CountVectorizer(
            analyzer="char",
            ngram_range=(2, 3),
            max_features=6000,
            lowercase=False,
        )
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return []
    vocabulary = vectorizer.get_feature_names_out()
    matrix = matrix.tocsr()
    totals = np.asarray(matrix.sum(axis=1)).ravel()
    totals[totals == 0] = 1
    tf = matrix.multiply(1 / totals[:, None]).tocsr()
    df = np.asarray((matrix > 0).sum(axis=0)).ravel()
    idf = np.log((1 + len(texts)) / (1 + df)) + 1
    scores = tf.multiply(idf[None, :]).tocsr()
    out: list[tuple[str, float]] = []
    for row, cluster_index in enumerate(rows):
        start, end = scores.indptr[row], scores.indptr[row + 1]
        if start == end:
            continue
        terms = scores.indices[start:end]
        values = scores.data[start:end]
        order = np.argsort(values)[::-1]
        picked = []
        for pos in order:
            term = str(vocabulary[terms[pos]]).strip().lower()
            if not term or term in (EN_STOP if language == "en" else ZH_STOP):
                continue
            if language == "en":
                if not re.fullmatch(r"[a-z][a-z\- ]{2,}", term):
                    continue
                if any(word in EN_STOP for word in term.split()):
                    continue
            else:
                if not re.fullmatch(r"[\u4e00-\u9fff]{2,6}", term):
                    continue
                if any(stop in term for stop in ZH_STOP):
                    continue
            if any(term == existing or term in existing or existing in term for existing in picked):
                continue
            picked.append(term)
            if len(picked) >= top_n:
                break
        out.append((language, picked))  # type: ignore[arg-type]
    # Flatten while retaining order; only one row is expected for a cluster.
    terms: list[str] = []
    for _, picked in out:
        for term in picked:
            if term not in terms:
                terms.append(term)
    return terms[:top_n]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suffix", default="")
    args = parser.parse_args()
    suffix = f"_{args.suffix}" if args.suffix else ""
    frame = pd.read_parquet(WORK / f"sections_reduced{suffix}.parquet")
    labels = np.load(WORK / f"clusters{suffix}.npy")
    if len(frame) != len(labels):
        raise SystemExit("cluster labels do not match section rows")

    cap_titles = {}
    for row in frame[["cap", "language", "doc_title"]].drop_duplicates().to_dict("records"):
        entry = cap_titles.setdefault(str(row["cap"]), {"en": "", "zh": ""})
        title = str(row.get("doc_title") or "").strip()
        if not title:
            continue
        if str(row.get("language")) == "en":
            entry["en"] = entry["en"] or title
        else:
            entry["zh"] = entry["zh"] or title

    clusters = []
    for cluster_id in sorted(set(int(v) for v in labels)):
        if cluster_id < 0:
            clusters.append({
                "id": -1,
                "label": "Unclustered",
                "label_en": "Unclustered",
                "label_zh": "未分群",
                "size": int((labels == -1).sum()),
                "color": "#9ca3af",
                "top_caps": [],
                "top_terms_en": [],
                "top_terms_zh": [],
            })
            continue
        mask = labels == cluster_id
        rows = frame[mask]
        sample = rows.sample(min(len(rows), 400), random_state=42) if len(rows) > 400 else rows

        en_docs: list[str] = []
        zh_docs: list[str] = []
        for row in sample.to_dict("records"):
            text = f"{row.get('heading','')} {row.get('text','')[:1200]}"
            if str(row.get("language")) == "en":
                en_docs.append(text)
            else:
                zh_docs.append(text)
        en_terms = top_terms(["\n".join(en_docs)], "en")
        zh_terms = top_terms(["\n".join(zh_docs)], "zh")

        cap_counts = Counter((str(r["cap"]), str(r.get("doc_title") or "")) for r in rows.to_dict("records"))
        top_caps = [
            {"cap": cap, "title": title, "count": count}
            for (cap, title), count in cap_counts.most_common(3)
        ]
        label_en = " · ".join(en_terms[:2]) if en_terms else ""
        label_zh = " · ".join(zh_terms[:2]) if zh_terms else ""
        if not label_en and top_caps:
            top_cap = top_caps[0]["cap"]
            label_en = cap_titles.get(top_cap, {}).get("en") or top_caps[0]["title"] or f"Cap. {top_cap}"
        if not label_zh and top_caps:
            top_cap = top_caps[0]["cap"]
            label_zh = cap_titles.get(top_cap, {}).get("zh") or top_caps[0]["title"] or f"第 {top_cap} 章"
        label = label_en or label_zh or f"Cluster {cluster_id}"
        clusters.append({
            "id": cluster_id,
            "label": label,
            "label_en": label_en,
            "label_zh": label_zh,
            "size": int(mask.sum()),
            "color": color_for(cluster_id),
            "top_caps": top_caps,
            "top_terms_en": en_terms,
            "top_terms_zh": zh_terms,
        })

    clusters = make_unique_labels(clusters)
    payload = {
        "generated_at": now_iso(),
        "clusters": clusters,
    }
    write_json(WORK / f"cluster_labels{suffix}.json", payload)
    print(f"labeled {len([c for c in clusters if c['id'] >= 0])} clusters")
    for cluster in clusters[:12]:
        print(cluster["id"], cluster["size"], cluster["label"], "|", cluster["label_zh"])


if __name__ == "__main__":
    main()
