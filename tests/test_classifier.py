"""Unit tests for classification system with user-defined DomainConfig."""

from __future__ import annotations

import pytest

from paper_expert.core.classifier import classify_l0
from paper_expert.core.domain import DomainConfig


@pytest.fixture
def domain() -> DomainConfig:
    return DomainConfig(
        domain_name="Test Domain",
        l0_keywords={
            "AI": ["attention", "transformer", "neural", "deep learning", "GAN", "generative adversarial"],
            "Computational Lithography": ["OPC", "lithography", "optical proximity", "mask optimization", "EUV"],
        },
    )


@pytest.fixture
def empty_domain() -> DomainConfig:
    return DomainConfig()


class TestL0Classifier:
    def test_ai_paper(self, domain: DomainConfig) -> None:
        tags = classify_l0(
            "Attention Is All You Need",
            "We propose the Transformer, a model architecture based on attention mechanisms.",
            domain_config=domain,
        )
        assert tags == ["AI"]

    def test_lithography_paper(self, domain: DomainConfig) -> None:
        tags = classify_l0(
            "Model-Based OPC for Advanced Nodes",
            "Optical proximity correction using resist model calibration.",
            domain_config=domain,
        )
        assert tags == ["Computational Lithography"]

    def test_cross_domain_paper(self, domain: DomainConfig) -> None:
        tags = classify_l0(
            "GAN-based Optical Proximity Correction",
            "We use generative adversarial networks for OPC mask optimization.",
            domain_config=domain,
        )
        assert tags == ["Cross-domain"]

    def test_other_paper(self, domain: DomainConfig) -> None:
        tags = classify_l0(
            "A Study of Butterflies",
            "This paper examines butterfly migration patterns.",
            domain_config=domain,
        )
        assert tags == ["Other"]

    def test_title_only(self, domain: DomainConfig) -> None:
        tags = classify_l0(
            "Deep Learning for EUV Lithography Defect Detection",
            domain_config=domain,
        )
        assert tags == ["Cross-domain"]

    def test_case_insensitive(self, domain: DomainConfig) -> None:
        tags = classify_l0(
            "TRANSFORMER ARCHITECTURE FOR NEURAL NETWORKS",
            domain_config=domain,
        )
        assert tags == ["AI"]

    def test_no_domain_config_returns_other(self) -> None:
        tags = classify_l0("Attention Is All You Need")
        assert tags == ["Other"]

    def test_empty_domain_returns_other(self, empty_domain: DomainConfig) -> None:
        tags = classify_l0(
            "Attention Is All You Need",
            domain_config=empty_domain,
        )
        assert tags == ["Other"]

    def test_single_keyword_match(self, domain: DomainConfig) -> None:
        tags = classify_l0(
            "A Survey of Neural Network Architectures",
            domain_config=domain,
        )
        assert tags == ["AI"]

    def test_no_abstract_works(self, domain: DomainConfig) -> None:
        tags = classify_l0(
            "Advanced EUV Lithography Techniques for 3nm Node",
            domain_config=domain,
        )
        assert tags == ["Computational Lithography"]
