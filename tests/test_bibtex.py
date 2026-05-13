"""Unit tests for BibTeX importer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from paper_expert.importers.bibtex import parse_bibtex

_SAMPLE_BIB = r"""
@article{vaswani2017attention,
  title = {Attention Is All You Need},
  author = {Vaswani, Ashish and Shazeer, Noam and Parmar, Niki},
  year = {2017},
  journal = {Advances in Neural Information Processing Systems},
  doi = {10.5555/3295222.3295349},
  abstract = {The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.},
}

@inproceedings{gao2024opc,
  title = {Neural {OPC} with {GAN}-Based Mask Synthesis},
  author = {Gao, Wei and Chen, Yibo},
  year = {2024},
  booktitle = {Proc. SPIE Advanced Lithography},
  eprint = {2401.12345},
  archiveprefix = {arXiv},
}

@misc{nopaper,
  note = {This entry has no title},
}
"""


class TestBibTexImporter:
    def test_parse_basic(self, tmp_path: Path) -> None:
        bib_file = tmp_path / "test.bib"
        bib_file.write_text(_SAMPLE_BIB, encoding="utf-8")

        results = parse_bibtex(bib_file)

        # Should skip entry without title
        assert len(results) == 2

    def test_metadata_extraction(self, tmp_path: Path) -> None:
        bib_file = tmp_path / "test.bib"
        bib_file.write_text(_SAMPLE_BIB, encoding="utf-8")

        results = parse_bibtex(bib_file)
        vaswani = results[0]

        assert vaswani.title == "Attention Is All You Need"
        assert "Ashish Vaswani" in vaswani.authors
        assert vaswani.year == 2017
        assert vaswani.doi == "10.5555/3295222.3295349"

    def test_arxiv_extraction(self, tmp_path: Path) -> None:
        bib_file = tmp_path / "test.bib"
        bib_file.write_text(_SAMPLE_BIB, encoding="utf-8")

        results = parse_bibtex(bib_file)
        gao = results[1]

        assert gao.arxiv_id == "2401.12345"
        assert "OPC" in gao.title  # LaTeX braces cleaned

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_bibtex(Path("/nonexistent/file.bib"))
