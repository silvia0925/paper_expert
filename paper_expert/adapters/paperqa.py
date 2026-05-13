"""PaperQA2 adapter that wraps Docs with persistence and config support."""

from __future__ import annotations

import logging
import pickle
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from paper_expert.core.config import PaperExpertConfig

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from paperqa import Docs as PaperQADocs
    from paperqa import Settings as PaperQASettings
except ImportError:  # pragma: no cover - executed when paperqa missing
    PaperQADocs = None  # type: ignore[assignment]
    PaperQASettings = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - typing only
    from paperqa import Docs as DocsType
    from paperqa import Settings as SettingsType
else:
    DocsType = Any
    SettingsType = Any


def _paperqa_available() -> bool:
    """Return True if the paperqa dependency is importable."""

    return PaperQADocs is not None and PaperQASettings is not None


class PaperQAAdapter:
    """Encapsulates PaperQA2 Docs lifecycle, persistence, and configuration."""

    def __init__(
        self,
        config: PaperExpertConfig | None = None,
        *,
        settings_overrides: Mapping[str, object] | None = None,
    ) -> None:
        self.config: PaperExpertConfig = config or PaperExpertConfig.load()
        self._vectors_dir: Path = self.config.library_path / "vectors"
        self._docs_path: Path = self._vectors_dir / "docs.pkl"
        self._docs: DocsType | None = None
        self._settings: SettingsType | None = None

        # Set env vars for litellm (used by PaperQA2 internally)
        self._setup_llm_env()

        if not _paperqa_available():
            logger.warning(
                "paperqa is not installed. PaperQAAdapter will remain inactive until the dependency is available."
            )
            return

        self._settings = self._build_settings(settings_overrides)
        self._docs = self.load()

    @property
    def available(self) -> bool:
        """Return True if PaperQA is installed and configured."""

        return _paperqa_available() and self._settings is not None

    def _setup_llm_env(self) -> None:
        """Set environment variables for litellm proxy support.

        PaperQA2 uses litellm internally, which reads OPENAI_API_KEY
        and OPENAI_API_BASE from environment. We set these from our config
        so users don't have to manage env vars manually.
        """
        import os

        if self.config.api_keys.openai and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = self.config.api_keys.openai

        if self.config.llm.api_base and not os.environ.get("OPENAI_API_BASE"):
            os.environ["OPENAI_API_BASE"] = self.config.llm.api_base

    def _build_settings(
        self, overrides: Mapping[str, object] | None = None
    ) -> SettingsType | None:
        if not _paperqa_available() or PaperQASettings is None:
            return None

        llm_config = self.config.llm

        settings_kwargs: dict[str, Any] = {}

        # LLM settings �?only set if non-default (litellm format like "ollama/qwen2.5")
        if llm_config.cloud_model:
            settings_kwargs["llm"] = llm_config.cloud_model
            settings_kwargs["summary_llm"] = llm_config.cloud_model
        elif llm_config.local_model:
            settings_kwargs["llm"] = llm_config.local_model
            settings_kwargs["summary_llm"] = llm_config.local_model

        if llm_config.embedding_model:
            settings_kwargs["embedding"] = llm_config.embedding_model

        if overrides:
            for key, value in overrides.items():
                settings_kwargs[key] = value

        try:
            return PaperQASettings(**settings_kwargs)
        except Exception:
            logger.debug(
                "Failed to create PaperQA Settings with custom config, trying defaults.",
                exc_info=True,
            )
            try:
                # PaperQA2 Settings uses pydantic-settings which reads env vars.
                # Environment variables (e.g. AGENT=1) can conflict. Isolate by
                # temporarily clearing problematic env vars.
                import os

                agent_val = os.environ.pop("AGENT", None)
                try:
                    return PaperQASettings()
                finally:
                    if agent_val is not None:
                        os.environ["AGENT"] = agent_val
            except Exception:
                logger.info(
                    "PaperQA Settings unavailable. Paper vectorization disabled. "
                    "Search and metadata features still work."
                )
                return None

    def _library_name(self) -> str:
        return self.config.library_path.name or "paper_expert-library"

    def _new_docs(self) -> DocsType:
        if PaperQADocs is None:  # pragma: no cover - defensive
            raise RuntimeError("paperqa Docs class is unavailable")
        return cast(DocsType, PaperQADocs(name=self._library_name()))

    def _ensure_docs(self) -> DocsType:
        if self._docs is None:
            self._docs = self._new_docs()
        return self._docs

    async def add_document(self, pdf_path: Path, doc_name: str | None = None) -> bool:
        """Parse, chunk, and vectorize a PDF via Docs.aadd, then persist state."""

        if not self.available:
            logger.error("PaperQAAdapter is unavailable; cannot add document.")
            return False

        if not pdf_path.is_file():
            logger.error("PDF path does not exist: %s", pdf_path)
            return False

        docs = self._ensure_docs()

        try:
            result = await docs.aadd(
                pdf_path,
                docname=doc_name,
                settings=self._settings,
            )
        except Exception:
            logger.exception("Failed to ingest document with PaperQA: %s", pdf_path)
            return False

        if result:
            self.save()
            return True
        return False

    async def rebuild_index(self, pdf_paths: list[Path]) -> int:
        """Rebuild the Docs collection from scratch using provided PDFs."""

        if not self.available:
            logger.error("PaperQAAdapter is unavailable; cannot rebuild index.")
            return 0

        docs = self._new_docs()
        self._docs = docs

        added = 0
        for pdf_path in pdf_paths:
            if not pdf_path.is_file():
                logger.warning("Skipping missing PDF during rebuild: %s", pdf_path)
                continue
            try:
                result = await docs.aadd(pdf_path, settings=self._settings)
            except Exception:
                logger.exception("Failed to ingest document during rebuild: %s", pdf_path)
                continue
            if result:
                added += 1

        self.save()
        return added

    def save(self) -> None:
        """Serialize the Docs object to disk for persistence."""

        if not self.available:
            return

        docs = self._ensure_docs()
        self._vectors_dir.mkdir(parents=True, exist_ok=True)

        try:
            with self._docs_path.open("wb") as fh:
                pickle.dump(docs, fh)
        except Exception:
            logger.exception("Failed to persist PaperQA docs to %s", self._docs_path)

    def load(self) -> DocsType | None:
        """Load Docs from disk if available, otherwise create a fresh collection."""

        if not _paperqa_available() or PaperQADocs is None:
            return None

        if not self._docs_path.exists():
            return self._new_docs()

        try:
            with self._docs_path.open("rb") as fh:
                docs_candidate = pickle.load(fh)
        except Exception:
            logger.exception(
                "Failed to load PaperQA docs from %s. Starting with a fresh collection.",
                self._docs_path,
            )
            return self._new_docs()

        if PaperQADocs is not None and not isinstance(docs_candidate, PaperQADocs):
            logger.warning(
                "Serialized docs at %s are not a PaperQA Docs instance. Resetting.",
                self._docs_path,
            )
            return self._new_docs()

        return cast(DocsType, docs_candidate)

    # ── Query Operations (Phase 2) ──────────────────────────

    async def query(
        self,
        question: str,
        settings_override: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        """Ask a question against the Docs collection.

        Returns a dict with keys: answer, question, references, contexts, cost.
        Returns an error dict if PaperQA2 is unavailable.
        """
        if not self.available:
            return {
                "answer": "",
                "question": question,
                "references": "",
                "contexts": [],
                "cost": 0.0,
                "error": "PaperQA2 is not available. Install paper-qa and configure a cloud LLM.",
            }

        docs = self._ensure_docs()
        if not docs.docs:
            return {
                "answer": "",
                "question": question,
                "references": "",
                "contexts": [],
                "cost": 0.0,
                "error": "No documents in the knowledge base. Add papers first.",
            }

        settings = self._settings
        if settings_override and PaperQASettings is not None:
            try:
                override_kwargs: dict[str, Any] = {}
                if self._settings is not None:
                    # Start from current settings dict
                    override_kwargs = self._settings.model_dump()
                override_kwargs.update(settings_override)
                settings = PaperQASettings(**override_kwargs)
            except Exception:
                logger.debug("Failed to apply settings override, using defaults")

        try:
            answer = await docs.aquery(question, settings=settings)
        except Exception:
            logger.exception("PaperQA2 query failed for: %s", question[:80])
            return {
                "answer": "",
                "question": question,
                "references": "",
                "contexts": [],
                "cost": 0.0,
                "error": "Query failed. Check LLM configuration and API keys.",
            }

        # Convert PaperQA2 Answer to a plain dict we control
        contexts = []
        if hasattr(answer, "contexts"):
            for ctx in answer.contexts:
                ctx_dict: dict[str, Any] = {
                    "text": getattr(ctx, "text", str(ctx)),
                    "score": getattr(ctx, "score", 0.0),
                    "doc_name": getattr(ctx, "doc", {}).get("docname", "")
                    if isinstance(getattr(ctx, "doc", None), dict)
                    else getattr(getattr(ctx, "doc", None), "docname", ""),
                }
                contexts.append(ctx_dict)

        return {
            "answer": getattr(answer, "answer", str(answer)),
            "question": question,
            "references": getattr(answer, "references", ""),
            "contexts": contexts,
            "cost": getattr(answer, "cost", 0.0),
            "error": None,
        }

    async def summarize(
        self,
        paper_title: str,
        settings_override: Mapping[str, object] | None = None,
    ) -> str:
        """Generate a structured summary for a specific paper.

        Uses PaperQA2 query to ask for a summary of the named paper.
        Returns the summary text, or an error message.
        """
        prompt = (
            f"Provide a structured summary of the paper '{paper_title}'. "
            "Include: (1) Objective, (2) Method, (3) Key findings, (4) Limitations. "
            "Only use information from this paper."
        )
        result = await self.query(prompt, settings_override=settings_override)

        if result.get("error"):
            return f"Summary unavailable: {result['error']}"

        return result.get("answer", "No summary generated.")
