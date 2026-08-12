from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from youtube_wiki.errors import InvalidChannelUrl, UnsupportedUrl

CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{20,}$")
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}


class ChannelReferenceKind(StrEnum):
    ID = "id"
    HANDLE = "handle"
    USERNAME = "username"
    CUSTOM = "custom"


@dataclass(frozen=True)
class ChannelReference:
    kind: ChannelReferenceKind
    value: str


def parse_channel_reference(value: str) -> ChannelReference:
    raw = value.strip()
    if not raw:
        raise InvalidChannelUrl("Enter a YouTube channel URL, handle, or channel ID.")
    if raw.startswith("@") and len(raw) > 1:
        return ChannelReference(ChannelReferenceKind.HANDLE, raw)
    if CHANNEL_ID_RE.fullmatch(raw):
        return ChannelReference(ChannelReferenceKind.ID, raw)

    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host not in ALLOWED_HOSTS:
        raise InvalidChannelUrl("Only youtube.com channel URLs are supported.")
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        raise InvalidChannelUrl("The URL does not identify a YouTube channel.")
    if parts[0] in {"watch", "playlist", "shorts", "live"}:
        raise UnsupportedUrl("Video and playlist URLs are not supported yet; enter a channel URL.")
    if parts[0].startswith("@"):
        return ChannelReference(ChannelReferenceKind.HANDLE, parts[0])
    if len(parts) < 2:
        raise InvalidChannelUrl("The URL does not identify a supported YouTube channel.")
    value = parts[1]
    if parts[0] == "channel" and CHANNEL_ID_RE.fullmatch(value):
        return ChannelReference(ChannelReferenceKind.ID, value)
    if parts[0] == "user":
        return ChannelReference(ChannelReferenceKind.USERNAME, value)
    if parts[0] == "c":
        return ChannelReference(ChannelReferenceKind.CUSTOM, value)
    raise UnsupportedUrl("This YouTube channel URL format is not supported.")

