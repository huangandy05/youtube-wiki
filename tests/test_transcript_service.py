from datetime import UTC, datetime

import pytest

from youtube_wiki.errors import ExtractionFailed, NoTranscriptAvailable, VideoUnavailable
from youtube_wiki.models import CaptionSegment, TranscriptResult
from youtube_wiki.transcripts.service import TranscriptService


class Provider:
    name = "provider"

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def fetch(self, video_id, languages):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def result():
    return TranscriptResult(
        video_id="video",
        segments=[CaptionSegment(text="hello", start=0, duration=1)],
        language_code="en",
        language_name="English",
        is_generated=False,
        provider="provider",
        retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
    )


def test_primary_success_does_not_call_fallback():
    primary, fallback = Provider(result()), Provider(result())
    assert TranscriptService(primary, fallback).get_transcript("video") == result()
    assert fallback.calls == 0


def test_primary_failure_uses_fallback():
    primary = Provider(error=NoTranscriptAvailable("none"))
    fallback = Provider(result())
    assert TranscriptService(primary, fallback).get_transcript("video") == result()
    assert fallback.calls == 1


def test_video_unavailable_does_not_call_fallback():
    fallback = Provider(result())
    with pytest.raises(VideoUnavailable):
        TranscriptService(Provider(error=VideoUnavailable("gone")), fallback).get_transcript(
            "video"
        )
    assert fallback.calls == 0


def test_both_report_no_captions_as_unavailable():
    service = TranscriptService(
        Provider(error=NoTranscriptAvailable("primary")),
        Provider(error=NoTranscriptAvailable("fallback")),
    )
    with pytest.raises(NoTranscriptAvailable, match="either provider"):
        service.get_transcript("video")


def test_unexpected_provider_failures_expose_combined_error():
    service = TranscriptService(
        Provider(error=ExtractionFailed("primary")),
        Provider(error=ExtractionFailed("fallback")),
    )
    with pytest.raises(ExtractionFailed, match="No provider"):
        service.get_transcript("video")
