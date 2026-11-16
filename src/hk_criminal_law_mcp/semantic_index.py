"""Read-only, agent-friendly index over the generated semantic atlas.

The atlas is a static visualisation; this module exposes its points, clusters,
and nearest-neighbour graph to the MCP server without requiring numpy. It is a
discovery aid: agents must verify every result with ``get_section``,
``verify_citation``, or ``verify_citations`` before relying on it.
"""
from __future__ import annotations

import json
import math
import re
import sys
from array import array
from pathlib import Path

from .citations import (
    normalise_cap,
    normalise_section,
    parse_case_citation,
    parse_legislation_citation,
)
from .config import semantic_map_dir

NEIGHBOURS = 12


class SemanticMapUnavailable(RuntimeError):
    """Raised when the generated atlas data cannot be loaded."""


def _normalise(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^\w\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class SemanticMapIndex:
    """Load the generated atlas data into compact Python arrays."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else semantic_map_dir()
        self.available = False
        self.error: str | None = None
        self._load()

    def _load(self) -> None:
        data = self.data_dir
        required = ["overview.json", "clusters.json", "points.bin", "knn.bin"]
        missing = [name for name in required if not (data / name).exists()]
        if missing:
            raise SemanticMapUnavailable(
                f"semantic atlas data not found in {data}: {', '.join(missing)}. "
                "Build it with `make map-all` or set HK_LAW_SEMANTIC_MAP."
            )

        self.overview = json.loads((data / "overview.json").read_text(encoding="utf-8"))
        cluster_payload = json.loads((data / "clusters.json").read_text(encoding="utf-8"))
        self.cluster_list = cluster_payload.get("clusters", [])
        self.clusters = {int(c["id"]): c for c in self.cluster_list}

        chunks = max(1, int(self.overview.get("meta_chunks", 1)))
        meta: dict[str, list] = {}
        for chunk_index in range(chunks):
            path = data / f"meta-{chunk_index}.json"
            if not path.exists() and chunk_index == 0 and (data / "meta.json").exists():
                path = data / "meta.json"
            if not path.exists():
                raise SemanticMapUnavailable(f"missing atlas metadata chunk: {path}")
            part = json.loads(path.read_text(encoding="utf-8"))
            if not meta:
                meta = {key: [] for key in part}
            for key, values in part.items():
                meta.setdefault(key, []).extend(values)
        self.meta = meta
        self.n = len(meta.get("i", []))
        if not self.n:
            raise SemanticMapUnavailable("atlas metadata contains no points")

        self.points = array("f")
        with (data / "points.bin").open("rb") as handle:
            self.points.fromfile(handle, self.n * 2)
        if sys.byteorder != "little":
            self.points.byteswap()
        if len(self.points) != self.n * 2:
            raise SemanticMapUnavailable("points.bin does not match the atlas metadata")

        self.knn = array("i")
        with (data / "knn.bin").open("rb") as handle:
            self.knn.fromfile(handle, self.n * NEIGHBOURS)
        if sys.byteorder != "little":
            self.knn.byteswap()
        if len(self.knn) != self.n * NEIGHBOURS:
            raise SemanticMapUnavailable("knn.bin does not match the atlas metadata")

        self.search_text: list[str] = []
        self.citation_index: dict[tuple[str, str, str], list[int]] = {}
        for point_id in range(self.n):
            cap = str(meta["c"][point_id])
            section = str(meta["s"][point_id])
            language = str(meta["l"][point_id])
            key = (normalise_cap(cap), normalise_section(section).upper(), language)
            self.citation_index.setdefault(key, []).append(point_id)
            self.search_text.append(
                _normalise(
                    f"{meta['h'][point_id]} {meta['d'][point_id]} "
                    f"cap {cap} s {section} {meta['sn'][point_id]}"
                )
            )
        self.available = True

    def _citation_of(self, point_id: int) -> str:
        cap = self.meta["c"][point_id]
        section = str(self.meta["s"][point_id] or "")
        if section.lower().startswith("sch"):
            return f"Cap. {cap} Sch. {section[3:]}"
        if not section or section == "document":
            return f"Cap. {cap}"
        return f"Cap. {cap} s.{section}"

    def _source_url(self, point_id: int) -> str:
        cap = self.meta["c"][point_id]
        language = self.meta["l"][point_id]
        return f"https://www.elegislation.gov.hk/hk/{cap}!{'en' if language == 'en' else 'zh-Hant'}"

    def _cluster_of(self, point_id: int) -> dict:
        cluster_id = int(self.meta["cl"][point_id])
        cluster = self.clusters.get(cluster_id)
        if not cluster:
            return {"id": cluster_id, "label": "Unclustered", "label_zh": "未分群", "color": "#9ca3af", "provisional": True}
        return {
            "id": cluster_id,
            "label": cluster.get("label_en") or cluster.get("label"),
            "label_zh": cluster.get("label_zh"),
            "color": cluster.get("color"),
            "provisional": True,
        }

    def _point(self, point_id: int, rank: int | None = None) -> dict:
        payload = {
            "point_id": point_id,
            "citation": self._citation_of(point_id),
            "cap": self.meta["c"][point_id],
            "section": self.meta["s"][point_id],
            "heading": self.meta["h"][point_id],
            "language": self.meta["l"][point_id],
            "document_title": self.meta["d"][point_id],
            "version_date": self.meta["v"][point_id],
            "part": self.meta["p"][point_id],
            "cluster": self._cluster_of(point_id),
            "source_url": self._source_url(point_id),
            "snippet": self.meta["sn"][point_id],
        }
        if rank is not None:
            payload["semantic_rank"] = rank
        return payload

    def status(self) -> dict:
        return {
            "available": True,
            "points": self.n,
            "documents": self.overview.get("documents"),
            "clusters": len([c for c in self.cluster_list if int(c["id"]) >= 0]),
            "noise": self.overview.get("noise", 0),
            "model": self.overview.get("model"),
            "embedding_dimension": self.overview.get("embedding_dimension"),
            "generated_at": self.overview.get("generated_at"),
            "snapshot": self.overview.get("snapshot"),
            "clustering": self.overview.get("clustering"),
            "bilingual_alignment": self.overview.get("bilingual_alignment"),
            "coverage": self.overview.get("coverage"),
            "data_dir": str(self.data_dir),
            "warning": (
                "Semantic atlas is a discovery aid. Proximity and cluster labels "
                "are not legal authority, treatment, or hierarchy."
            ),
        }

    def search(
        self,
        query: str,
        limit: int = 10,
        cluster: int | str | None = None,
        language: str | None = None,
    ) -> dict:
        tokens = _normalise(query).split(" ")
        tokens = [token for token in tokens if token]
        if not tokens:
            return {"found": False, "error": "query must contain at least one word"}
        cluster_id = None
        cluster_text = None
        if cluster is not None and cluster != "":
            try:
                cluster_id = int(cluster)
            except (TypeError, ValueError):
                cluster_text = _normalise(cluster)
        language = language if language in {"en", "zh-Hant"} else None
        matches: list[tuple[int, int]] = []
        for point_id in range(self.n):
            if language and self.meta["l"][point_id] != language:
                continue
            if cluster_id is not None and int(self.meta["cl"][point_id]) != cluster_id:
                continue
            if cluster_text:
                cluster_payload = self._cluster_of(point_id)
                haystack = _normalise(f"{cluster_payload['label']} {cluster_payload['label_zh']}")
                if cluster_text not in haystack:
                    continue
            text = self.search_text[point_id]
            if not all(token in text for token in tokens):
                continue
            heading = _normalise(self.meta["h"][point_id])
            score = sum(2 for token in tokens if token in heading) + len(tokens)
            matches.append((score, point_id))
        matches.sort(key=lambda item: (-item[0], item[1]))
        limit = max(1, min(int(limit), 50))
        results = [self._point(point_id, rank) for rank, (_, point_id) in enumerate(matches[:limit], start=1)]
        return {
            "found": True,
            "query": query,
            "count": len(matches),
            "results": results,
            "warning": (
                "Discovery only. The atlas is a semantic research aid; read the provision "
                "with get_section and verify it with verify_citation before relying on it."
            ),
        }

    def locate(self, citation: str, language: str | None = None) -> dict:
        if parse_case_citation(citation):
            return {
                "found": False,
                "error": "The semantic atlas covers legislation only; use search_cases/get_case for judgments.",
            }
        parsed = parse_legislation_citation(citation)
        if not parsed:
            return {"found": False, "error": "Could not parse a Cap./section citation."}
        cap = normalise_cap(parsed.cap)
        if parsed.schedule:
            section = f"SCH{normalise_section(parsed.schedule)}".upper()
        else:
            section = normalise_section(parsed.section or "").upper()
        languages = [language] if language in {"en", "zh-Hant"} else ["en", "zh-Hant"]
        found: list[dict] = []
        for lang in languages:
            keys = [(cap, section, lang)]
            for key in keys:
                for point_id in self.citation_index.get(key, []):
                    found.append(self._point(point_id))
        if not found:
            # Fall back to a cap-level match when no section was supplied.
            if not section:
                for point_id in range(self.n):
                    if normalise_cap(self.meta["c"][point_id]) == cap:
                        found.append(self._point(point_id))
                        break
        if not found:
            return {"found": False, "citation": citation, "error": "No matching provision in the atlas."}
        return {
            "found": True,
            "citation": citation,
            "count": len(found),
            "matches": found,
            "warning": "Atlas locations are semantic coordinates, not legal authority.",
        }

    def neighbors(
        self,
        point_id: int | None = None,
        citation: str | None = None,
        language: str | None = None,
        limit: int = 10,
    ) -> dict:
        seed_id: int | None = None
        if point_id is not None:
            seed_id = int(point_id)
        elif citation:
            located = self.locate(citation, language=language)
            if located.get("found") and located.get("matches"):
                seed_id = int(located["matches"][0]["point_id"])
        if seed_id is None or not (0 <= seed_id < self.n):
            return {"found": False, "error": "Provide a valid point_id or a legislation citation."}
        limit = max(1, min(int(limit), 50))
        start = seed_id * NEIGHBOURS
        neighbour_ids = []
        seen = {seed_id}
        for index in self.knn[start:start + NEIGHBOURS]:
            if index < 0 or index >= self.n or index in seen:
                continue
            seen.add(index)
            neighbour_ids.append(int(index))
            if len(neighbour_ids) >= limit:
                break
        return {
            "found": True,
            "seed": self._point(seed_id),
            "count": len(neighbour_ids),
            "neighbours": [
                self._point(index, rank)
                for rank, index in enumerate(neighbour_ids, start=1)
            ],
            "warning": (
                "Nearest neighbours are semantic similarity, not authority or treatment. "
                "Verify each provision with get_section and verify_citation."
            ),
        }

    def clusters_list(self, query: str | None = None, limit: int = 50) -> dict:
        needle = _normalise(query) if query else None
        rows = []
        for cluster in self.cluster_list:
            cluster_id = int(cluster["id"])
            if cluster_id < 0:
                continue
            if needle:
                haystack = _normalise(
                    f"{cluster.get('label_en','')} {cluster.get('label_zh','')} "
                    + " ".join(str(c.get("title", "")) for c in cluster.get("top_caps", []))
                )
                if needle not in haystack:
                    continue
            rows.append({
                "id": cluster_id,
                "label": cluster.get("label_en") or cluster.get("label"),
                "label_zh": cluster.get("label_zh"),
                "size": cluster.get("size"),
                "color": cluster.get("color"),
                "top_caps": cluster.get("top_caps", []),
                "top_terms_en": cluster.get("top_terms_en", []),
                "top_terms_zh": cluster.get("top_terms_zh", []),
            })
        rows.sort(key=lambda item: item.get("size") or 0, reverse=True)
        limit = max(1, min(int(limit), 100))
        return {
            "count": len(rows),
            "clusters": rows[:limit],
            "warning": "Cluster labels are generated and provisional, not a legal taxonomy.",
        }

    def cluster(self, cluster_id: int, limit: int = 20) -> dict:
        cluster_id = int(cluster_id)
        cluster = self.clusters.get(cluster_id)
        if not cluster or cluster_id < 0:
            return {"found": False, "error": f"Unknown cluster id: {cluster_id}"}
        members = [
            point_id for point_id in range(self.n)
            if int(self.meta["cl"][point_id]) == cluster_id
        ]
        limit = max(1, min(int(limit), 100))
        if len(members) > limit:
            count = len(members)
            cx = sum(self.points[point_id * 2] for point_id in members) / count
            cy = sum(self.points[point_id * 2 + 1] for point_id in members) / count
            members.sort(
                key=lambda point_id: (
                    (self.points[point_id * 2] - cx) ** 2
                    + (self.points[point_id * 2 + 1] - cy) ** 2
                )
            )
        return {
            "found": True,
            "cluster": {
                "id": cluster_id,
                "label": cluster.get("label_en") or cluster.get("label"),
                "label_zh": cluster.get("label_zh"),
                "size": cluster.get("size"),
                "color": cluster.get("color"),
                "top_caps": cluster.get("top_caps", []),
                "top_terms_en": cluster.get("top_terms_en", []),
                "top_terms_zh": cluster.get("top_terms_zh", []),
            },
            "members_count": len(members),
            "members": [self._point(point_id, rank) for rank, point_id in enumerate(members[:limit], start=1)],
            "warning": "Representative members are closest to the cluster centroid; verify each provision.",
        }


_INDEX: SemanticMapIndex | None = None
_INDEX_ERROR: str | None = None


def get_index() -> SemanticMapIndex | None:
    """Return the cached atlas index, reloading if it was previously unavailable."""
    global _INDEX, _INDEX_ERROR
    if _INDEX is not None and _INDEX.available:
        return _INDEX
    try:
        _INDEX = SemanticMapIndex()
        _INDEX_ERROR = None
    except Exception as exc:  # noqa: BLE001 - exposed to the MCP caller
        _INDEX = None
        _INDEX_ERROR = str(exc)
    return _INDEX


def index_error() -> str | None:
    return _INDEX_ERROR
