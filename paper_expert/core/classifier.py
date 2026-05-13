"""Paper classification system.

Three-tier classification (all user-defined, no hardcoded domains):
- L0: Keyword-based domain classification using user-defined keyword groups
- L1: LLM-based sub-topic classification with user-defined vocabulary normalization
- L2: Free-form user tags (managed via CLI)
"""

from __future__ import annotations

import json
import logging

import httpx

from paper_expert.core.database import Database
from paper_expert.core.domain import DomainConfig, build_l1_prompt
from paper_expert.models.paper import ClassificationResult, PaperMetadata, Tag, TagLevel

logger = logging.getLogger(__name__)


def classify_l0(
    title: str,
    abstract: str | None = None,
    domain_config: DomainConfig | None = None,
) -> list[str]:
    """Classify paper into L0 domains using user-defined keyword groups."""
    if not domain_config or not domain_config.l0_keywords:
        return ["Other"]

    text = (title + " " + (abstract or "")).lower()

    matched_domains: list[str] = []
    for domain_name, keywords in domain_config.l0_keywords.items():
        if any(kw.lower() in text for kw in keywords):
            matched_domains.append(domain_name)

    if len(matched_domains) >= 2:
        return ["Cross-domain"]
    if matched_domains:
        return matched_domains
    return ["Other"]


async def classify_l1_llm(
    title: str,
    abstract: str | None,
    domain_config: DomainConfig | None = None,
    ollama_model: str = "qwen2.5",
    ollama_url: str = "http://localhost:11434",
) -> list[str]:
    """Classify paper into L1 sub-topics using local Ollama LLM."""
    if domain_config and domain_config.l1_prompt_template:
        prompt = build_l1_prompt(domain_config, title, abstract)
    else:
        prompt = (
            "You are an academic paper classifier.\n"
            "Given a paper's title and abstract, classify it into 1-3 sub-topic tags.\n"
            "Respond ONLY with a JSON array of tag strings.\n\n"
            f"Title: {title}\n"
            f"Abstract: {abstract or 'No abstract available.'}"
        )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("response", "")
            tags = json.loads(response_text)
            if isinstance(tags, list):
                return [str(t) for t in tags if t]
            return []
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Ollama classification failed: %s", e)
        return []


def normalize_l1_tags(
    raw_tags: list[str], db: Database
) -> tuple[list[str], list[str]]:
    """Normalize raw L1 tags against the controlled vocabulary."""
    normalized: list[str] = []
    unrecognized: list[str] = []
    for raw in raw_tags:
        canonical = db.normalize_tag(raw)
        if canonical:
            normalized.append(canonical)
        else:
            unrecognized.append(raw)
    return normalized, unrecognized


def classify_paper(
    db: Database,
    paper_id: int,
    metadata: PaperMetadata,
    domain_config: DomainConfig | None = None,
) -> ClassificationResult:
    """Run synchronous L0 keyword classification."""
    l0_tags = classify_l0(metadata.title, metadata.abstract, domain_config)
    for tag in l0_tags:
        db.add_tag(paper_id, TagLevel.L0.value, tag)
    return ClassificationResult(l0_tags=l0_tags)


async def classify_paper_full(
    db: Database,
    paper_id: int,
    metadata: PaperMetadata,
    domain_config: DomainConfig | None = None,
    ollama_model: str = "qwen2.5",
) -> ClassificationResult:
    """Run full classification: L0 keyword + L1 LLM."""
    l0_tags = classify_l0(metadata.title, metadata.abstract, domain_config)
    for tag in l0_tags:
        db.add_tag(paper_id, TagLevel.L0.value, tag)

    raw_l1 = await classify_l1_llm(
        metadata.title, metadata.abstract, domain_config, ollama_model
    )
    normalized, unrecognized = normalize_l1_tags(raw_l1, db)

    l1_tags: list[Tag] = []
    for tag in normalized:
        db.add_tag(paper_id, TagLevel.L1.value, tag, confidence=0.8)
        l1_tags.append(Tag(level=TagLevel.L1, tag=tag, confidence=0.8))
    for tag in unrecognized:
        db.add_tag(paper_id, TagLevel.L1.value, tag, suggested=True)
        l1_tags.append(Tag(level=TagLevel.L1, tag=tag, suggested=True))

    return ClassificationResult(
        l0_tags=l0_tags,
        l1_tags=l1_tags,
        raw_l1_output=json.dumps(raw_l1),
    )


async def batch_classify(
    db: Database,
    domain_config: DomainConfig | None = None,
    ollama_model: str = "qwen2.5",
) -> int:
    """Classify all papers that have no L1 tags."""
    untagged_ids = db.get_untagged_paper_ids(level="L1")
    classified = 0
    for paper_id in untagged_ids:
        paper_row = db.get_paper(paper_id)
        if not paper_row:
            continue
        metadata = PaperMetadata(
            title=paper_row["title"],
            abstract=paper_row.get("abstract"),
        )
        try:
            await classify_paper_full(db, paper_id, metadata, domain_config, ollama_model)
            classified += 1
        except Exception:
            logger.warning("Failed to classify paper %d", paper_id, exc_info=True)
    return classified
