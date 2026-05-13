"""Campus PDF downloader -- standalone script for local campus machines.

Usage:
    python campus_fetch.py <doi_or_file> [--output DIR] [--proxy PROXY]

Examples:
    # Download a single paper by DOI
    python campus_fetch.py "10.1109/TCAD.2023.1234567"

    # Batch download from a file (one DOI per line)
    python campus_fetch.py papers_to_download.txt --output ./pdfs

    # With custom proxy
    python campus_fetch.py "10.1145/3592442" --proxy "http://proxy.campus.edu:8080"

After downloading, use paper-expert CLI to import PDFs:
    paper-expert add doi:10.1109/xxx --pdf ./pdfs/Paper_Title.pdf
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("campus_fetch")

_IEEE_TPL = "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={arn}&ref="
_ACM_TPL = "https://dl.acm.org/doi/pdf/{doi}"
_SPRINGER_TPL = "https://link.springer.com/content/pdf/{doi}.pdf"
_ELSEVIER_TPL = "https://www.sciencedirect.com/science/article/pii/{pii}/pdf?md5=0&isDTMRedir=Y"

_TIMEOUT = 90
_CHUNK = 65536


def doi_to_url(doi: str) -> str | None:
    doi = doi.strip()
    if doi.startswith("10.1109/"):
        arn = doi.rsplit(".", 1)[-1]
        return _IEEE_TPL.format(arn=arn)
    if doi.startswith("10.1145/"):
        return _ACM_TPL.format(doi=quote(doi, safe=""))
    if doi.startswith("10.1007/"):
        return _SPRINGER_TPL.format(doi=quote(doi, safe=""))
    if doi.startswith("10.1016/"):
        pii = doi.replace("10.1016/", "")
        return _ELSEVIER_TPL.format(pii=quote(pii, safe=""))
    return None


def download(doi: str, output_dir: Path, proxy: str | None = None) -> Path | None:
    url = doi_to_url(doi)
    if not url:
        logger.warning("Unsupported DOI prefix: %s", doi)
        return None

    filename = doi.replace("/", "_").replace(".", "_") + ".pdf"
    dest = output_dir / filename
    output_dir.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        logger.info("Already exists: %s", dest)
        return dest

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
    }

    client_kwargs = {
        "timeout": _TIMEOUT,
        "follow_redirects": True,
        "headers": headers,
    }
    if proxy:
        client_kwargs["proxy"] = proxy

    try:
        with httpx.Client(**client_kwargs) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                header = resp.read(5)
                if header != b"%PDF-":
                    logger.warning("Not a PDF from: %s", url[:80])
                    return None
                dest.write_bytes(header + resp.read())
                size_mb = dest.stat().st_size / (1024 * 1024)
                logger.info("Downloaded: %s (%.1f MB)", doi, size_mb)
                return dest
    except httpx.HTTPError as e:
        logger.error("Failed: %s - %s", doi, str(e)[:100])
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Download paywalled papers via campus network"
    )
    parser.add_argument(
        "input",
        help="DOI string or path to a file (one DOI per line)",
    )
    parser.add_argument(
        "--output", "-o",
        default="./campus_pdfs",
        help="Output directory (default: ./campus_pdfs)",
    )
    parser.add_argument(
        "--proxy", "-p",
        default=None,
        help="HTTP/HTTPS proxy URL, e.g. http://proxy.campus.edu:8080",
    )
    args = parser.parse_args()

    proxy = args.proxy
    # Auto-detect from config if available
    if not proxy:
        try:
            from paper_expert.core.config import PaperExpertConfig
            cfg = PaperExpertConfig.load()
            if cfg.campus.enabled:
                proxy = cfg.campus.https_proxy or cfg.campus.http_proxy or None
                if proxy:
                    logger.info("Using proxy from paper_expert config: %s", proxy)
        except Exception:
            pass

    output_dir = Path(args.output)

    # Is input a file or a DOI?
    inp = args.input.strip()
    if Path(inp).is_file():
        dois = Path(inp).read_text(encoding="utf-8").strip().splitlines()
    else:
        dois = [inp]

    dois = [d.strip() for d in dois if d.strip() and not d.strip().startswith("#")]
    if not dois:
        logger.error("No DOIs found")
        sys.exit(1)

    logger.info("Downloading %d papers to %s", len(dois), output_dir)
    success = 0
    for doi in dois:
        result = download(doi, output_dir, proxy=proxy)
        if result:
            success += 1

    logger.info("Done: %d/%d downloaded", success, len(dois))

    # Print import commands
    if success > 0:
        print("\nImport into Paper Expert:")
        for doi in dois:
            doi_clean = doi.strip()
            filename = doi_clean.replace("/", "_").replace(".", "_") + ".pdf"
            pdf = output_dir / filename
            if pdf.exists():
                print(f"  paper-expert add doi:{doi_clean} --pdf \"{pdf}\"")


if __name__ == "__main__":
    main()
