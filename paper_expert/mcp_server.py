"""Paper Expert MCP Server.

Exposes paper_expert's paper management, QA, and review capabilities as MCP tools
for use in OpenCode, Claude Desktop, or any MCP-compatible client.

Run: python -m paper_expert.mcp_server
Or:  python paper_expert/mcp_server.py
"""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Ensure paper_expert package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library

logger = logging.getLogger(__name__)

mcp = FastMCP("Paper Expert")

# Global library instance (initialized lazily)
_library: Library | None = None


def _get_library() -> Library:
    global _library
    if _library is None:
        config = PaperExpertConfig.load()
        _library = Library(config)
    return _library


async def _close_library() -> None:
    global _library
    if _library is not None:
        await _library.close()
        _library = None


# ── Search & Discovery ────────────────────────────────────


@mcp.tool()
async def search_papers(
    query: str,
    limit: int = 10,
    year: str | None = None,
    source: str | None = None,
) -> str:
    """Search for academic papers across Semantic Scholar, OpenAlex, arXiv, and IEEE.

    Args:
        query: Search query (keywords or natural language).
        limit: Max number of results (default 10).
        year: Year filter, e.g. "2024" or "2023-2025".
        source: Specific source: "semantic_scholar", "openalex", "arxiv", "ieee".

    Returns:
        JSON list of papers with title, authors, year, venue, citations, PDF availability.
    """
    lib = _get_library()
    sources = [source] if source else None
    results = await lib.search(query, sources=sources, limit=limit, year=year)

    output = []
    for r in results:
        output.append({
            "title": r.title,
            "authors": r.authors[:3],
            "year": r.year,
            "venue": r.venue,
            "citations": r.citation_count,
            "doi": r.doi,
            "arxiv_id": r.arxiv_id,
            "has_pdf": bool(r.open_access_pdf_url),
            "in_library": r.in_library,
        })

    return json.dumps(output, ensure_ascii=False, indent=2)


@mcp.tool()
async def add_paper(identifier: str) -> str:
    """Add a paper to the knowledge base by identifier.

    Args:
        identifier: Paper identifier - "arxiv:2401.12345", "doi:10.xxx/yyy", or S2 ID.

    Returns:
        Confirmation with paper title, state, and tags.
    """
    lib = _get_library()
    paper = await lib.add_by_identifier(identifier)

    if paper:
        tags = ", ".join(t.tag for t in paper.tags) if paper.tags else "none"
        return (
            f"Added: {paper.title}\n"
            f"State: {paper.state.value}\n"
            f"Tags: {tags}\n"
            f"ID: {paper.id}"
        )
    return f"Failed to add paper: {identifier}"


# ── Knowledge Base Management ────────────────────────────


@mcp.tool()
async def list_papers(
    tag: str | None = None,
    year: int | None = None,
    state: str | None = None,
    sort_by: str = "date_added",
    limit: int = 20,
) -> str:
    """List papers in the knowledge base with optional filters.

    Args:
        tag: Filter by tag (e.g. "OPC", "Bei Yu").
        year: Filter by publication year.
        state: Filter by state: "full-text" or "metadata-only".
        sort_by: Sort field: "date_added", "year", "citation_count", "title".
        limit: Max results (default 20).

    Returns:
        JSON list of papers with id, title, year, citations, state, tags.
    """
    lib = _get_library()
    papers = lib.list_papers(tag=tag, year=year, state=state, sort_by=sort_by, limit=limit)

    output = []
    for p in papers:
        output.append({
            "id": p.id,
            "title": p.title,
            "authors": p.authors[:3],
            "year": p.year,
            "citations": p.citation_count,
            "state": p.state.value,
            "tags": [t.tag for t in p.tags],
        })

    return json.dumps(output, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_paper(paper_id: int) -> str:
    """Get full details of a paper by its ID.

    Args:
        paper_id: The paper's database ID.

    Returns:
        Paper details including title, authors, abstract, venue, tags, and citation info.
    """
    lib = _get_library()
    paper = lib.get_paper(paper_id)
    if not paper:
        return f"Paper {paper_id} not found."

    return json.dumps({
        "id": paper.id,
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "venue": paper.venue,
        "abstract": paper.abstract,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "state": paper.state.value,
        "citations": paper.citation_count,
        "tags": [{"level": t.level.value, "tag": t.tag} for t in paper.tags],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def tag_paper(paper_id: int, tags: str) -> str:
    """Add tags to a paper.

    Args:
        paper_id: The paper's database ID.
        tags: Comma-separated tags to add, e.g. "important, to-read".

    Returns:
        Confirmation with updated tag list.
    """
    lib = _get_library()
    paper = lib.get_paper(paper_id)
    if not paper:
        return f"Paper {paper_id} not found."

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    for tag in tag_list:
        lib.db.add_tag(paper_id, "L2", tag)

    all_tags = lib.db.get_tags(paper_id)
    tag_str = ", ".join(f"[{t['level']}]{t['tag']}" for t in all_tags)
    return f"Tags updated for '{paper.title}':\n{tag_str}"


@mcp.tool()
async def get_stats() -> str:
    """Get knowledge base statistics.

    Returns:
        Summary with paper counts by state, category, year, and storage size.
    """
    lib = _get_library()
    stats = lib.get_stats()
    return json.dumps(stats, ensure_ascii=False, indent=2)


# ── QA & Analysis ────────────────────────────────────────

# Feature -> required config keys mapping
_REQUIRED_KEYS: dict[str, dict[str, list[str]]] = {
    "generate_review": {
        "any_llm": ["api_keys.openai", "llm.local_model"],
    },
    "suggest_directions": {
        "any_llm": ["api_keys.openai", "llm.local_model"],
    },
    "build_expertise": {
        "any_llm": ["api_keys.openai", "llm.local_model"],
    },
    "ask_question": {
        "any_llm": ["api_keys.openai", "llm.local_model"],
    },
}

# All common config keys the agent might need to help users set
_CONFIG_KEY_HELP: dict[str, str] = {
    "api_keys.openai": (
        "OpenAI API key (required for literature review, direction suggestion, "
        "domain expertise, and QA). Get one at https://platform.openai.com/api-keys"
    ),
    "api_keys.semantic_scholar": (
        "Semantic Scholar API key (optional, increases rate limits). "
        "Get one at https://www.semanticscholar.org/product/api"
    ),
    "api_keys.unpaywall_email": (
        "Your email for Unpaywall API (needed for PDF fetching). Free registration."
    ),
    "api_keys.ieee_xplore": (
        "IEEE Xplore API key (optional, enables IEEE search). "
        "Get one at https://developer.ieee.org"
    ),
    "api_keys.anthropic": "Anthropic API key (optional, alternative LLM).",
    "llm.local_model": (
        "Local Ollama model name (e.g. 'qwen2.5', 'llama3'). "
        "Requires Ollama running locally."
    ),
    "llm.cloud_model": (
        "Cloud LLM model (e.g. 'openai/gpt-4o'). Requires api_keys.openai."
    ),
    "llm.api_base": (
        "Custom API base URL if using a proxy (e.g. 'https://api.example.com/v1')."
    ),
    "notify.wechat_webhook": "WeChat Work bot webhook URL for paper monitoring notifications.",
    "notify.feishu_webhook": "Feishu bot webhook URL for paper monitoring notifications.",
    "notify.dingtalk_webhook": "DingTalk bot webhook URL for paper monitoring notifications.",
    "notify.smtp_host": "SMTP server host for email notifications (e.g. smtp.gmail.com).",
    "notify.smtp_port": "SMTP server port (default: 587 for TLS, 465 for SSL).",
    "notify.smtp_username": "SMTP login username (usually your email address).",
    "notify.smtp_password": "SMTP login password or app-specific password.",
    "notify.email_recipient": "Recipient email address for weekly paper digest.",
    "campus.enabled": "Enable/disable campus proxy for paywalled paper downloads (true/false).",
    "campus.http_proxy": "Campus HTTP proxy URL, e.g. http://proxy.campus.edu:8080",
    "campus.https_proxy": "Campus HTTPS proxy URL (usually same as http_proxy).",
    "campus.ieee_inst_url": "Institutional IEEE Xplore URL (optional).",
    "campus.acm_inst_url": "Institutional ACM Digital Library URL (optional).",
}


def _check_config_for(feature: str) -> str:
    """Check which required config keys are missing for a feature.

    Supports "any_X" groups where owning any one of the listed keys is sufficient.

    Returns a JSON string with:
        ok: bool - whether all requirements are met
        feature: str - the feature name
        missing: list[dict] - list of missing requirements with help text
        help_text: str - human-readable instructions for the agent to relay
    """
    required = _REQUIRED_KEYS.get(feature, {})
    if not required:
        return json.dumps({"ok": True, "feature": feature})

    config = PaperExpertConfig.load()
    missing: list[dict[str, str]] = []

    for group, keys in required.items():
        if group.startswith("any_"):
            satisfied = False
            for k in keys:
                try:
                    v = config.get_nested(k)
                except KeyError:
                    v = ""
                if v:
                    satisfied = True
                    break
            if not satisfied:
                label = group[4:]  # strip "any_"
                key_descs = ", ".join(keys)
                missing.append({
                    "key": key_descs,
                    "help": (
                        f"{label}: need one of [{key_descs}]. "
                        "For local (free, no API key): set llm.local_model "
                        "and run 'ollama pull qwen2.5'. "
                        "For cloud: set api_keys.openai."
                    ),
                    "example_value": (
                        "For local: key=llm.local_model value=ollama/qwen2.5"
                    ),
                })
        else:
            try:
                value = config.get_nested(group)
            except KeyError:
                value = ""
            if not value:
                missing.append({
                    "key": group,
                    "help": _CONFIG_KEY_HELP.get(group, group),
                    "example_value": {
                        "api_keys.openai": "sk-...",
                        "api_keys.semantic_scholar": "your-s2-key",
                        "api_keys.unpaywall_email": "your@email.com",
                        "api_keys.ieee_xplore": "your-ieee-key",
                        "api_keys.anthropic": "sk-ant-...",
                        "llm.local_model": "ollama/qwen2.5",
                        "llm.cloud_model": "openai/gpt-4o",
                        "llm.api_base": "https://api.openai.com/v1",
                        "notify.wechat_webhook": "https://qyapi.weixin.qq.com/...",
                        "notify.feishu_webhook": "https://open.feishu.cn/...",
                        "notify.dingtalk_webhook": "https://oapi.dingtalk.com/...",
                        "notify.smtp_host": "smtp.gmail.com",
                        "notify.smtp_port": "587",
                        "notify.smtp_username": "your@email.com",
                        "notify.smtp_password": "your-app-password",
                        "notify.email_recipient": "your@email.com",
                    }.get(group, ""),
                })

    if not missing:
        return json.dumps({"ok": True, "feature": feature})

    help_lines = [f"- {m['key']}: {m['help']}" for m in missing]
    help_text = (
        f"Feature '{feature}' requires the following configuration:\n\n"
        + "\n".join(help_lines)
        + "\n\nPlease ask the user to provide these values, then call set_config "
        + "for each one."
    )
    return json.dumps({
        "ok": False,
        "feature": feature,
        "missing": missing,
        "help_text": help_text,
    }, ensure_ascii=False)


@mcp.tool()
async def ask_question(
    question: str,
    scope: str | None = None,
    auto_fetch: bool = False,
) -> str:
    """Ask a question based on papers in the knowledge base.

    The answer is grounded in paper content with citation references.

    Args:
        question: Your research question.
        scope: Optional scope filter: "tag:OPC", "year:2024-2025".
        auto_fetch: If true, automatically search and add new papers when evidence is insufficient.

    Returns:
        Answer with sources, confidence level, and cost.
    """
    lib = _get_library()

    answer = await lib.ask(question, scope=scope, auto_fetch=auto_fetch)

    result = {
        "answer": answer.answer,
        "confidence": answer.confidence.value,
        "is_sufficient": answer.is_sufficient,
        "sources": [
            {"paper": s.paper_title, "year": s.year, "excerpt": s.passage[:200]}
            for s in answer.sources
        ],
        "cost": answer.cost,
    }
    if answer.error:
        result["error"] = answer.error

    # Warn if config is incomplete even though QA may work without cloud key
    check = json.loads(_check_config_for("ask_question"))
    if not check["ok"]:
        result["config_warning"] = check["help_text"]

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def generate_review(
    topic: str,
    scope: str | None = None,
    auto_fetch: bool = False,
) -> str:
    """Generate a structured literature review on a topic.

    The review includes: Introduction, Methodology Taxonomy, Detailed Analysis,
    Discussion, Research Gaps, and References.

    Args:
        topic: Research topic for the review (e.g. "neural approaches to inverse lithography").
        scope: Optional scope filter: "tag:OPC", "year:2022-2025".
        auto_fetch: If true, fetch additional papers if coverage is thin.

    Returns:
        Complete Markdown literature review.
    """
    lib = _get_library()

    check = json.loads(_check_config_for("generate_review"))
    if not check["ok"]:
        return check["help_text"]

    review = await lib.generate_review(
        topic=topic, scope=scope, auto_fetch=auto_fetch,
    )
    return review


@mcp.tool()
async def suggest_directions(topic: str) -> str:
    """Analyze the knowledge base and suggest promising research directions.

    Identifies gaps in the method x problem matrix, detects trends,
    and generates evidence-based suggestions.

    Args:
        topic: Research area to analyze (e.g. "GAN-OPC", "computational lithography").

    Returns:
        Structured Markdown report with suggestions, trends, and unexplored combinations.
    """
    lib = _get_library()

    check = json.loads(_check_config_for("suggest_directions"))
    if not check["ok"]:
        return check["help_text"]

    report = await lib.suggest_directions(topic)
    return report.full_text


@mcp.tool()
async def build_expertise(
    topic: str,
    question: str | None = None,
) -> str:
    """Build domain expertise by systematically reading papers, or ask an expert question.

    Without a question: digests all papers on the topic and generates a domain knowledge report.
    With a question: answers using deep domain knowledge (more context than regular QA).

    Args:
        topic: Domain/topic (e.g. "inverse lithography technology").
        question: Optional expert-level question to answer using domain knowledge.

    Returns:
        Domain knowledge report (Markdown), or expert answer if question provided.
    """
    lib = _get_library()

    check = json.loads(_check_config_for("build_expertise"))
    if not check["ok"]:
        return check["help_text"]

    return await lib.build_expertise(topic, ask=question)


# ── Domain Management ────────────────────────────────────


@mcp.tool()
async def setup_domain(
    domain_name: str,
    keywords_json: str | None = None,
) -> str:
    """Set up or change your research domain for paper classification.

    This is the first thing you should do before using classification features.
    Define your research field and keyword groups for L0 classification.

    Args:
        domain_name: Your research field name (e.g. "Quantum Computing", "Bioinformatics").
        keywords_json: Optional JSON string defining L0 keyword groups.
            Format: {"Group1": ["keyword1", "keyword2"], "Group2": ["keyword3"]}
            Example: {"Quantum": ["qubit", "quantum gate", "entanglement"],
                      "ML": ["neural", "deep learning"]}

    Returns:
        Confirmation with current domain configuration.
    """
    from paper_expert.core.domain import init_domain

    l0_keywords: dict[str, list[str]] = {}
    if keywords_json:
        try:
            l0_keywords = json.loads(keywords_json)
        except json.JSONDecodeError:
            return "Invalid keywords_json format. Must be a valid JSON object."

    domain = init_domain(domain_name, l0_keywords=l0_keywords)

    # Save to config
    lib = _get_library()
    lib.config.domain = domain
    lib.config.save()

    result = {
        "domain_name": domain.domain_name,
        "l0_keyword_groups": list(domain.l0_keywords.keys()),
        "l0_keyword_counts": {k: len(v) for k, v in domain.l0_keywords.items()},
        "l1_vocabulary_entries": len(domain.l1_vocabulary),
        "status": "Domain configured successfully.",
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_domain_config() -> str:
    """Get current domain configuration.

    Returns:
        Current domain name, keyword groups, and vocabulary settings.
    """
    lib = _get_library()
    domain = lib.config.domain

    if not domain.is_initialized():
        return json.dumps({"status": "No domain configured. Use setup_domain first."})

    result = {
        "domain_name": domain.domain_name,
        "l0_keywords": domain.l0_keywords,
        "l1_vocabulary_count": len(domain.l1_vocabulary),
        "l1_vocabulary_terms": list(domain.l1_vocabulary.keys()),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def add_domain_keyword(group: str, keyword: str) -> str:
    """Add a keyword to an existing L0 domain group, or create a new group.

    Args:
        group: Domain group name (e.g. "Quantum", "ML").
        keyword: Keyword to add (e.g. "qubit", "transformer").

    Returns:
        Updated keyword group contents.
    """
    lib = _get_library()
    domain = lib.config.domain

    if not domain.is_initialized():
        return "No domain configured. Use setup_domain first."

    if group not in domain.l0_keywords:
        domain.l0_keywords[group] = []
    if keyword not in domain.l0_keywords[group]:
        domain.l0_keywords[group].append(keyword)

    lib.config.save()

    return json.dumps({
        "group": group,
        "keywords": domain.l0_keywords[group],
        "total_keywords": sum(len(v) for v in domain.l0_keywords.values()),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def add_domain_vocab(canonical: str, aliases: str) -> str:
    """Add a vocabulary entry for L1 tag normalization.

    Args:
        canonical: Canonical term (e.g. "GAN").
        aliases: Comma-separated aliases (e.g. "Generative Adversarial Network, GANs").

    Returns:
        Updated vocabulary entry.
    """
    lib = _get_library()
    domain = lib.config.domain

    if not domain.is_initialized():
        return "No domain configured. Use setup_domain first."

    alias_list = [a.strip() for a in aliases.split(",") if a.strip()]
    domain.l1_vocabulary[canonical] = alias_list

    lib.config.save()

    # Also update the database vocabulary
    lib.db.add_vocabulary(canonical, alias_list)

    return json.dumps({
        "canonical": canonical,
        "aliases": alias_list,
        "total_vocab_entries": len(domain.l1_vocabulary),
    }, ensure_ascii=False, indent=2)


# ── Configuration Management ───────────────────────────


@mcp.tool()
async def get_config() -> str:
    """Get current configuration values (API keys shown as masked).

    Returns:
        JSON with current config: library_path, LLM settings, API key status,
        notify settings, email config.
    """
    lib = _get_library()
    c = lib.config
    result = {
        "library_path": str(c.library_path),
        "llm": {
            "local_model": c.llm.local_model,
            "cloud_model": c.llm.cloud_model,
            "embedding_model": c.llm.embedding_model,
            "api_base": c.llm.api_base or "(default)",
        },
        "api_keys": {
            "openai": "***configured***" if c.api_keys.openai else "(not set)",
            "semantic_scholar": "***configured***" if c.api_keys.semantic_scholar else "(not set)",
            "anthropic": "***configured***" if c.api_keys.anthropic else "(not set)",
            "ieee_xplore": "***configured***" if c.api_keys.ieee_xplore else "(not set)",
            "unpaywall_email": c.api_keys.unpaywall_email or "(not set)",
        },
        "search": {
            "default_sources": c.search.default_sources,
            "default_limit": c.search.default_limit,
        },
        "notify": {
            "wechat_webhook": "***configured***" if c.notify.wechat_webhook else "(not set)",
            "feishu_webhook": "***configured***" if c.notify.feishu_webhook else "(not set)",
            "dingtalk_webhook": "***configured***" if c.notify.dingtalk_webhook else "(not set)",
            "smtp_host": c.notify.smtp_host or "(not set)",
            "smtp_port": c.notify.smtp_port,
            "smtp_username": c.notify.smtp_username or "(not set)",
            "email_recipient": c.notify.email_recipient or "(not set)",
        },
        "campus": {
            "enabled": c.campus.enabled,
            "http_proxy": c.campus.http_proxy or "(not set)",
            "https_proxy": c.campus.https_proxy or "(not set)",
            "ieee_inst_url": c.campus.ieee_inst_url or "(not set)",
            "acm_inst_url": c.campus.acm_inst_url or "(not set)",
        },
        "domain": {
            "name": c.domain.domain_name or "(not set)",
            "keyword_groups": len(c.domain.l0_keywords),
            "vocab_entries": len(c.domain.l1_vocabulary),
        },
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def set_config(key: str, value: str) -> str:
    """Set a configuration value and save it to disk.

    Use this to configure API keys and other settings that features need.
    After setting all required values, retry the feature that asked for them.

    Args:
        key: Config key in dotted notation. Common keys:
            - api_keys.openai              (OpenAI API key)
            - api_keys.semantic_scholar    (S2 API key)
            - api_keys.unpaywall_email     (unpaywall email)
            - api_keys.ieee_xplore         (IEEE API key)
            - api_keys.anthropic           (Anthropic API key)
            - llm.local_model              (e.g. "ollama/qwen2.5")
            - llm.cloud_model              (e.g. "openai/gpt-4o")
            - llm.api_base                 (custom API base URL)
            - notify.wechat_webhook        (WeChat bot webhook URL)
            - notify.feishu_webhook        (Feishu bot webhook URL)
            - notify.dingtalk_webhook      (DingTalk bot webhook URL)
            - notify.smtp_host             (SMTP host, e.g. smtp.gmail.com)
            - notify.smtp_port             (SMTP port, e.g. 587)
            - notify.smtp_username         (SMTP login username)
            - notify.smtp_password         (SMTP login password)
            - notify.email_recipient       (recipient email address)
            - campus.enabled               (true/false)
            - campus.http_proxy            (e.g. http://proxy.campus.edu:8080)
            - campus.https_proxy           (e.g. http://proxy.campus.edu:8080)
            - campus.ieee_inst_url         (institutional IEEE URL)
            - campus.acm_inst_url          (institutional ACM URL)
        value: The value to set for this key.

    Returns:
        Confirmation with the key that was set (value is never shown).
    """
    known_keys = _CONFIG_KEY_HELP.keys()
    if key not in known_keys:
        valid = "\n".join(f"  - {k}" for k in sorted(known_keys))
        return (
            f"Unknown config key: '{key}'.\n\n"
            f"Valid keys:\n{valid}"
        )

    lib = _get_library()
    config = lib.config
    try:
        config.set_nested(key, value)
        config.save()
    except (KeyError, ValueError) as e:
        return f"Failed to set '{key}': {e}"

    return json.dumps({
        "status": "ok",
        "key": key,
        "message": f"'{key}' has been configured.",
    }, ensure_ascii=False)


@mcp.tool()
async def check_required_config(feature: str) -> str:
    """Check which configuration is needed for a feature.

    Use this before generate_review, suggest_directions, or build_expertise
    to understand what API keys are required.

    Args:
        feature: One of: generate_review, suggest_directions, build_expertise, ask_question.

    Returns:
        JSON with ok=true if ready, or list of missing config keys with instructions.
    """
    valid = list(_REQUIRED_KEYS.keys())
    if feature not in valid:
        return json.dumps({
            "ok": False,
            "error": f"Unknown feature: {feature}. Valid: {', '.join(valid)}",
        })

    return _check_config_for(feature)


# ── Campus Download Tools ──────────────────────────────


@mcp.tool()
async def enable_campus_proxy(
    http_proxy: str = "",
    https_proxy: str = "",
    ieee_inst_url: str = "",
    acm_inst_url: str = "",
) -> str:
    """Enable campus network proxy for downloading paywalled papers.

    After enabling, paper downloads will try the campus proxy first
    before falling back to arXiv/Unpaywall.

    Args:
        http_proxy: HTTP proxy URL, e.g. "http://proxy.campus.edu:8080"
        https_proxy: HTTPS proxy URL (same as http_proxy usually)
        ieee_inst_url: Institutional IEEE access URL (optional)
        acm_inst_url: Institutional ACM access URL (optional)

    Returns:
        Confirmation with current campus config.
    """
    lib = _get_library()
    lib.config.campus.enabled = True
    if http_proxy:
        lib.config.campus.http_proxy = http_proxy
    if https_proxy:
        lib.config.campus.https_proxy = https_proxy
    if ieee_inst_url:
        lib.config.campus.ieee_inst_url = ieee_inst_url
    if acm_inst_url:
        lib.config.campus.acm_inst_url = acm_inst_url
    lib.config.save()
    return json.dumps({
        "status": "Campus proxy enabled",
        "http_proxy": lib.config.campus.http_proxy,
        "https_proxy": lib.config.campus.https_proxy,
        "ieee_inst_url": lib.config.campus.ieee_inst_url,
        "acm_inst_url": lib.config.campus.acm_inst_url,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def disable_campus_proxy() -> str:
    """Disable campus network proxy for paper downloads.

    Returns:
        Confirmation.
    """
    lib = _get_library()
    lib.config.campus.enabled = False
    lib.config.save()
    return "Campus proxy disabled."


@mcp.tool()
async def campus_download_paper(
    identifier: str,
) -> str:
    """Download a paper PDF via campus proxy and add to library.

    Args:
        identifier: Paper identifier: "doi:10.xxx/yyy" or "arxiv:xxxx.xxxxx".

    Returns:
        Download result with paper ID and state.
    """
    lib = _get_library()
    paper = await lib.add_by_identifier(identifier)
    if not paper:
        return f"Failed to resolve: {identifier}"
    tags = ", ".join(t.tag for t in paper.tags) if paper.tags else "none"
    return json.dumps({
        "id": paper.id,
        "title": paper.title,
        "state": paper.state.value,
        "tags": tags,
        "doi": paper.doi,
    }, ensure_ascii=False, indent=2)


# ── Monitor & Notify Tools ──────────────────────────────


@mcp.tool()
async def add_watch_topic(
    name: str,
    queries_json: str,
    limit: int = 10,
    sources_json: str | None = None,
    channels_json: str | None = None,
) -> str:
    """Set up a research direction to monitor for new papers weekly.

    After adding watch topics, call run_monitor on a schedule to fetch and notify.

    Args:
        name: Watch topic name (e.g. "Quantum Error Correction").
        queries_json: JSON array of search queries.
            Example: '["quantum error mitigation", "surface codes"]'
        limit: Max papers to fetch per query (default 10).
        sources_json: Optional JSON array of sources. Default: config defaults.
            Example: '["semantic_scholar", "arxiv"]'
        channels_json: Optional JSON array of notification channels.
            Example: '["wechat", "email"]'. Default: all configured.

    Returns:
        Created watch topic details with ID.
    """
    try:
        queries = json.loads(queries_json)
        if not isinstance(queries, list):
            return "queries_json must be a JSON array."
    except json.JSONDecodeError:
        return "Invalid JSON for queries_json."

    sources = None
    if sources_json:
        try:
            sources = json.loads(sources_json)
        except json.JSONDecodeError:
            return "Invalid JSON for sources_json."

    channels = None
    if channels_json:
        try:
            channels = json.loads(channels_json)
        except json.JSONDecodeError:
            return "Invalid JSON for channels_json."

    lib = _get_library()
    topic_id = lib.add_watch_topic(
        name=name,
        queries=queries,
        sources=sources,
        fetch_limit=limit,
        notify_channels=channels,
    )
    topic = lib.get_watch_topic(topic_id)
    return json.dumps(topic, ensure_ascii=False, indent=2, default=str)


@mcp.tool()
async def list_watch_topics() -> str:
    """List all configured research watch topics.

    Returns:
        JSON array of watch topics with ID, name, queries, active status.
    """
    lib = _get_library()
    topics = lib.list_watch_topics()
    result = []
    for t in topics:
        result.append({
            "id": t["id"],
            "name": t["name"],
            "queries": t.get("queries", []),
            "sources": t.get("sources", []),
            "fetch_limit": t.get("fetch_limit", 10),
            "notify_channels": t.get("notify_channels", []),
            "is_active": bool(t.get("is_active", 1)),
            "created_at": t.get("created_at"),
            "last_run_at": t.get("last_run_at"),
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def remove_watch_topic(watch_id: int) -> str:
    """Remove a research watch topic by ID.

    Args:
        watch_id: Watch topic ID from list_watch_topics.

    Returns:
        Confirmation message.
    """
    lib = _get_library()
    topic = lib.get_watch_topic(watch_id)
    if not topic:
        return f"Watch topic {watch_id} not found."
    lib.delete_watch_topic(watch_id)
    return f"Deleted watch topic: {topic['name']}"


@mcp.tool()
async def toggle_watch_topic(watch_id: int) -> str:
    """Enable or disable a watch topic.

    Args:
        watch_id: Watch topic ID.

    Returns:
        New state.
    """
    lib = _get_library()
    topic = lib.get_watch_topic(watch_id)
    if not topic:
        return f"Watch topic {watch_id} not found."
    new_state = not topic["is_active"]
    lib.update_watch_topic(watch_id, is_active=new_state)
    s = "enabled" if new_state else "disabled"
    return f"Watch topic '{topic['name']}' is now {s}."


@mcp.tool()
async def run_monitor(watch_id: int | None = None) -> str:
    """Execute paper monitoring: search for new papers and send notifications.

    This is the main tool to call on a schedule (e.g. weekly).
    Without watch_id, runs all active topics.

    Args:
        watch_id: Optional specific watch topic ID. Omit to run all.

    Returns:
        JSON summary of monitoring results.
    """
    lib = _get_library()
    result = await lib.run_monitor(watch_id=watch_id)

    if hasattr(result, "results"):
        output = {
            "run_at": result.run_at,
            "topics_checked": result.topics_checked,
            "total_found": result.total_found,
            "total_added": result.total_added,
            "details": [],
        }
        for r in result.results:
            output["details"].append({
                "topic": r.topic_name,
                "papers_found": r.papers_found,
                "papers_added": r.papers_added,
                "new_papers": [
                    {"title": p["title"][:80], "year": p.get("year"),
                     "doi": p.get("doi")}
                    for p in r.new_papers
                ],
                "notified_via": [k for k, v in r.notify_results.items() if v],
                "error": r.error,
            })
    else:
        output = {
            "topic": result.topic_name,
            "papers_found": result.papers_found,
            "papers_added": result.papers_added,
            "new_papers": [
                {"title": p["title"][:80], "year": p.get("year"),
                 "doi": p.get("doi")}
                for p in result.new_papers
            ],
            "notified_via": [k for k, v in result.notify_results.items() if v],
            "error": result.error,
        }
    return json.dumps(output, ensure_ascii=False, indent=2)


@mcp.tool()
async def set_notify_channel(channel: str, webhook_url: str) -> str:
    """Configure a notification channel for paper monitoring.

    Args:
        channel: Which channel: "wechat", "feishu", "dingtalk", or "email".
            For "email", webhook_url is the recipient email address.
        webhook_url: The webhook URL, or email address for the email channel.

    Returns:
        Confirmation.
    """
    if channel not in ("wechat", "feishu", "dingtalk", "email"):
        return f"Unknown channel: {channel}. Use wechat, feishu, dingtalk, or email."
    lib = _get_library()
    if channel == "wechat":
        lib.config.notify.wechat_webhook = webhook_url
    elif channel == "feishu":
        lib.config.notify.feishu_webhook = webhook_url
    elif channel == "dingtalk":
        lib.config.notify.dingtalk_webhook = webhook_url
    elif channel == "email":
        lib.config.notify.email_recipient = webhook_url
    lib.config.save()
    return f"{channel} channel configured."


@mcp.tool()
async def get_monitor_logs(watch_id: int, limit: int = 10) -> str:
    """Get recent monitoring logs for a watch topic.

    Args:
        watch_id: Watch topic ID.
        limit: Max log entries (default 10).

    Returns:
        JSON array of log entries.
    """
    lib = _get_library()
    logs = lib.get_watch_logs(watch_id, limit=limit)
    result = []
    for log in logs:
        result.append({
            "run_at": log.get("run_at"),
            "papers_found": log.get("papers_found", 0),
            "papers_added": log.get("papers_added", 0),
            "notify_status": log.get("notify_status"),
            "error": log.get("error"),
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Entry point ──────────────────────────────────────────

def main():
    """Run the MCP server."""
    atexit.register(_cleanup)
    mcp.run(transport="stdio")


def _cleanup():
    try:
        asyncio.run(_close_library())
    except Exception:
        pass


if __name__ == "__main__":
    main()
