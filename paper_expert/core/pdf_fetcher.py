"""PDF acquisition waterfall.

Attempts to fetch PDFs through a prioritized sequence of sources.
Order: Campus proxy (if enabled) -> arXiv direct -> S2 openAccessPdf -> Unpaywall -> metadata-only.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from paper_expert.adapters.arxiv import ArxivAdapter
from paper_expert.models.paper import PaperMetadata

logger = logging.getLogger(__name__)

_UNPAYWALL_API = "https://api.unpaywall.org/v2"


class PDFFetcher:
    """Fetches PDFs via a waterfall of open access sources."""

    def __init__(self, pdf_dir: Path, unpaywall_email: str = "", config: Any = None) -> None:
        self.pdf_dir = pdf_dir
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.unpaywall_email = unpaywall_email
        self._config = config
        self._client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch(
        self, metadata: PaperMetadata, category: str | None = None
    ) -> Path | None:
        """Attempt to fetch PDF using the waterfall strategy.

        Args:
            metadata: Paper metadata for PDF lookup.
            category: L0 category (e.g. "AI", "Computational Lithography").
                      PDF is stored under pdfs/<category>/ subfolder.

        Returns the local path to the downloaded PDF, or None if unavailable.
        """
        # Determine target directory: pdfs/<category>/
        target_dir = self._category_dir(category)
        filename = self._make_filename(metadata)
        dest = target_dir / filename

        if dest.exists():
            logger.info("PDF already exists: %s", dest)
            return dest

        # Step 0: Campus proxy download (highest priority if enabled)
        if metadata.doi and self._config:
            from paper_expert.core.campus_downloader import campus_download

            success = await campus_download(metadata.doi, dest, self._config)
            if success:
                logger.info("PDF fetched via campus proxy: %s", metadata.doi)
                return dest

        # Step 1: arXiv direct link
        if metadata.arxiv_id:
            url = ArxivAdapter.pdf_url(metadata.arxiv_id)
            result = await self._download(url, dest)
            if result:
                logger.info("PDF fetched from arXiv: %s", metadata.arxiv_id)
                return result

        # Step 2: Semantic PaperExpert openAccessPdf
        if metadata.open_access_pdf_url:
            result = await self._download(metadata.open_access_pdf_url, dest)
            if result:
                logger.info("PDF fetched from S2 OA link")
                return result

        # Step 3: Unpaywall
        if metadata.doi and self.unpaywall_email:
            url = await self._unpaywall_lookup(metadata.doi)
            if url:
                result = await self._download(url, dest)
                if result:
                    logger.info("PDF fetched from Unpaywall")
                    return result

        logger.info(
            "No PDF available for: %s (will be metadata-only)",
            metadata.title[:80],
        )
        return None

    async def _download(self, url: str, dest: Path) -> Path | None:
        """Download a file from URL to dest. Returns dest on success, None on failure."""
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "pdf" not in content_type and not resp.content[:5] == b"%PDF-":
                logger.debug("URL did not return PDF: %s (got %s)", url, content_type)
                return None

            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return dest
        except (httpx.HTTPError, OSError) as e:
            logger.debug("Download failed from %s: %s", url, e)
            return None

    async def _unpaywall_lookup(self, doi: str) -> str | None:
        """Query Unpaywall for an OA PDF URL."""
        try:
            resp = await self._client.get(
                f"{_UNPAYWALL_API}/{doi}",
                params={"email": self.unpaywall_email},
            )
            resp.raise_for_status()
            data = resp.json()

            best = data.get("best_oa_location") or {}
            pdf_url = best.get("url_for_pdf")
            if pdf_url:
                return pdf_url

            # Fallback to any OA location with a PDF
            for loc in data.get("oa_locations", []):
                if loc.get("url_for_pdf"):
                    return loc["url_for_pdf"]

            return None
        except (httpx.HTTPError, KeyError) as e:
            logger.debug("Unpaywall lookup failed for %s: %s", doi, e)
            return None

    def _category_dir(self, category: str | None) -> Path:
        """Get the PDF storage directory for a category.

        Rule: PDFs are organized by L0 classification into subfolders.
        e.g. pdfs/AI/, pdfs/Computational Lithography/, pdfs/Cross-domain/
        """
        if not category:
            category = "Uncategorized"
        # Sanitize category name for filesystem
        safe_cat = "".join(
            c if c.isalnum() or c in " -_" else "_"
            for c in category
        ).strip()
        target = self.pdf_dir / safe_cat
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _make_filename(self, metadata: PaperMetadata) -> str:
        """Generate a safe filename from the paper title.

        Rule: ALL PDFs are named by paper title, no exceptions.
        """
        title = metadata.title.strip()
        if not title:
            # Last resort fallback if title is truly empty
            if metadata.doi:
                title = metadata.doi
            elif metadata.arxiv_id:
                title = metadata.arxiv_id
            else:
                title = "untitled"

        # Sanitize: keep alphanumeric, spaces, hyphens; replace rest with _
        safe = "".join(
            c if c.isalnum() or c in " -" else "_"
            for c in title
        ).strip()
        # Collapse multiple underscores/spaces
        while "  " in safe:
            safe = safe.replace("  ", " ")
        while "__" in safe:
            safe = safe.replace("__", "_")
        # Truncate to reasonable length (200 chars max for filesystem safety)
        safe = safe[:200].strip(" _-")
        return f"{safe}.pdf"
