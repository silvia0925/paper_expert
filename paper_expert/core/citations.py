"""Citation graph traversal and related paper discovery.

Provides citation chain traversal (BFS to configurable depth) and
identification of papers in the citation graph that are not yet in the library.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from paper_expert.core.database import Database

logger = logging.getLogger(__name__)


def get_citation_summary(db: Database, paper_id: int) -> dict[str, Any]:
    """Get a complete citation summary for a paper.

    Returns:
        Dict with 'references' (outgoing), 'citations' (incoming),
        each paper marked with 'in_library' status.
    """
    references = db.get_references(paper_id)
    citations = db.get_citations(paper_id)

    return {
        "references": [
            {**r, "in_library": r["state"] != "metadata-only" or r["pdf_path"] is not None}
            for r in references
        ],
        "citations": [
            {**c, "in_library": c["state"] != "metadata-only" or c["pdf_path"] is not None}
            for c in citations
        ],
        "reference_count": len(references),
        "citation_count": len(citations),
    }


def traverse_citations(
    db: Database,
    paper_id: int,
    depth: int = 2,
    direction: str = "both",
) -> dict[int, list[dict[str, Any]]]:
    """Traverse the citation graph via BFS up to a given depth.

    Args:
        db: Database instance.
        paper_id: Starting paper.
        depth: Max hops from the starting paper.
        direction: "references" (outgoing), "citations" (incoming), or "both".

    Returns:
        Dict mapping hop distance (1, 2, ...) to list of paper dicts found at that distance.
    """
    visited: set[int] = {paper_id}
    queue: deque[tuple[int, int]] = deque()  # (paper_id, current_depth)
    queue.append((paper_id, 0))

    by_depth: dict[int, list[dict[str, Any]]] = {}

    while queue:
        current_id, current_depth = queue.popleft()
        if current_depth >= depth:
            continue

        neighbors: list[dict[str, Any]] = []
        if direction in ("references", "both"):
            neighbors.extend(db.get_references(current_id))
        if direction in ("citations", "both"):
            neighbors.extend(db.get_citations(current_id))

        next_depth = current_depth + 1
        for neighbor in neighbors:
            nid = neighbor["id"]
            if nid in visited:
                continue
            visited.add(nid)

            if next_depth not in by_depth:
                by_depth[next_depth] = []
            by_depth[next_depth].append(neighbor)

            queue.append((nid, next_depth))

    return by_depth


def discover_missing_papers(db: Database, paper_id: int) -> list[dict[str, Any]]:
    """Find papers in the citation graph of a paper that are metadata-only
    (i.e., not yet fully in the library).

    Returns list of metadata-only paper dicts with potential for full acquisition.
    """
    references = db.get_references(paper_id)
    citations = db.get_citations(paper_id)

    all_related = references + citations
    missing = [
        p for p in all_related
        if p["state"] == "metadata-only" and p["pdf_path"] is None
    ]

    # Deduplicate
    seen: set[int] = set()
    unique: list[dict[str, Any]] = []
    for p in missing:
        if p["id"] not in seen:
            seen.add(p["id"])
            unique.append(p)

    return unique
