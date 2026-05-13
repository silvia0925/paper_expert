"""Domain configuration module -- user-defined research direction.

No preset domains. All vocabulary, keywords, and classification prompts
are defined by the user to match their specific research field.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DomainConfig:
    """User-defined research domain configuration.

    No defaults -- every field starts empty. The user must initialize
    their domain before classification and vocabulary features work.
    """

    domain_name: str = ""
    # L0 domain groups: {"Physics": {"quantum", "qubit", ...}, "ML": {"neural", ...}}
    l0_keywords: dict[str, list[str]] = field(default_factory=dict)
    # L1 vocabulary: {"GAN": ["Generative Adversarial Network", ...], ...}
    l1_vocabulary: dict[str, list[str]] = field(default_factory=dict)
    # LLM classification prompt template (domain-agnostic default)
    l1_prompt_template: str = ""

    def is_initialized(self) -> bool:
        """Check if the domain has been set up."""
        return bool(self.domain_name)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for TOML persistence."""
        return {
            "domain_name": self.domain_name,
            "l0_keywords": self.l0_keywords,
            "l1_vocabulary": self.l1_vocabulary,
            "l1_prompt_template": self.l1_prompt_template,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DomainConfig:
        """Deserialize from a plain dict (TOML-loaded)."""
        return cls(
            domain_name=data.get("domain_name", ""),
            l0_keywords=data.get("l0_keywords", {}),
            l1_vocabulary=data.get("l1_vocabulary", {}),
            l1_prompt_template=data.get("l1_prompt_template", ""),
        )


# Default L1 prompt template (domain-agnostic, filled at runtime)
_DEFAULT_L1_PROMPT = """You are an academic paper classifier specializing in {domain_name}.

Given a paper's title and abstract, classify it into 1-3 sub-topic tags.

Domain terminology for reference:
{vocab_summary}

Respond ONLY with a JSON array of tag strings, e.g.: ["{example_tag}", "{another_tag}"]

Title: {title}
Abstract: {abstract}
"""


def init_domain(
    domain_name: str,
    l0_keywords: dict[str, list[str]] | None = None,
    l1_vocabulary: dict[str, list[str]] | None = None,
) -> DomainConfig:
    """Create a DomainConfig from user input.

    Args:
        domain_name: The research field name (e.g. "Quantum Computing").
        l0_keywords: Domain groups with keyword lists for L0 classification.
        l1_vocabulary: Canonical term → alias mappings for L1 normalization.

    Returns:
        A fully initialized DomainConfig.
    """
    vocab = l1_vocabulary or {}
    keywords = l0_keywords or {}

    # Build default prompt template if not provided
    prompt = _DEFAULT_L1_PROMPT

    config = DomainConfig(
        domain_name=domain_name,
        l0_keywords=keywords,
        l1_vocabulary=vocab,
        l1_prompt_template=prompt,
    )
    logger.info("Initialized domain: %s with %d keyword groups, %d vocab entries",
                domain_name, len(keywords), len(vocab))
    return config


def build_l1_prompt(
    domain_config: DomainConfig,
    title: str,
    abstract: str | None,
) -> str:
    """Build the L1 classification prompt using domain config.

    Fills in the template with domain-specific vocabulary and examples.
    """
    # Build vocabulary summary from l1_vocabulary
    vocab_lines: list[str] = []
    for canonical, aliases in domain_config.l1_vocabulary.items():
        aliases_str = ", ".join(aliases[:3])
        vocab_lines.append(f"- {canonical}: {aliases_str}")

    vocab_summary = "\n".join(vocab_lines) if vocab_lines else f"(No vocabulary defined yet for {domain_config.domain_name})"

    # Pick example tags from vocabulary
    example_tags = list(domain_config.l1_vocabulary.keys())[:2]
    example_tag = example_tags[0] if example_tags else "Topic1"
    another_tag = example_tags[1] if len(example_tags) > 1 else "Topic2"

    return domain_config.l1_prompt_template.format(
        domain_name=domain_config.domain_name,
        vocab_summary=vocab_summary,
        example_tag=example_tag,
        another_tag=another_tag,
        title=title,
        abstract=abstract or "No abstract available.",
    )


def save_domain_config_to_toml(domain: DomainConfig) -> str:
    """Serialize DomainConfig to TOML section string."""
    lines: list[str] = []
    lines.append(f"domain_name = '{domain.domain_name}'")

    # l0_keywords as inline tables
    lines.append("")
    lines.append("[domain.l0_keywords]")
    for group, keywords in domain.l0_keywords.items():
        kw_str = ", ".join(f"'{k}'" for k in keywords)
        lines.append(f"{group} = [{kw_str}]")

    # l1_vocabulary as inline tables
    lines.append("")
    lines.append("[domain.l1_vocabulary]")
    for canonical, aliases in domain.l1_vocabulary.items():
        alias_str = ", ".join(f"'{a}'" for a in aliases)
        lines.append(f"{canonical} = [{alias_str}]")

    # l1_prompt_template (use multi-line if long)
    lines.append("")
    if domain.l1_prompt_template:
        template = domain.l1_prompt_template.replace("\\", "\\\\")
        lines.append(f"l1_prompt_template = '{template}'")
    else:
        lines.append("l1_prompt_template = ''")

    return "\n".join(lines)


def load_domain_from_toml(data: dict[str, Any]) -> DomainConfig:
    """Load DomainConfig from TOML-parsed dict.

    The TOML section looks like:
    ```toml
    [domain]
    domain_name = "Quantum Computing"

    [domain.l0_keywords]
    Physics = ["quantum", "qubit"]

    [domain.l1_vocabulary]
    QNN = ["Quantum Neural Network", "Quantum NN"]
    ```
    """
    domain_data = data.get("domain", {})
    if not domain_data:
        return DomainConfig()

    domain_name = domain_data.get("domain_name", "")

    # Parse l0_keywords (TOML arrays become Python lists)
    l0_keywords: dict[str, list[str]] = {}
    l0_raw = domain_data.get("l0_keywords", {})
    for group, keywords in l0_raw.items():
        if isinstance(keywords, list):
            l0_keywords[group] = keywords
        elif isinstance(keywords, str):
            l0_keywords[group] = [k.strip() for k in keywords.split(",")]

    # Parse l1_vocabulary
    l1_vocabulary: dict[str, list[str]] = {}
    l1_raw = domain_data.get("l1_vocabulary", {})
    for canonical, aliases in l1_raw.items():
        if isinstance(aliases, list):
            l1_vocabulary[canonical] = aliases
        elif isinstance(aliases, str):
            l1_vocabulary[canonical] = [a.strip() for a in aliases.split(",")]

    l1_prompt_template = domain_data.get("l1_prompt_template", "")

    return DomainConfig(
        domain_name=domain_name,
        l0_keywords=l0_keywords,
        l1_vocabulary=l1_vocabulary,
        l1_prompt_template=l1_prompt_template,
    )
