from youtube_wiki.models import CaptionSegment
from youtube_wiki.processing.cleaner import clean_transcript


def segment(text, start, duration=1):
    return CaptionSegment(text=text, start=start, duration=duration)


def test_cleaner_normalizes_and_paragraphs_conservatively():
    result = clean_transcript(
        [
            segment("Hello &amp; <i>welcome</i>", 0),
            segment("[Music]", 1),
            segment("to this video .", 2),
            segment("to this video .", 3),
            segment("New thought", 8),
        ]
    )
    assert result == "Hello & welcome to this video.\n\nNew thought\n"


def test_cleaner_wraps_long_paragraphs():
    result = clean_transcript(
        [segment("one", 0), segment("two", 1), segment("three", 2)],
        max_paragraph_chars=7,
    )
    assert result == "one two\n\nthree\n"

