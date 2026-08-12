from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from youtube_wiki.models import Channel, ProcessingStatus, Video


class StateRepository:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    handle TEXT,
                    url TEXT NOT NULL,
                    uploads_playlist_id TEXT NOT NULL,
                    thumbnail_url TEXT,
                    refreshed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    channel_title TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    description TEXT NOT NULL,
                    thumbnail_url TEXT,
                    published_at TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    broadcast_state TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    FOREIGN KEY(channel_id) REFERENCES channels(channel_id)
                );
                CREATE TABLE IF NOT EXISTS extractions (
                    video_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    output_path TEXT,
                    provider TEXT,
                    language_code TEXT,
                    transcript_type TEXT,
                    retrieved_at TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    FOREIGN KEY(video_id) REFERENCES videos(video_id)
                );
                """
            )
            connection.execute(
                """
                UPDATE extractions
                SET status = ?, error_code = 'interrupted',
                    error_message = 'The previous extraction was interrupted.'
                WHERE status = ?
                """,
                (ProcessingStatus.FAILED, ProcessingStatus.PROCESSING),
            )

    def upsert_channel(self, channel: Channel) -> None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO channels VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    title=excluded.title, handle=excluded.handle, url=excluded.url,
                    uploads_playlist_id=excluded.uploads_playlist_id,
                    thumbnail_url=excluded.thumbnail_url, refreshed_at=excluded.refreshed_at
                """,
                (
                    channel.channel_id,
                    channel.title,
                    channel.handle,
                    channel.url,
                    channel.uploads_playlist_id,
                    channel.thumbnail_url,
                    now,
                ),
            )

    def upsert_videos(self, videos: list[Video]) -> None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    channel_id=excluded.channel_id, channel_title=excluded.channel_title,
                    title=excluded.title, url=excluded.url, description=excluded.description,
                    thumbnail_url=excluded.thumbnail_url, published_at=excluded.published_at,
                    duration_seconds=excluded.duration_seconds,
                    broadcast_state=excluded.broadcast_state,
                    discovered_at=excluded.discovered_at
                """,
                [
                    (
                        video.video_id,
                        video.channel_id,
                        video.channel_title,
                        video.title,
                        video.url,
                        video.description,
                        video.thumbnail_url,
                        video.published_at.isoformat(),
                        video.duration_seconds,
                        video.broadcast_state,
                        now,
                    )
                    for video in videos
                ],
            )

    def statuses(self, video_ids: list[str]) -> dict[str, ProcessingStatus]:
        if not video_ids:
            return {}
        placeholders = ",".join("?" for _ in video_ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT video_id, status FROM extractions WHERE video_id IN ({placeholders})",  # noqa: S608
                video_ids,
            ).fetchall()
        return {row["video_id"]: ProcessingStatus(row["status"]) for row in rows}

    def set_processing(self, video_id: str) -> None:
        self._set_status(video_id, ProcessingStatus.PROCESSING)

    def set_extracted(
        self,
        video_id: str,
        output_path: Path,
        provider: str,
        language_code: str,
        is_generated: bool,
        retrieved_at: datetime,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO extractions (
                    video_id, status, output_path, provider, language_code,
                    transcript_type, retrieved_at, error_code, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                ON CONFLICT(video_id) DO UPDATE SET
                    status=excluded.status, output_path=excluded.output_path,
                    provider=excluded.provider, language_code=excluded.language_code,
                    transcript_type=excluded.transcript_type,
                    retrieved_at=excluded.retrieved_at, error_code=NULL, error_message=NULL
                """,
                (
                    video_id,
                    ProcessingStatus.EXTRACTED,
                    str(output_path),
                    provider,
                    language_code,
                    "generated" if is_generated else "manual",
                    retrieved_at.isoformat(),
                ),
            )

    def set_error(self, video_id: str, unavailable: bool, error: Exception) -> None:
        status = ProcessingStatus.UNAVAILABLE if unavailable else ProcessingStatus.FAILED
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO extractions (video_id, status, error_code, error_message)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    status=excluded.status, error_code=excluded.error_code,
                    error_message=excluded.error_message
                """,
                (video_id, status, error.__class__.__name__, str(error)[:1000]),
            )

    def _set_status(self, video_id: str, status: ProcessingStatus) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO extractions (video_id, status) VALUES (?, ?)
                ON CONFLICT(video_id) DO UPDATE SET status=excluded.status
                """,
                (video_id, status),
            )
