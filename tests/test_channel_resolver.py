import pytest

from youtube_wiki.discovery.channel_resolver import ChannelReferenceKind, parse_channel_reference
from youtube_wiki.errors import InvalidChannelUrl, UnsupportedUrl


@pytest.mark.parametrize(
    ("value", "kind", "expected"),
    [
        ("@GoogleDevelopers", ChannelReferenceKind.HANDLE, "@GoogleDevelopers"),
        (
            "https://www.youtube.com/@GoogleDevelopers/videos",
            ChannelReferenceKind.HANDLE,
            "@GoogleDevelopers",
        ),
        (
            "https://youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw",
            ChannelReferenceKind.ID,
            "UC_x5XG1OV2P6uZZ5FSM9Ttw",
        ),
        (
            "youtube.com/user/GoogleDevelopers",
            ChannelReferenceKind.USERNAME,
            "GoogleDevelopers",
        ),
        ("https://youtube.com/c/OldName", ChannelReferenceKind.CUSTOM, "OldName"),
    ],
)
def test_parse_channel_reference(value, kind, expected):
    result = parse_channel_reference(value)
    assert result.kind is kind
    assert result.value == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://example.com/@channel",
        "https://youtube.com/",
    ],
)
def test_invalid_channel_reference(value):
    with pytest.raises(InvalidChannelUrl):
        parse_channel_reference(value)


def test_rejects_video_url():
    with pytest.raises(UnsupportedUrl, match="not supported yet"):
        parse_channel_reference("https://youtube.com/watch?v=abc")

