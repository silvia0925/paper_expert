"""Pydantic models for monitoring and notification."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WatchTopic(BaseModel):
    """A research direction to monitor for new papers."""

    id: int | None = None
    name: str = ""
    queries: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    fetch_limit: int = 10
    notify_channels: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: str | None = None
    last_run_at: str | None = None

    @classmethod
    def from_db_row(cls, row: dict) -> WatchTopic:
        return cls(
            id=row["id"],
            name=row["name"],
            queries=row.get("queries", []),
            sources=row.get("sources", []),
            fetch_limit=row.get("fetch_limit", 10),
            notify_channels=row.get("notify_channels", []),
            is_active=bool(row.get("is_active", 1)),
            created_at=row.get("created_at"),
            last_run_at=row.get("last_run_at"),
        )


class MonitorResult(BaseModel):
    """Result of a single watch topic monitoring run."""

    watch_id: int
    topic_name: str = ""
    queries_searched: list[str] = Field(default_factory=list)
    papers_found: int = 0
    papers_added: int = 0
    new_papers: list[dict] = Field(default_factory=list)
    notify_results: dict[str, bool] = Field(default_factory=dict)
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.error is None


class MonitorRunResult(BaseModel):
    """Result of running all watch topics at once."""

    run_at: str = ""
    topics_checked: int = 0
    results: list[MonitorResult] = Field(default_factory=list)
    total_found: int = 0
    total_added: int = 0
