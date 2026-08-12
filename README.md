# YouTube Transcript Collector

A local Streamlit app for selecting videos from a public YouTube channel and saving their existing English captions as Markdown with YAML metadata.

## Current scope

- Public channel discovery by channel ID URL, `@handle`, or legacy `/user/` URL.
- Metadata for normal videos and completed, active, or upcoming livestreams.
- Manual English captions preferred, with generated English captions next.
- `youtube-transcript-api` primary extraction and subtitle-only `yt-dlp` fallback.
- No audio/video downloads, speech-to-text, translation, or LLM processing.
- Active and upcoming livestream captions are not collected.

## Setup

You need Python 3.11+ and a YouTube Data API v3 key.

1. In [Google Cloud Console](https://console.cloud.google.com/), create or select a project.
2. Enable [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
3. Open **APIs & Services → Credentials**, create an API key, and restrict it to YouTube Data API v3. Since this is a local app, an application restriction is optional; keep the key private.
4. Create local configuration:

   ```bash
   cp .env.example .env
   ```

5. Put the key in `.env`:

   ```dotenv
   YOUTUBE_API_KEY=your_key_here
   ```

6. Install and run with `uv`:

   ```bash
   uv sync
   uv run streamlit run app.py
   ```

The app starts even without a key, but channel loading remains disabled and setup guidance is shown. Never commit `.env`.

## Output

Transcripts are written to:

```text
data/raw/<channel-slug>/<title-slug>--<video-id>.md
```

SQLite discovery/extraction state is stored in `data/cache/state.sqlite3`. Cache state and secrets are ignored by Git; Markdown transcript output is not ignored, so review copyright and publishing rights before committing it.

## Development

```bash
uv run pytest
uv run ruff check .
```

Automated tests use mocks and fixtures and do not call YouTube. Unofficial transcript endpoints can occasionally change or be throttled; the app reports per-video failures without stopping the remainder of a batch.

