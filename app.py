from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from youtube_wiki.config import Settings
from youtube_wiki.discovery.youtube_api import YouTubeDataApi, format_duration
from youtube_wiki.errors import NoTranscriptAvailable, VideoUnavailable, YouTubeWikiError
from youtube_wiki.models import BroadcastState, ProcessingStatus, Video
from youtube_wiki.processing.cleaner import clean_transcript
from youtube_wiki.storage.markdown import MarkdownWriter
from youtube_wiki.storage.state import StateRepository
from youtube_wiki.transcripts.service import TranscriptService

PROJECT_ROOT = Path(__file__).resolve().parent
SETTINGS = Settings.load(PROJECT_ROOT)
logging.basicConfig(
    level=getattr(logging, SETTINGS.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("youtube_wiki.app")

VIDEO_TABLE_COLUMNS = [
    "Select",
    "Thumbnail",
    "Title",
    "YouTube",
    "Published",
    "Duration",
    "Description",
    "Stream",
    "Status",
    "Video ID",
]


@st.cache_resource
def state_repository(database_path: str) -> StateRepository:
    return StateRepository(Path(database_path))


@st.cache_resource
def transcript_service() -> TranscriptService:
    return TranscriptService()


def discover(channel_input: str) -> None:
    if not SETTINGS.api_key:
        st.error("Add YOUTUBE_API_KEY to .env before loading a channel.")
        return
    try:
        with st.spinner("Loading channel and videos from YouTube…"):
            api = YouTubeDataApi(SETTINGS.api_key)
            channel = api.resolve_channel(channel_input)
            videos = api.list_videos(channel)
            repository = state_repository(str(SETTINGS.database_path))
            repository.upsert_channel(channel)
            repository.upsert_videos(videos)
            st.session_state.channel = channel
            st.session_state.videos = videos
            st.session_state.selection = set()
    except YouTubeWikiError as error:
        st.error(str(error))


def video_table(videos: list[Video]) -> pd.DataFrame:
    statuses = state_repository(str(SETTINGS.database_path)).statuses(
        [video.video_id for video in videos]
    )
    rows = []
    for video in videos:
        status = statuses.get(video.video_id, ProcessingStatus.UNPROCESSED)
        video.processing_status = status
        rows.append(
            {
                "Select": video.video_id in st.session_state.get("selection", set()),
                "Thumbnail": video.thumbnail_url,
                "Title": video.title,
                "YouTube": video.url,
                "Published": video.published_at.date(),
                "Duration": format_duration(video.duration_seconds),
                "Description": video.description.replace("\n", " ")[:180],
                "Stream": video.broadcast_state.value,
                "Status": status.value,
                "Video ID": video.video_id,
            }
        )
    return pd.DataFrame(rows, columns=VIDEO_TABLE_COLUMNS)


def extract_selected(videos: list[Video], selected_ids: set[str], replace: bool) -> None:
    selected = [video for video in videos if video.video_id in selected_ids]
    if not selected:
        st.warning("Select at least one video.")
        return

    repository = state_repository(str(SETTINGS.database_path))
    writer = MarkdownWriter(SETTINGS.raw_dir)
    service = transcript_service()
    results = {"extracted": [], "skipped": [], "unavailable": [], "failed": []}
    progress = st.progress(0, text="Starting extraction…")

    for index, video in enumerate(selected, start=1):
        progress.progress((index - 1) / len(selected), text=f"Processing {video.title}")
        if video.broadcast_state in {BroadcastState.LIVE, BroadcastState.UPCOMING}:
            results["unavailable"].append((video.title, "Live captions are not supported."))
            continue
        if writer.exists(video) and not replace:
            results["skipped"].append((video.title, "Output already exists."))
            continue
        repository.set_processing(video.video_id)
        try:
            transcript = service.get_transcript(video.video_id)
            cleaned = clean_transcript(transcript.segments)
            output_path = writer.write(video, transcript, cleaned, replace=replace)
            repository.set_extracted(
                video.video_id,
                output_path,
                transcript.provider,
                transcript.language_code,
                transcript.is_generated,
                transcript.retrieved_at,
            )
            results["extracted"].append((video.title, str(output_path)))
        except (NoTranscriptAvailable, VideoUnavailable) as error:
            repository.set_error(video.video_id, unavailable=True, error=error)
            results["unavailable"].append((video.title, str(error)))
        except Exception as error:
            LOGGER.exception("Transcript extraction failed", extra={"video_id": video.video_id})
            repository.set_error(video.video_id, unavailable=False, error=error)
            results["failed"].append((video.title, str(error)))
    progress.progress(1.0, text="Extraction complete")

    counts = " · ".join(f"{len(items)} {name}" for name, items in results.items())
    st.success(counts)
    for name, items in results.items():
        if items:
            with st.expander(f"{name.title()} ({len(items)})", expanded=name == "failed"):
                for title, detail in items:
                    st.markdown(f"- **{title}** — {detail}")


def main() -> None:
    st.set_page_config(page_title="YouTube Transcript Collector", page_icon="▶️", layout="wide")
    SETTINGS.ensure_directories()
    state_repository(str(SETTINGS.database_path))

    st.title("YouTube Transcript Collector")
    st.caption("Collect existing English captions as Markdown. No video or audio is downloaded.")

    if not SETTINGS.api_key:
        st.warning(
            "YouTube Data API configuration is required for channel discovery. "
            "Copy `.env.example` to `.env`, add `YOUTUBE_API_KEY`, then restart the app."
        )

    with st.form("channel-form"):
        channel_input = st.text_input(
            "YouTube channel URL or handle",
            placeholder="https://www.youtube.com/@GoogleDevelopers",
        )
        load = st.form_submit_button("Load videos", disabled=not SETTINGS.api_key)
    if load:
        discover(channel_input)

    channel = st.session_state.get("channel")
    all_videos: list[Video] = st.session_state.get("videos", [])
    if not channel:
        st.info("Load a public YouTube channel to begin.")
        return

    header, refresh_column = st.columns([5, 1])
    with header:
        st.subheader(channel.title)
        st.caption(f"{len(all_videos)} public uploads loaded")
    with refresh_column:
        if st.button("Refresh"):
            discover(channel.handle or channel.url)
            st.rerun()

    search_column, state_column, status_column, sort_column = st.columns(4)
    search = search_column.text_input("Search", placeholder="Title or description")
    stream_filter = state_column.multiselect(
        "Stream state", [state.value for state in BroadcastState]
    )
    status_filter = status_column.multiselect(
        "Transcript status", [status.value for status in ProcessingStatus]
    )
    sort = sort_column.selectbox(
        "Sort", ["Newest", "Oldest", "Title", "Longest", "Shortest"]
    )

    videos = list(all_videos)
    if search:
        term = search.casefold()
        videos = [
            video
            for video in videos
            if term in video.title.casefold() or term in video.description.casefold()
        ]
    if stream_filter:
        videos = [video for video in videos if video.broadcast_state.value in stream_filter]
    table = video_table(videos)
    if status_filter:
        allowed_ids = set(table.loc[table["Status"].isin(status_filter), "Video ID"])
        videos = [video for video in videos if video.video_id in allowed_ids]
        table = table.loc[table["Video ID"].isin(allowed_ids)]

    sort_key, ascending = {
        "Newest": ("Published", False),
        "Oldest": ("Published", True),
        "Title": ("Title", True),
        "Longest": ("Duration", False),
        "Shortest": ("Duration", True),
    }[sort]
    if sort_key == "Duration":
        duration_by_id = {video.video_id: video.duration_seconds for video in videos}
        table = table.assign(_duration=table["Video ID"].map(duration_by_id)).sort_values(
            "_duration", ascending=ascending
        ).drop(columns="_duration")
    else:
        table = table.sort_values(sort_key, ascending=ascending)

    select_all, select_unprocessed, clear = st.columns(3)
    if select_all.button("Select all visible"):
        st.session_state.selection = {
            video.video_id
            for video in videos
            if video.broadcast_state not in {BroadcastState.LIVE, BroadcastState.UPCOMING}
        }
        st.rerun()
    if select_unprocessed.button("Select unprocessed"):
        st.session_state.selection = {
            video.video_id
            for video in videos
            if video.processing_status is ProcessingStatus.UNPROCESSED
            and video.broadcast_state not in {BroadcastState.LIVE, BroadcastState.UPCOMING}
        }
        st.rerun()
    if clear.button("Clear selection"):
        st.session_state.selection = set()
        st.rerun()

    edited = st.data_editor(
        table,
        hide_index=True,
        width="stretch",
        disabled=[
            "Thumbnail",
            "Title",
            "YouTube",
            "Published",
            "Duration",
            "Description",
            "Stream",
            "Status",
            "Video ID",
        ],
        column_config={
            "Select": st.column_config.CheckboxColumn(required=True),
            "Thumbnail": st.column_config.ImageColumn(width="small"),
            "YouTube": st.column_config.LinkColumn(display_text="Open"),
            "Description": st.column_config.TextColumn(width="large"),
            "Video ID": None,
        },
        key="video-editor",
    )
    visible_ids = set(table["Video ID"])
    selected_visible = set(edited.loc[edited["Select"], "Video ID"])
    previous = st.session_state.get("selection", set())
    st.session_state.selection = (previous - visible_ids) | selected_visible

    selected_count = len(st.session_state.selection)
    st.write(f"Selected: {selected_count}")
    replace = st.checkbox("Re-extract and replace existing transcript files")
    if st.button("Extract transcripts", type="primary", disabled=selected_count == 0):
        extract_selected(all_videos, st.session_state.selection, replace)


if __name__ == "__main__":
    main()
