from __future__ import annotations

import html
import re

from youtube_wiki.models import CaptionSegment

TAG_RE = re.compile(r"<[^>]+>")
MARKER_RE = re.compile(
    r"^\s*[\[(](?:music|applause|laughter|laughs|cheering|silence)[\]).]\s*$",
    re.IGNORECASE,
)
SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+([,.;:!?])")
MULTISPACE_RE = re.compile(r"[ \t]+")


def _normalize_segment(text: str) -> str:
    text = html.unescape(TAG_RE.sub("", text)).replace("\n", " ")
    return MULTISPACE_RE.sub(" ", text).strip()


def clean_transcript(
    segments: list[CaptionSegment],
    paragraph_gap: float = 3.5,
    max_paragraph_chars: int = 900,
) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    current_length = 0
    previous_text: str | None = None
    previous_end: float | None = None

    for segment in segments:
        text = _normalize_segment(segment.text)
        if not text or MARKER_RE.fullmatch(text) or text == previous_text:
            continue
        gap = segment.start - previous_end if previous_end is not None else 0
        addition_length = len(text) + (1 if current else 0)
        if current and (
            gap >= paragraph_gap or current_length + addition_length > max_paragraph_chars
        ):
            paragraphs.append(_join_fragments(current))
            current, current_length = [], 0
            addition_length = len(text)
        current.append(text)
        current_length += addition_length
        previous_text = text
        previous_end = segment.start + segment.duration

    if current:
        paragraphs.append(_join_fragments(current))
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph).strip() + "\n"


def _join_fragments(fragments: list[str]) -> str:
    text = " ".join(fragments)
    return SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", MULTISPACE_RE.sub(" ", text)).strip()
