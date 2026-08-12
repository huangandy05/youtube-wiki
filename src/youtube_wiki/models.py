from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class BroadcastState(StrEnum):
    NORMAL = "normal"
    UPCOMING = "upcoming"
    LIVE = "live"
    COMPLETED = "completed"


class ProcessingStatus(StrEnum):
    UNPROCESSED = "unprocessed"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class Channel(BaseModel):
    channel_id: str
    title: str
    handle: str | None = None
    url: str
    uploads_playlist_id: str
    thumbnail_url: str | None = None


class Video(BaseModel):
    video_id: str
    channel_id: str
    channel_title: str
    title: str
    url: str
    description: str = ""
    thumbnail_url: str | None = None
    published_at: datetime
    duration_seconds: int = Field(ge=0)
    broadcast_state: BroadcastState = BroadcastState.NORMAL
    processing_status: ProcessingStatus = ProcessingStatus.UNPROCESSED


class CaptionSegment(BaseModel):
    text: str
    start: float = Field(ge=0)
    duration: float = Field(ge=0)


class TranscriptResult(BaseModel):
    video_id: str
    segments: list[CaptionSegment]
    language_code: str
    language_name: str
    is_generated: bool
    provider: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

