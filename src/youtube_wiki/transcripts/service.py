from __future__ import annotations

from typing import Protocol

from youtube_wiki.errors import (
    ExtractionFailed,
    NoTranscriptAvailable,
    VideoUnavailable,
    YouTubeWikiError,
)
from youtube_wiki.models import TranscriptResult
from youtube_wiki.transcripts.youtube_transcript import YouTubeTranscriptProvider
from youtube_wiki.transcripts.yt_dlp import YtDlpTranscriptProvider

DEFAULT_LANGUAGES = ("en", "en-US", "en-GB")


class TranscriptProvider(Protocol):
    name: str

    def fetch(self, video_id: str, languages: tuple[str, ...]) -> TranscriptResult: ...


class TranscriptService:
    def __init__(
        self,
        primary: TranscriptProvider | None = None,
        fallback: TranscriptProvider | None = None,
    ):
        self.primary = primary or YouTubeTranscriptProvider()
        self.fallback = fallback or YtDlpTranscriptProvider()

    def get_transcript(
        self, video_id: str, languages: tuple[str, ...] = DEFAULT_LANGUAGES
    ) -> TranscriptResult:
        try:
            return self.primary.fetch(video_id, languages)
        except VideoUnavailable:
            raise
        except YouTubeWikiError as primary_error:
            try:
                return self.fallback.fetch(video_id, languages)
            except VideoUnavailable:
                raise
            except NoTranscriptAvailable as fallback_error:
                raise NoTranscriptAvailable(
                    "No usable English captions were available from either provider."
                ) from fallback_error
            except YouTubeWikiError as fallback_error:
                raise ExtractionFailed(
                    f"No provider could retrieve this transcript. "
                    f"Primary: {primary_error} Fallback: {fallback_error}"
                ) from fallback_error
