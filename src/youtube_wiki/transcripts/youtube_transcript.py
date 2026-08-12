from __future__ import annotations

from typing import Any

from youtube_wiki.errors import (
    ExtractionFailed,
    NoTranscriptAvailable,
    RateLimited,
    VideoUnavailable,
)
from youtube_wiki.models import CaptionSegment, TranscriptResult


class YouTubeTranscriptProvider:
    name = "youtube-transcript-api"

    def __init__(self, api: Any | None = None):
        if api is None:
            from youtube_transcript_api import YouTubeTranscriptApi

            api = YouTubeTranscriptApi()
        self.api = api

    def fetch(self, video_id: str, languages: tuple[str, ...]) -> TranscriptResult:
        try:
            transcript_list = self.api.list(video_id)
            try:
                transcript = transcript_list.find_manually_created_transcript(list(languages))
            except Exception as error:
                if error.__class__.__name__ != "NoTranscriptFound":
                    raise
                transcript = transcript_list.find_generated_transcript(list(languages))
            fetched = transcript.fetch()
            segments = [
                CaptionSegment(text=item.text, start=item.start, duration=item.duration)
                for item in fetched
            ]
            return TranscriptResult(
                video_id=video_id,
                segments=segments,
                language_code=transcript.language_code,
                language_name=transcript.language,
                is_generated=transcript.is_generated,
                provider=self.name,
            )
        except Exception as error:
            self._raise_domain_error(error)

    @staticmethod
    def _raise_domain_error(error: Exception) -> None:
        name = error.__class__.__name__
        if name in {"NoTranscriptFound", "TranscriptsDisabled", "NoTranscriptAvailable"}:
            raise NoTranscriptAvailable("No usable English captions are available.") from error
        if name in {"VideoUnavailable", "InvalidVideoId", "AgeRestricted"}:
            raise VideoUnavailable("The video is unavailable for transcript extraction.") from error
        if name in {"RequestBlocked", "IpBlocked", "TooManyRequests"}:
            raise RateLimited("YouTube blocked or throttled the transcript request.") from error
        raise ExtractionFailed(f"The primary transcript provider failed: {error}") from error
