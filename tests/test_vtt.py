from youtube_wiki.transcripts.vtt import parse_vtt

SAMPLE = """WEBVTT

00:00:00.000 --> 00:00:02.000
Hello

00:00:01.000 --> 00:00:03.000
Hello world

00:00:04.000 --> 00:00:05.000
<c>Again</c>
"""


def test_parse_vtt_removes_rolling_prefixes():
    segments = parse_vtt(SAMPLE)
    assert [item.text for item in segments] == ["Hello", "world", "Again"]
    assert segments[0].duration == 2

