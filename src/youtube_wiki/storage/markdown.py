from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from pathlib import Path

import yaml

from youtube_wiki.models import TranscriptResult, Video

UNSAFE_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str, fallback: str, max_length: int = 80) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    slug = UNSAFE_RE.sub("-", normalized).strip("-")[:max_length].rstrip("-")
    return slug or fallback


class MarkdownWriter:
    def __init__(self, raw_dir: Path):
        self.raw_dir = raw_dir

    def path_for(self, video: Video) -> Path:
        channel_slug = slugify(video.channel_title, video.channel_id)
        title_slug = slugify(video.title, video.video_id)
        return self.raw_dir / channel_slug / f"{title_slug}--{video.video_id}.md"

    def exists(self, video: Video) -> bool:
        return self.path_for(video).exists()

    def write(
        self,
        video: Video,
        transcript: TranscriptResult,
        cleaned_text: str,
        replace: bool = False,
    ) -> Path:
        destination = self.path_for(video)
        if destination.exists() and not replace:
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "youtube_id": video.video_id,
            "title": video.title,
            "channel_id": video.channel_id,
            "channel": video.channel_title,
            "url": video.url,
            "published_at": video.published_at.isoformat(),
            "duration_seconds": video.duration_seconds,
            "thumbnail_url": video.thumbnail_url,
            "broadcast_state": video.broadcast_state.value,
            "transcript_language": transcript.language_code,
            "transcript_type": "generated" if transcript.is_generated else "manual",
            "transcript_provider": transcript.provider,
            "retrieved_at": transcript.retrieved_at.isoformat(),
            "description": video.description,
        }
        frontmatter = yaml.safe_dump(
            metadata, allow_unicode=True, sort_keys=False, default_flow_style=False
        ).strip()
        content = f"---\n{frontmatter}\n---\n\n# {video.title}\n\n{cleaned_text.strip()}\n"
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return destination

