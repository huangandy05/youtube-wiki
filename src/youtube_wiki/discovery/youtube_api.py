from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from youtube_wiki.discovery.channel_resolver import (
    ChannelReference,
    ChannelReferenceKind,
    parse_channel_reference,
)
from youtube_wiki.errors import (
    ApiKeyInvalid,
    ApiRequestError,
    ChannelNotFound,
    QuotaExceeded,
    UnsupportedUrl,
)
from youtube_wiki.models import BroadcastState, Channel, Video

API_BASE = "https://www.googleapis.com/youtube/v3"
DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?)?$"
)


def parse_duration(value: str) -> int:
    match = DURATION_RE.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid ISO-8601 duration: {value}")
    parts = {key: int(number or 0) for key, number in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def classify_broadcast(
    snippet: dict[str, Any], live_details: dict[str, Any] | None
) -> BroadcastState:
    state = snippet.get("liveBroadcastContent", "none")
    if state == "live":
        return BroadcastState.LIVE
    if state == "upcoming":
        return BroadcastState.UPCOMING
    if live_details and live_details.get("actualEndTime"):
        return BroadcastState.COMPLETED
    return BroadcastState.NORMAL


class YouTubeDataApi:
    def __init__(self, api_key: str, timeout: float = 20.0):
        self.api_key = api_key
        self.timeout = timeout

    def _get(self, resource: str, **params: str | int) -> dict[str, Any]:
        query = urlencode({**params, "key": self.api_key})
        try:
            with urlopen(f"{API_BASE}/{resource}?{query}", timeout=self.timeout) as response:  # noqa: S310
                return json.load(response)
        except HTTPError as error:
            try:
                payload = json.loads(error.read().decode("utf-8"))
                reasons = [
                    item.get("reason", "")
                    for item in payload.get("error", {}).get("errors", [])
                ]
                message = payload.get("error", {}).get("message", str(error))
            except (json.JSONDecodeError, UnicodeDecodeError):
                reasons, message = [], str(error)
            invalid_reasons = {"keyInvalid", "ipRefererBlocked", "accessNotConfigured"}
            if any(reason in invalid_reasons for reason in reasons):
                raise ApiKeyInvalid(
                    "The YouTube API key is invalid or not enabled for this API."
                ) from error
            if any(reason in {"quotaExceeded", "dailyLimitExceeded"} for reason in reasons):
                raise QuotaExceeded("The YouTube Data API quota has been exhausted.") from error
            raise ApiRequestError(message) from error
        except (URLError, TimeoutError) as error:
            raise ApiRequestError(f"Could not reach the YouTube Data API: {error}") from error

    def resolve_channel(self, value: str) -> Channel:
        reference = parse_channel_reference(value)
        if reference.kind is ChannelReferenceKind.CUSTOM:
            raise UnsupportedUrl(
                "Legacy /c/ channel URLs cannot be resolved by the Data API. "
                "Use the channel's current @handle URL instead."
            )
        return self._resolve_reference(reference)

    def _resolve_reference(self, reference: ChannelReference) -> Channel:
        filters = {
            ChannelReferenceKind.ID: {"id": reference.value},
            ChannelReferenceKind.HANDLE: {"forHandle": reference.value},
            ChannelReferenceKind.USERNAME: {"forUsername": reference.value},
        }
        payload = self._get(
            "channels",
            part="snippet,contentDetails",
            **filters[reference.kind],
        )
        items = payload.get("items", [])
        if not items:
            raise ChannelNotFound("No public YouTube channel matched that URL or handle.")
        item = items[0]
        snippet = item["snippet"]
        thumbnails = snippet.get("thumbnails", {})
        thumbnail = thumbnails.get("high") or thumbnails.get("medium") or thumbnails.get("default")
        handle = reference.value if reference.kind is ChannelReferenceKind.HANDLE else None
        return Channel(
            channel_id=item["id"],
            title=snippet["title"],
            handle=handle,
            url=f"https://www.youtube.com/channel/{item['id']}",
            uploads_playlist_id=item["contentDetails"]["relatedPlaylists"]["uploads"],
            thumbnail_url=thumbnail.get("url") if thumbnail else None,
        )

    def list_videos(self, channel: Channel) -> list[Video]:
        ids: list[str] = []
        page_token: str | None = None
        while True:
            params: dict[str, str | int] = {
                "part": "contentDetails",
                "playlistId": channel.uploads_playlist_id,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._get("playlistItems", **params)
            ids.extend(
                item["contentDetails"]["videoId"]
                for item in payload.get("items", [])
                if item.get("contentDetails", {}).get("videoId")
            )
            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        videos: list[Video] = []
        for start in range(0, len(ids), 50):
            payload = self._get(
                "videos",
                part="snippet,contentDetails,liveStreamingDetails",
                id=",".join(ids[start : start + 50]),
                maxResults=50,
            )
            for item in payload.get("items", []):
                snippet = item["snippet"]
                thumbnails = snippet.get("thumbnails", {})
                thumbnail = (
                    thumbnails.get("medium")
                    or thumbnails.get("high")
                    or thumbnails.get("default")
                )
                video_id = item["id"]
                videos.append(
                    Video(
                        video_id=video_id,
                        channel_id=channel.channel_id,
                        channel_title=channel.title,
                        title=snippet["title"],
                        url=f"https://www.youtube.com/watch?v={video_id}",
                        description=snippet.get("description", ""),
                        thumbnail_url=thumbnail.get("url") if thumbnail else None,
                        published_at=datetime.fromisoformat(
                            snippet["publishedAt"].replace("Z", "+00:00")
                        ),
                        duration_seconds=parse_duration(
                            item["contentDetails"].get("duration", "PT0S")
                        ),
                        broadcast_state=classify_broadcast(
                            snippet, item.get("liveStreamingDetails")
                        ),
                    )
                )
        order = {video_id: index for index, video_id in enumerate(ids)}
        videos.sort(key=lambda video: order.get(video.video_id, len(order)))
        return videos
