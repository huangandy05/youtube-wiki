from __future__ import annotations

import re

from youtube_wiki.errors import ExtractionFailed
from youtube_wiki.models import CaptionSegment

TIMING_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})\s+-->\s+"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})"
)
VTT_TAG_RE = re.compile(r"<[^>]+>")


def _seconds(timestamp: str) -> float:
    parts = timestamp.replace(",", ".").split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_vtt(content: str) -> list[CaptionSegment]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", normalized)
    segments: list[CaptionSegment] = []
    previous_text = ""
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next(
            (index for index, line in enumerate(lines) if TIMING_RE.search(line)), None
        )
        if timing_index is None:
            continue
        match = TIMING_RE.search(lines[timing_index])
        if match is None:
            continue
        text = " ".join(lines[timing_index + 1 :])
        text = VTT_TAG_RE.sub("", text).strip()
        if not text:
            continue
        # YouTube VTT often repeats a growing caption window. Keep only the new suffix.
        if previous_text and text.startswith(previous_text):
            text = text[len(previous_text) :].strip()
        elif previous_text and previous_text.endswith(text):
            continue
        if not text:
            continue
        start, end = _seconds(match.group("start")), _seconds(match.group("end"))
        segments.append(CaptionSegment(text=text, start=start, duration=max(0, end - start)))
        previous_text = VTT_TAG_RE.sub("", " ".join(lines[timing_index + 1 :])).strip()
    if not segments:
        raise ExtractionFailed("The downloaded subtitle file contained no readable captions.")
    return segments
