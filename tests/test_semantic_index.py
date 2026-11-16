import json
import struct
from pathlib import Path

from hk_criminal_law_mcp.semantic_index import SemanticMapIndex


def _write_fixture(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    overview = {
        "points": 3,
        "documents": 1,
        "clusters": 2,
        "noise": 0,
        "model": "test-model",
        "embedding_dimension": 2,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "snapshot": "2026-01-01",
        "meta_chunks": 1,
        "coverage": {"legislation": "test"},
        "clustering": {"method": "kmeans", "clusters": 2},
        "bilingual_alignment": {"enabled": True, "alpha": 0.25},
    }
    clusters = {
        "clusters": [
            {
                "id": 0, "label": "bail", "label_en": "bail", "label_zh": "保釋",
                "size": 2, "color": "#0072B2", "top_caps": [{"cap": "221", "title": "Criminal Procedure Ordinance", "count": 2}],
                "top_terms_en": ["bail"], "top_terms_zh": ["保釋"],
            },
            {
                "id": 1, "label": "interpretation", "label_en": "interpretation", "label_zh": "釋義",
                "size": 1, "color": "#D55E00", "top_caps": [{"cap": "1", "title": "Interpretation and General Clauses Ordinance", "count": 1}],
                "top_terms_en": ["interpretation"], "top_terms_zh": ["釋義"],
            },
        ]
    }
    meta = {
        "i": [0, 1, 2],
        "c": ["221", "221", "1"],
        "s": ["9J", "9J", "1"],
        "h": ["Review of bail", "覆核保釋", "Short title"],
        "l": ["en", "zh-Hant", "en"],
        "cl": [0, 0, 1],
        "d": ["Criminal Procedure Ordinance", "刑事訴訟程序條例", "Interpretation and General Clauses Ordinance"],
        "v": ["2026-01-01", "2026-01-01", "2026-01-01"],
        "p": ["Bail", "保釋", ""],
        "k": ["s9J", "s9J", "s1"],
        "sn": ["A person may apply for bail review.", "任何人可申請覆核保釋。", "This Ordinance may be cited."],
    }
    (root / "overview.json").write_text(json.dumps(overview), encoding="utf-8")
    (root / "clusters.json").write_text(json.dumps(clusters), encoding="utf-8")
    (root / "meta-0.json").write_text(json.dumps(meta), encoding="utf-8")
    (root / "points.bin").write_bytes(struct.pack("<6f", -0.5, 0.0, 0.0, 0.5, 0.5, -0.5))
    rows = [
        [1, 2, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [0, 2, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [0, 1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
    ]
    (root / "knn.bin").write_bytes(b"".join(struct.pack("<12i", *row) for row in rows))


def test_semantic_index_search_locate_and_neighbors(tmp_path):
    _write_fixture(tmp_path)
    index = SemanticMapIndex(tmp_path)
    assert index.available
    assert index.status()["points"] == 3
    assert index.status()["clusters"] == 2

    result = index.search("bail", limit=5)
    assert result["found"] is True
    assert result["count"] == 1
    assert {item["citation"] for item in result["results"]} == {"Cap. 221 s.9J"}

    located = index.locate("Cap. 221 s.9J")
    assert located["found"] is True
    assert located["matches"][0]["citation"] == "Cap. 221 s.9J"
    assert located["matches"][0]["cluster"]["id"] == 0

    neighbours = index.neighbors(citation="Cap. 221 s.9J", limit=2)
    assert neighbours["found"] is True
    assert len(neighbours["neighbours"]) == 2

    clusters = index.clusters_list()
    assert clusters["count"] == 2
    assert clusters["clusters"][0]["id"] == 0

    one = index.cluster(0, limit=1)
    assert one["found"] is True
    assert one["members_count"] == 2
    assert len(one["members"]) == 1


def test_semantic_index_reports_missing_data(tmp_path):
    try:
        SemanticMapIndex(tmp_path / "missing")
    except Exception as exc:
        assert "semantic atlas data not found" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected missing atlas data to raise")
