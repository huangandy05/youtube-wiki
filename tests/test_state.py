from datetime import UTC, datetime

from youtube_wiki.models import Channel, ProcessingStatus, Video
from youtube_wiki.storage.state import StateRepository


def test_state_round_trip(tmp_path):
    repository = StateRepository(tmp_path / "state.sqlite3")
    channel = Channel(
        channel_id="channel",
        title="Channel",
        url="https://youtube.com/channel/channel",
        uploads_playlist_id="uploads",
    )
    video = Video(
        video_id="video",
        channel_id="channel",
        channel_title="Channel",
        title="Video",
        url="https://youtube.com/watch?v=video",
        published_at=datetime.now(UTC),
        duration_seconds=10,
    )
    repository.upsert_channel(channel)
    repository.upsert_videos([video])
    assert repository.statuses(["video"]) == {}
    repository.set_processing("video")
    assert repository.statuses(["video"])["video"] is ProcessingStatus.PROCESSING
    repository.set_extracted(
        "video", tmp_path / "video.md", "test", "en", False, datetime.now(UTC)
    )
    assert repository.statuses(["video"])["video"] is ProcessingStatus.EXTRACTED


def test_state_recovers_interrupted_extraction(tmp_path):
    path = tmp_path / "state.sqlite3"
    repository = StateRepository(path)
    repository.set_processing("video")
    recovered = StateRepository(path)
    assert recovered.statuses(["video"])["video"] is ProcessingStatus.FAILED

