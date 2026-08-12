from datetime import UTC, datetime

import yaml

from youtube_wiki.models import BroadcastState, CaptionSegment, TranscriptResult, Video
from youtube_wiki.storage.markdown import MarkdownWriter, slugify


def video():
    return Video(
        video_id="abc123",
        channel_id="channel-id",
        channel_title="A / Channel",
        title='A: "Title"?',
        url="https://youtube.com/watch?v=abc123",
        description="A description: with YAML characters",
        published_at=datetime(2025, 1, 1, tzinfo=UTC),
        duration_seconds=60,
        broadcast_state=BroadcastState.NORMAL,
    )


def transcript():
    return TranscriptResult(
        video_id="abc123",
        segments=[CaptionSegment(text="Hello", start=0, duration=1)],
        language_code="en",
        language_name="English",
        is_generated=False,
        provider="test",
    )


def test_slugify_handles_unicode_and_empty_values():
    assert slugify("Café Talk", "fallback") == "cafe-talk"
    assert slugify("東京", "fallback") == "fallback"


def test_markdown_writer_creates_parseable_frontmatter(tmp_path):
    writer = MarkdownWriter(tmp_path)
    path = writer.write(video(), transcript(), "Hello world\n")
    assert path.name == "a-title--abc123.md"
    content = path.read_text(encoding="utf-8")
    _, frontmatter, body = content.split("---", 2)
    metadata = yaml.safe_load(frontmatter)
    assert metadata["youtube_id"] == "abc123"
    assert metadata["description"] == "A description: with YAML characters"
    assert "# A: \"Title\"?" in body


def test_markdown_writer_does_not_replace_by_default(tmp_path):
    writer = MarkdownWriter(tmp_path)
    writer.write(video(), transcript(), "First")
    try:
        writer.write(video(), transcript(), "Second")
    except FileExistsError:
        pass
    else:
        raise AssertionError("Expected FileExistsError")
    assert "First" in writer.path_for(video()).read_text()

