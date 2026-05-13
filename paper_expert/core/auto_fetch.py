"""Auto-Fetch Engine �?automatic paper retrieval on knowledge gaps.

When a QA answer has insufficient confidence, this module:
1. Derives search queries from the question + gap analysis
2. Searches external sources for new papers
3. Downloads and adds them to the knowledge base
4. Retries the question with the expanded library
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from paper_expert.core.qa_engine import QAEngine
from paper_expert.models.qa import QAAnswer

logger = logging.getLogger(__name__)

_SEARCH_QUERY_PROMPT = """Given a research question and an insufficient answer, generate 2-3 targeted search queries for finding relevant academic papers.

Question: {question}

Current answer (insufficient): {answer}

Generate search queries that would find papers to fill the knowledge gap. Return ONLY a JSON array of query strings.
Example: ["query 1", "query 2", "query 3"]
"""


@dataclass
class FetchProgress:
    """Progress state for an auto-fetch cycle."""

    iteration: int = 0
    max_iterations: int = 3
    total_papers_added: int = 0
    search_queries: list[str] = field(default_factory=list)
    message: str = ""


ProgressCallback = Callable[[FetchProgress], None]


async def derive_search_queries(
    question: str,
    insufficient_answer: str,
    ollama_model: str = "qwen2.5",
    ollama_url: str = "http://localhost:11434",
) -> list[str]:
    """Use LLM to generate search queries from the question and gap analysis.

    Falls back to using the original question if LLM is unavailable.
    """
    import json

    prompt = _SEARCH_QUERY_PROMPT.format(
        question=question,
        answer=insufficient_answer[:500] if insufficient_answer else "No answer available.",
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

            queries = json.loads(response_text)
            if isinstance(queries, list) and queries:
                return [str(q) for q in queries[:3]]
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        logger.info("LLM query derivation failed (%s), using original question", e)

    # Fallback: use the original question directly
    return [question]


class AutoFetcher:
    """Orchestrates the auto-fetch loop: ask �?assess �?search �?add �?retry."""

    def __init__(
        self,
        qa_engine: QAEngine,
        library: Any,  # Library (avoid circular import)
    ) -> None:
        self.qa_engine = qa_engine
        self.library = library

    async def ask_with_fetch(
        self,
        question: str,
        scope: str | None = None,
        fetch_limit: int = 5,
        max_iterations: int = 3,
        on_progress: ProgressCallback | None = None,
    ) -> QAAnswer:
        """Ask a question with automatic paper fetching on knowledge gaps.

        Args:
            question: The research question.
            scope: Optional scope filter for QA.
            fetch_limit: Max papers to fetch per iteration.
            max_iterations: Max fetch-retry iterations.
            on_progress: Optional callback for progress updates.

        Returns:
            QAAnswer �?the best answer after all iterations.
        """
        progress = FetchProgress(max_iterations=max_iterations)
        best_answer: QAAnswer | None = None

        for iteration in range(max_iterations + 1):
            progress.iteration = iteration

            # Step 1: Query existing knowledge base
            if on_progress:
                progress.message = (
                    "Querying knowledge base..."
                    if iteration == 0
                    else f"Retrying after adding {progress.total_papers_added} papers..."
                )
                on_progress(progress)

            answer = await self.qa_engine.ask(question, scope=scope)
            best_answer = answer

            # Step 2: Check if answer is sufficient
            if answer.is_sufficient or answer.error:
                break

            # Don't fetch on the last iteration �?just return what we have
            if iteration >= max_iterations:
                break

            # Step 3: Derive search queries
            if on_progress:
                progress.message = "Deriving search queries for knowledge gap..."
                on_progress(progress)

            model = "qwen2.5"
            if self.library.config and self.library.config.llm.local_model:
                model = self.library.config.llm.local_model.replace("ollama/", "")

            queries = await derive_search_queries(
                question=question,
                insufficient_answer=answer.answer,
                ollama_model=model,
            )
            progress.search_queries = queries

            # Step 4: Search and fetch papers
            papers_added_this_round = 0
            for query in queries:
                if on_progress:
                    progress.message = f"Searching: {query[:60]}..."
                    on_progress(progress)

                try:
                    results = await self.library.search(
                        query, limit=fetch_limit
                    )
                except Exception:
                    logger.warning("Search failed for query: %s", query[:60])
                    continue

                for result in results:
                    if result.in_library:
                        continue
                    if papers_added_this_round >= fetch_limit:
                        break

                    try:
                        from paper_expert.models.paper import PaperMetadata

                        metadata = PaperMetadata(
                            title=result.title,
                            authors=result.authors,
                            year=result.year,
                            venue=result.venue,
                            doi=result.doi,
                            arxiv_id=result.arxiv_id,
                            s2_paper_id=result.s2_paper_id,
                            citation_count=result.citation_count,
                            abstract=result.abstract,
                            open_access_pdf_url=result.open_access_pdf_url,
                            source=result.source,
                        )
                        paper = await self.library.add_paper(metadata, auto_classify=False)
                        if paper:
                            papers_added_this_round += 1
                    except Exception:
                        logger.warning("Failed to add paper from auto-fetch: %s",
                                       result.title[:60], exc_info=True)

                if papers_added_this_round >= fetch_limit:
                    break

            progress.total_papers_added += papers_added_this_round

            if on_progress:
                progress.message = f"Added {papers_added_this_round} papers (total: {progress.total_papers_added})"
                on_progress(progress)

            # If no new papers were added, no point retrying
            if papers_added_this_round == 0:
                logger.info("No new papers found, stopping auto-fetch")
                break

        if best_answer is None:
            best_answer = QAAnswer(
                question=question,
                error="Auto-fetch failed to produce an answer.",
            )

        return best_answer
