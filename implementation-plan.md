# YouTube Transcript Collector — Implementation Plan

## 1. Goal

Build a local Streamlit application that:

1. Accepts a public YouTube channel URL.
2. Discovers the channel's uploaded videos and completed livestreams.
3. Displays their title, URL, thumbnail, upload date, duration, description, and processing state.
4. Lets the user filter and select videos.
5. Retrieves existing English captions without downloading audio or running speech-to-text.
6. Cleans the captions and writes one Markdown file with YAML frontmatter per video.

The generated Markdown should remain usable by later wiki tooling, but LLM-based wiki generation is not part of this implementation.

## 2. Decisions and assumptions

- Runtime: Python 3.11 or newer.
- UI: Streamlit on localhost.
- Discovery: YouTube Data API v3 is the primary metadata source.
- Transcript extraction: `youtube-transcript-api` is primary; `yt-dlp` subtitle extraction is the fallback.
- Persistence: SQLite for discovery cache and processing state; Markdown files are the durable transcript output.
- Scale: tens of videos per channel, so processing can run synchronously inside the Streamlit process.
- Language: prefer manually authored English captions, then automatically generated English captions. Do not translate non-English captions in the MVP.
- Livestreams: completed livestreams are processed when captions are available. Active and upcoming streams are shown but cannot be selected for extraction.
- Input scope: channel URLs are supported in the MVP. Arbitrary individual video and playlist URLs are deferred.
- Existing output is skipped by default. A deliberate re-extract action may replace it atomically.
- No separate API service, task queue, Docker deployment, authentication, audio download, Whisper, or LLM is needed for the MVP.

## 3. User workflow

1. Start the app with `streamlit run app.py`.
2. Paste a public YouTube channel URL or handle.
3. Select **Load videos**.
4. Review, search, and sort the resulting video list.
5. Select one or more eligible videos, with **Select all** and **Select unprocessed** shortcuts.
6. Select **Extract transcripts**.
7. Watch per-video progress and receive a final success/skip/failure summary.
8. Open the generated files under `data/raw/<channel-slug>/`.

One failed transcript must not stop the rest of a selected batch.

## 4. Proposed architecture

```text
Streamlit UI
    |
    +-- Channel resolver
    |       +-- parse channel ID / handle / legacy username
    |
    +-- YouTube discovery adapter
    |       +-- YouTube Data API v3
    |
    +-- Transcript service
    |       +-- youtube-transcript-api adapter
    |       +-- yt-dlp subtitle fallback
    |
    +-- Transcript cleaner
    |
    +-- Markdown writer
    |
    +-- SQLite state repository

Output: data/raw/<channel-slug>/<title-slug>--<video-id>.md
```

Keep external libraries behind small adapters. In particular, the UI should call a stable application-level interface rather than importing `youtube-transcript-api`, `yt-dlp`, or Google client objects directly. This limits the impact of upstream API changes and allows transcript extraction to become a microservice later without changing the UI or storage layers.

## 5. Repository layout

```text
youtube-wiki/
├── app.py
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── src/
│   └── youtube_wiki/
│       ├── config.py
│       ├── models.py
│       ├── discovery/
│       │   ├── channel_resolver.py
│       │   └── youtube_api.py
│       ├── transcripts/
│       │   ├── service.py
│       │   ├── youtube_transcript.py
│       │   ├── yt_dlp.py
│       │   └── vtt.py
│       ├── processing/
│       │   └── cleaner.py
│       └── storage/
│           ├── markdown.py
│           └── state.py
├── data/
│   ├── raw/
│   └── cache/
└── tests/
    ├── fixtures/
    ├── test_channel_resolver.py
    ├── test_discovery.py
    ├── test_transcript_service.py
    ├── test_vtt.py
    ├── test_cleaner.py
    ├── test_markdown.py
    └── test_state.py
```

Use a `src` package so tests and the app import the same installed package. Ignore `.env`, SQLite/cache files, temporary subtitle files, and Python/Streamlit caches. Do not ignore `data/raw/` by default because those files are the requested output.

## 6. Core data contracts

Define typed models, preferably with Pydantic:

### `Channel`

- `channel_id`
- `title`
- `handle` when available
- `url`
- `uploads_playlist_id`
- `thumbnail_url`

### `Video`

- `video_id`
- `channel_id`
- `channel_title`
- `title`
- `url`
- `description`
- `thumbnail_url`
- `published_at`
- `duration_seconds`
- `broadcast_state`: `normal`, `upcoming`, `live`, or `completed`
- `processing_status`: `unprocessed`, `processing`, `extracted`, `unavailable`, or `failed`

### `TranscriptResult`

- `video_id`
- ordered caption segments before cleaning
- `language_code`
- `language_name`
- `is_generated`
- `provider`: `youtube-transcript-api` or `yt-dlp`
- `retrieved_at`

### Stable service interface

```python
class TranscriptService:
    def get_transcript(
        self,
        video_id: str,
        languages: tuple[str, ...] = ("en", "en-US", "en-GB"),
    ) -> TranscriptResult: ...
```

Return domain-specific errors such as `NoTranscriptAvailable`, `VideoUnavailable`, `LiveTranscriptUnsupported`, `RateLimited`, and `ExtractionFailed`; do not leak library-specific exceptions into the UI.

## 7. Discovery implementation

### Channel resolution

Normalize and validate the user input before calling the API:

- `/channel/<id>`: use the channel ID directly.
- `/@handle`: resolve with `channels.list(forHandle=...)`.
- `/user/<name>`: resolve with `channels.list(forUsername=...)`.
- `/c/<custom-name>` or other legacy URL forms: attempt a metadata-only `yt-dlp` resolution; otherwise show a precise unsupported-URL message.
- Reject video and playlist URLs in the MVP with a clear explanation.

Store the canonical channel ID so aliases and handles do not create duplicate channel records.

### Video enumeration

1. Call `channels.list` to obtain channel metadata and the uploads playlist ID.
2. Page through `playlistItems.list` with `maxResults=50` until all uploads are collected.
3. Call `videos.list` in batches of at most 50 IDs for `snippet`, `contentDetails`, and `liveStreamingDetails`.
4. Parse ISO-8601 durations into integer seconds and a UI display string.
5. Classify normal videos, completed livestreams, active livestreams, and upcoming livestreams.
6. Upsert channels and videos in SQLite.

Cache the most recent discovery result. A user-triggered **Refresh** should query YouTube again; a normal Streamlit rerun should use session state rather than repeat API requests.

## 8. Transcript selection and fallback rules

For each selected eligible video:

1. Ask `youtube-transcript-api` for the available transcript list.
2. Prefer a manually created exact-English transcript.
3. If absent, prefer another manually created English locale.
4. If absent, prefer generated English captions.
5. If the primary adapter fails or returns no usable English transcript, invoke the `yt-dlp` adapter with video download disabled and English manual/automatic subtitle options enabled.
6. Parse the resulting VTT in a temporary directory and delete the temporary artifacts after processing.
7. If neither adapter succeeds, map the outcome to a useful per-video status and continue the batch.

The fallback must never download video or audio. Do not attempt machine translation or speech-to-text.

## 9. Transcript cleaning

Keep cleaning deterministic and conservative so `data/raw` remains close to the source:

1. Preserve segment order and use segment timing only to infer paragraph breaks; do not emit timestamps.
2. Decode HTML entities and strip subtitle/VTT formatting tags.
3. Remove configurable standalone caption markers such as `[Music]` and `[Applause]`.
4. Remove exact consecutive duplicates introduced by rolling captions.
5. Join caption fragments with normalized spacing while avoiding spaces before punctuation.
6. Split text into readable paragraphs using long timing gaps and a maximum paragraph length.
7. Normalize newlines and trailing whitespace without rewriting wording or grammar.

Test cleaning against both `youtube-transcript-api` segment fixtures and VTT fixtures. Preserve punctuation supplied by YouTube; do not try to invent punctuation in this stage.

## 10. Markdown output

Use the filename pattern:

```text
data/raw/<channel-slug>/<title-slug>--<video-id>.md
```

Including the video ID prevents collisions when titles repeat or change. Generate slugs safely across platforms, cap their length, and fall back to the video ID if a title has no usable filename characters.

Example output:

```markdown
---
youtube_id: "aircAruvnKk"
title: "But what is a neural network?"
channel_id: "UCYO_jab_esuFRV4b17AJtAw"
channel: "3Blue1Brown"
url: "https://www.youtube.com/watch?v=aircAruvnKk"
published_at: "2017-10-05T14:00:00Z"
duration_seconds: 1157
thumbnail_url: "https://..."
broadcast_state: "normal"
transcript_language: "en"
transcript_type: "manual"
transcript_provider: "youtube-transcript-api"
retrieved_at: "2026-08-12T00:00:00Z"
description: >-
  Original video description.
---

# But what is a neural network?

What is a neural network? To start things off...
```

Serialize frontmatter with a YAML library rather than manual string interpolation. Write to a temporary sibling file and atomically rename it only after serialization succeeds, so interrupted runs cannot leave a partial Markdown file.

Before extraction, check SQLite and the output directory by video ID. Default to `skipped` if output already exists. A **Re-extract existing** option should explicitly enable replacement.

## 11. SQLite state

Use the standard-library `sqlite3` module. The minimum schema should contain:

- `channels`: canonical channel metadata and last refresh time.
- `videos`: metadata keyed by `video_id`, broadcast state, and last discovery time.
- `extractions`: video ID, status, output path, provider, language, caption type, retrieval time, and last error code/message.

Create the database and schema on first run. Keep all SQL in the state repository. Use transactions for upserts and extraction status changes. On startup, reconcile records marked `processing` from an interrupted prior run to `failed` or `unprocessed`.

## 12. Streamlit UI

### Configuration state

- Read `YOUTUBE_API_KEY` from `.env` or the process environment.
- If it is missing, show setup instructions and disable discovery actions.
- Never display or log the key.

### Discovery view

- Channel URL input and **Load videos** / **Refresh** actions.
- Channel title, thumbnail, total loaded count, and last refresh time.
- Search by title and description.
- Sort by newest/oldest, title, or duration.
- Optional filters for livestream state and extraction status.
- Table columns: select, thumbnail, title/link, upload date, duration, shortened description, stream state, and transcript status.

### Selection and extraction view

- **Select all visible**, **Select unprocessed**, and **Clear selection** actions.
- Active/upcoming streams have disabled selection with an explanatory label.
- Selected count and extraction confirmation button.
- Progress indicator plus the current video title.
- Result summary grouped into extracted, skipped, unavailable, and failed.
- Expandable failure details with actionable messages, without stack traces by default.

Preserve the loaded channel, filters, and selection in `st.session_state` so ordinary widget reruns do not clear the page.

## 13. Error handling and observability

Handle these cases explicitly:

- Invalid or unsupported channel URL.
- Missing, invalid, or quota-exhausted YouTube API key.
- Deleted, private, age-restricted, members-only, or region-blocked video.
- Captions disabled or no English transcript available.
- Active/upcoming livestream.
- YouTube request throttling or IP blocking.
- Network timeout.
- Malformed subtitle/VTT response.
- Filesystem permission or serialization failure.

Use Python logging with timestamps, level, module, and video ID, but never transcript bodies or secrets. Keep technical details in logs and translate expected errors into short UI messages. Add bounded retries with backoff only for transient network and rate-limit failures; do not retry permanent availability errors.

## 14. Implementation phases

### Phase 1 — Project foundation

Tasks:

- Create the package layout, dependency metadata, configuration loader, `.env.example`, `.gitignore`, and basic README.
- Define the typed domain models and exception hierarchy.
- Initialize SQLite and implement repository tests.

Exit criteria:

- A fresh checkout can install and start the Streamlit shell.
- Missing configuration produces a useful UI message.
- Database creation and model validation tests pass.

### Phase 2 — Channel and video discovery

Tasks:

- Implement URL normalization and channel resolution.
- Implement paginated upload discovery and batched video detail retrieval.
- Classify broadcast state and persist metadata.
- Build the discovery table, search, sort, filters, and cached refresh behavior.

Exit criteria:

- A public test channel with more than 50 uploads is fully paginated.
- Required metadata appears correctly for normal videos and completed livestreams.
- Active/upcoming streams are visibly distinguished.
- Streamlit reruns do not consume API quota unless the user loads or refreshes.

### Phase 3 — Primary transcript extraction and cleaning

Tasks:

- Implement the `youtube-transcript-api` adapter and language preference rules.
- Implement deterministic cleaning.
- Implement the Markdown/YAML writer and idempotency checks.
- Connect selection, progress, and results to the UI.

Exit criteria:

- Manual and generated English transcript fixtures are handled correctly.
- A selected captioned video produces valid UTF-8 Markdown with parseable YAML.
- Re-running extraction skips existing output unless replacement is requested.
- A failure for one selected video does not abort the batch.

### Phase 4 — `yt-dlp` fallback and resilience

Tasks:

- Implement metadata-only legacy URL resolution if needed.
- Implement subtitle-only `yt-dlp` fallback in a temporary directory.
- Parse and clean VTT while removing rolling-caption duplicates.
- Add error mapping, transient retries, logging, and interrupted-state reconciliation.

Exit criteria:

- Fallback is invoked only after the primary adapter cannot provide a usable transcript.
- Automated tests prove the fallback command/configuration cannot download media.
- Temporary files are removed on both success and failure.
- Expected unavailable and rate-limit cases receive distinct statuses.

### Phase 5 — End-to-end hardening and documentation

Tasks:

- Add mocked integration tests for discovery through Markdown writing.
- Run manual smoke tests against a small set of public videos, including a completed livestream and a no-caption video.
- Document API-key setup, startup, output layout, status meanings, troubleshooting, and limitations.
- Confirm generated Markdown opens cleanly in Obsidian and a GitHub Markdown preview.

Exit criteria:

- All automated tests and lint/type checks pass.
- The documented clean-install path works.
- The MVP definition of done below is satisfied.

## 15. Test strategy

Avoid live YouTube requests in the normal automated test suite. Use recorded/minimal JSON and VTT fixtures, and mock both external adapters.

### Unit tests

- URL parsing for channel IDs, handles, usernames, legacy/custom forms, and rejected inputs.
- API pagination, 50-ID batching, ISO duration parsing, and livestream classification.
- Manual-versus-generated English transcript selection.
- Exception mapping for unavailable, disabled, throttled, and malformed responses.
- Cleaning of HTML entities, tags, markers, repeated rolling captions, whitespace, punctuation, and Unicode.
- Filename sanitization, duplicate titles, long titles, YAML escaping, and atomic replacement.
- SQLite upserts, status transitions, and interrupted-run recovery.

### Integration tests

- Mocked channel input through discovery table data.
- Mocked primary transcript through Markdown output.
- Primary failure through `yt-dlp` fallback and VTT parsing.
- Mixed batch with successful, skipped, unavailable, and failed videos.

### Manual smoke tests

- A normal video with manual English captions.
- A normal video with generated English captions.
- A completed livestream with captions.
- A video without captions.
- An active or upcoming livestream.
- A channel containing more than one API page of uploads.

Because YouTube's unofficial transcript interfaces change, keep a small opt-in live smoke test that is excluded from CI and can be run manually when dependencies are upgraded.

## 16. Definition of done

The MVP is complete when:

- A user can load a public channel and see all required metadata.
- Search, sorting, selection, and processed-state display work across Streamlit reruns.
- Selected normal videos and completed livestreams with English captions produce cleaned Markdown files with valid YAML metadata.
- The primary/fallback preference is observable in saved metadata.
- Active/upcoming livestreams, missing captions, and extraction errors are reported without breaking a batch.
- Repeat runs do not create duplicates or silently overwrite output.
- External calls, cleaning, state persistence, and Markdown writing have automated coverage.
- Setup and known limitations are documented.

## 17. Deferred work

- Live, in-progress caption capture.
- Speech-to-text when captions are missing.
- Non-English transcript selection, translation, or multilingual UI.
- Individual video and playlist inputs.
- Automatic polling for new uploads.
- Hosted transcript-management UI, authentication, queues, or a separate microservice.
- LLM-based summarization and cross-video wiki generation.
- GitHub Pages, MkDocs, Quartz, or Obsidian publishing automation.

## 18. Risks and mitigations

- **Unofficial transcript endpoints can change:** isolate providers behind adapters, pin dependencies, keep fixture and opt-in live tests, and retain `yt-dlp` as a fallback.
- **YouTube can throttle or block transcript requests:** use bounded retries, clear status messages, modest sequential request pacing, and local execution.
- **Data API quota can be wasted by Streamlit reruns:** paginate efficiently, batch `videos.list`, cache results, and refresh only on explicit actions.
- **Title changes and duplicate titles can overwrite files:** use the immutable video ID in filenames and state keys.
- **Partial writes can corrupt output:** serialize first and atomically replace the destination.
- **Full transcripts may carry copyright or licensing restrictions:** keep publishing separate from collection and require the user to review rights before committing or publicly publishing generated files.
