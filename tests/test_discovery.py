from youtube_wiki.discovery.youtube_api import (
    YouTubeDataApi,
    classify_broadcast,
    format_duration,
    parse_duration,
)
from youtube_wiki.models import BroadcastState, Channel


def test_duration_parsing_and_formatting():
    assert parse_duration("PT15M7S") == 907
    assert parse_duration("PT2H3M4S") == 7384
    assert parse_duration("P1DT2S") == 86402
    assert format_duration(907) == "15:07"
    assert format_duration(7384) == "2:03:04"


def test_broadcast_classification():
    assert classify_broadcast({"liveBroadcastContent": "live"}, {}) is BroadcastState.LIVE
    assert classify_broadcast({"liveBroadcastContent": "upcoming"}, {}) is BroadcastState.UPCOMING
    assert classify_broadcast(
        {"liveBroadcastContent": "none"}, {"actualEndTime": "2025-01-01T00:00:00Z"}
    ) is BroadcastState.COMPLETED
    assert classify_broadcast({"liveBroadcastContent": "none"}, None) is BroadcastState.NORMAL


class FakeApi(YouTubeDataApi):
    def __init__(self):
        super().__init__("key")
        self.calls = []

    def _get(self, resource, **params):
        self.calls.append((resource, params))
        if resource == "playlistItems":
            page = params.get("pageToken")
            if not page:
                return {
                    "items": [{"contentDetails": {"videoId": f"v{i}"}} for i in range(50)],
                    "nextPageToken": "next",
                }
            return {"items": [{"contentDetails": {"videoId": "v50"}}]}
        ids = params["id"].split(",")
        return {
            "items": [
                {
                    "id": video_id,
                    "snippet": {
                        "title": video_id,
                        "description": "description",
                        "publishedAt": "2025-01-01T00:00:00Z",
                        "liveBroadcastContent": "none",
                        "thumbnails": {"default": {"url": "https://image"}},
                    },
                    "contentDetails": {"duration": "PT1M"},
                }
                for video_id in ids
            ]
        }


def test_list_videos_paginates_and_batches_at_fifty():
    channel = Channel(
        channel_id="channel",
        title="Test",
        url="https://youtube.com/channel/channel",
        uploads_playlist_id="uploads",
    )
    api = FakeApi()
    videos = api.list_videos(channel)
    assert len(videos) == 51
    assert [call[0] for call in api.calls].count("playlistItems") == 2
    detail_calls = [call for call in api.calls if call[0] == "videos"]
    assert len(detail_calls) == 2
    assert len(detail_calls[0][1]["id"].split(",")) == 50

