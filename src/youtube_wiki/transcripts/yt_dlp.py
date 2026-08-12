from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from youtube_wiki.errors import (
    ExtractionFailed,
    NoTranscriptAvailable,
    RateLimited,
    VideoUnavailable,
)
from youtube_wiki.models import TranscriptResult
from youtube_wiki.transcripts.vtt import parse_vtt


class _QuietLogger:
    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


class YtDlpTranscriptProvider:
    name = "yt-dlp"

    def fetch(self, video_id: str, languages: tuple[str, ...]) -> TranscriptResult:
        try:
            from yt_dlp import YoutubeDL
            from yt_dlp.utils import DownloadError
        except ImportError as error:
            raise ExtractionFailed("yt-dlp is not installed.") from error

        url = f"https://www.youtube.com/watch?v={video_id}"
        with tempfile.TemporaryDirectory(prefix="youtube-wiki-subs-") as directory:
            output = str(Path(directory) / "%(id)s.%(ext)s")
            options: dict[str, Any] = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": list(languages) + ["en.*"],
                "subtitlesformat": "vtt",
                "outtmpl": output,
                "quiet": True,
                "no_warnings": True,
                "logger": _QuietLogger(),
                "noplaylist": True,
            }
            try:
                with YoutubeDL(options) as downloader:
                    info = downloader.extract_info(url, download=True)
            except DownloadError as error:
                self._raise_download_error(error)

            files = sorted(Path(directory).glob("*.vtt"))
            if not files:
                raise NoTranscriptAvailable("yt-dlp found no usable English captions.")
            subtitle_file = files[0]
            language_code = _language_from_filename(subtitle_file, video_id)
            subtitles = info.get("subtitles", {}) if info else {}
            is_generated = language_code not in subtitles
            content = subtitle_file.read_text(encoding="utf-8")
            return TranscriptResult(
                video_id=video_id,
                segments=parse_vtt(content),
                language_code=language_code,
                language_name=language_code,
                is_generated=is_generated,
                provider=self.name,
            )

    @staticmethod
    def _raise_download_error(error: Exception) -> None:
        message = str(error)
        lowered = message.lower()
        if "private video" in lowered or "video unavailable" in lowered:
            raise VideoUnavailable("The video is unavailable for transcript extraction.") from error
        if "429" in lowered or "too many requests" in lowered:
            raise RateLimited("YouTube throttled the subtitle request.") from error
        if "subtitle" in lowered or "caption" in lowered:
            raise NoTranscriptAvailable("yt-dlp could not retrieve English captions.") from error
        raise ExtractionFailed(f"The yt-dlp fallback failed: {message}") from error


def _language_from_filename(path: Path, video_id: str) -> str:
    prefix = f"{video_id}."
    name = path.name
    return name[len(prefix) : -len(".vtt")] if name.startswith(prefix) else "en"
