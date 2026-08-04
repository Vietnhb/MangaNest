from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MangaRun(Base):
    """Persisted pipeline output and LoRA-candidate metadata."""

    __tablename__ = "manga_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    idea: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False)
    lora_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    story_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    layout_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    generation_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    render_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    critique_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
class StorySeries(Base):
    """Canonical, versioned memory shared by every episode in a series."""

    __tablename__ = "story_series"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    premise: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visual_style: Mapped[str] = mapped_column(Text, nullable=False, default="")
    story_bible: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    continuity_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class StoryEpisode(Base):
    """Immutable AI output plus a separately editable page/panel overlay."""

    __tablename__ = "story_episodes"
    __table_args__ = (UniqueConstraint("series_id", "episode_number", name="uq_series_episode_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    series_id: Mapped[str] = mapped_column(ForeignKey("story_series.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True, index=True)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    story_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    layout_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    generation_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    render_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    editor_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    continuity_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
