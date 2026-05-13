"""Campus network PDF downloader for paywalled papers.

Uses campus proxy / institutional access to download papers that
arXiv, S2 OA, and Unpaywall cannot reach. Runs as the highest-priority
step in the PDF waterfall.

Publisher routing by DOI prefix:
  - 10.1109/  → IEEE Xplore
  - 10.1145/  → ACM Digital Library
  - 10.1007/  → Springer
  - 10.1016/  → Elsevier / ScienceDirect
  - others    → Sci-Hub fallback (configurable)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_IEEE_TPL = "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={arn}&ref="
_ACM_TPL = "https://dl.acm.org/doi/pdf/{doi}"
_SPRINGER_TPL = "https://link.springer.com/content/pdf/{doi}.pdf"
_ELSEVIER_TPL = "https://www.sciencedirect.com/science/article/pii/{pii}/pdf?md5=0&isDTMRedir=Y"

_DOWNLOAD_TIMEOUT = 90.0


def _doi_to_publisher_url(doi: str) -> str | None:
    """Construct a publisher direct PDF URL from a DOI if known."""
    doi = doi.strip()
    if doi.startswith("10.1109/"):
        # IEEE: extract article number after last dot
        # DOI format: 10.1109/TCAD.2023.1234567
        arn = doi.rsplit(".", 1)[-1]
        return _IEEE_TPL.format(arn=arn)
    if doi.startswith("10.1145/"):
        return _ACM_TPL.format(doi=quote(doi, safe=""))
    if doi.startswith("10.1007/"):
        return _SPRINGER_TPL.format(doi=quote(doi, safe=""))
    if doi.startswith("10.1016/") or doi.startswith("10.1016/"):
        # Elsevier: PII is the part after 10.1016/
        pii = doi.replace("10.1016/", "")
        return _ELSEVIER_TPL.format(pii=quote(pii, safe=""))
    return None


async def campus_download(
    doi: str,
    dest: Path,
    config: Any,  # PaperExpertConfig
) -> bool:
    """Download a paper PDF via campus proxy.

    Args:
        doi: Paper DOI.
        dest: Target file path.
        config: PaperExpertConfig (reads campus settings).

    Returns:
        True if PDF was downloaded successfully.
    """
    campus = config.campus
    if not campus.enabled:
        logger.debug("Campus download disabled, skipping DOI: %s", doi)
        return False

    url = _doi_to_publisher_url(doi)
    if not url:
        logger.debug("No publisher URL for DOI: %s", doi)
        return False

    # Build proxy config
    proxy = None
    if campus.https_proxy:
        proxy = campus.https_proxy
    elif campus.http_proxy:
        proxy = campus.http_proxy
    # httpx proxy: pass as "http://proxy:port"
    proxy_url = proxy if proxy and ("://" in proxy) else None

    # Build headers
    headers: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
    }

    client_kwargs: dict[str, Any] = {
        "timeout": _DOWNLOAD_TIMEOUT,
        "follow_redirects": True,
        "headers": headers,
    }
    if proxy_url:
        client_kwargs["proxy"] = proxy_url

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            # Verify PDF
            if resp.content[:5] == b"%PDF-":
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(resp.content)
                logger.info("Campus download succeeded: %s", doi)
                return True

            logger.debug(
                "Campus URL returned non-PDF (len=%d, type=%s): %s",
                len(resp.content),
                resp.headers.get("content-type", "?"),
                url[:80],
            )
    except httpx.HTTPError as e:
        logger.debug("Campus download failed for DOI %s: %s", doi, str(e)[:80])

    return False
