"""Controlled vocabulary manager.

Manages the mapping of synonym variations to canonical terms
for consistent L1 tag classification. No hardcoded defaults --
all vocabulary is user-defined via DomainConfig.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from paper_expert.core.database import Database
from paper_expert.core.domain import DomainConfig

logger = logging.getLogger(__name__)


def init_vocabulary(
    db: Database,
    vocab_path: Path | None = None,
    domain_config: DomainConfig | None = None,
) -> int:
    """Initialize the vocabulary in the database.

    Priority: domain_config.l1_vocabulary > YAML file > empty.
    Returns the number of entries added.
    """
    vocab: dict[str, list[str]]

    if domain_config and domain_config.l1_vocabulary:
        vocab = domain_config.l1_vocabulary
    elif vocab_path and vocab_path.exists():
        with open(vocab_path, encoding="utf-8") as f:
            vocab = yaml.safe_load(f) or {}
    else:
        vocab = {}  # No defaults -- starts empty

    count = 0
    for canonical, aliases in vocab.items():
        db.add_vocabulary(canonical, aliases)
        count += 1

    logger.info("Initialized vocabulary with %d entries", count)
    return count


def export_vocabulary(db: Database, vocab_path: Path) -> None:
    """Export the current vocabulary to a YAML file."""
    entries = db.get_vocabulary()
    vocab: dict[str, list[str]] = {}
    for entry in entries:
        aliases = json.loads(entry["aliases_json"])
        vocab[entry["canonical"]] = aliases

    vocab_path.parent.mkdir(parents=True, exist_ok=True)
    with open(vocab_path, "w", encoding="utf-8") as f:
        yaml.dump(vocab, f, allow_unicode=True, default_flow_style=False, sort_keys=True)

    logger.info("Exported vocabulary to %s", vocab_path)


def check_suggested_tags(db: Database, threshold: int = 3) -> list[dict[str, Any]]:
    """Check for suggested tags that have reached the promotion threshold.

    Returns list of {tag, count} dicts for tags with count >= threshold.
    """
    suggestions = db.get_suggested_tag_counts()
    return [s for s in suggestions if s["count"] >= threshold]
