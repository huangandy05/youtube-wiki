Help me plan out the following project: I want to create a markdown wiki off certain youtube pages. This wiki can then be viewed in Github Pages or Obsidian or something similar.
First, there should be some local interface that scrapes a youtube channels videos titles. I can then select certain videos from this list to extract a transcript from. This will populate a folder with raw transcripts. I will need some sort of microservice or scrape tool to extract these transcripts.

Do research on how this could be done, if there is any existing useful tools. First, ask followup questions to be sure of my requirements.


Before I research tools and architecture, I need these requirements clarified:

1. **YouTube scope**

   * Only public videos?
   * Entire channels/playlists, or arbitrary video URLs too?
   * Rough scale: tens, hundreds, or thousands of videos per channel?

2. **Local interface**

   * Would you prefer a lightweight web UI such as **Streamlit/Gradio**, or a more conventional React/Next.js frontend?
   * Should it run entirely locally, e.g. `localhost:8501`?

3. **Video discovery**

   * Should the app fetch:

     * title
     * thumbnail
     * upload date
     * duration
     * description
     * playlist
     * watched/processed status?
   * Do you want filtering/search before selecting videos?

4. **Transcript extraction**

   * Should we prioritize existing YouTube captions when available?
   * If captions are unavailable, should the system download audio and run speech-to-text such as **Whisper**?
   * Do you need timestamps, or just cleaned transcript text?
   * English only, or multilingual?

5. **Raw transcript format**

   * Something like:

     ```text
     /raw/
       channel-name/
         video-title.md
     ```
   * Should raw files contain YAML metadata such as video URL, channel, upload date, video ID, transcript source, and extraction date?

6. **Wiki generation**

   * Is the next stage intended to automatically turn transcripts into structured wiki pages using an LLM?
   * For example:

     ```text
     /raw/
       transcripts/

     /wiki/
       concepts/
       videos/
       people/
       topics/
     ```
   * Should multiple videos discussing the same concept be merged into shared wiki pages?

7. **LLM**

   * Local models, OpenAI API, another API, or configurable?
   * Should generated pages include citations back to the transcript/timestamp?

8. **Wiki frontend**

   * Is **plain Markdown compatible with both Obsidian and GitHub** the primary requirement?
   * For publishing, would you prefer:

     * GitHub Pages + MkDocs
     * Quartz
     * Docusaurus
     * Obsidian locally with a separate publishing layer?

9. **Automation**

   * Initially manual: select videos → click **Extract transcripts**?
   * Later should it detect new channel uploads and add them to an inbox automatically?

10. **Deployment**

    * Is this mainly a **personal local tool**, with only the generated Markdown published?
    * Or should the transcript-management interface eventually be hosted too?

Once you answer these, I’ll research existing projects/APIs—particularly YouTube metadata extraction, caption/transcript libraries, `yt-dlp`, Whisper-based fallbacks, Markdown/Obsidian pipelines, and existing YouTube-to-wiki projects—and propose a minimal architecture and implementation plan.

It will be public youtube videos (and live streams). I will need the corresponding URL, title and potentially thumbnail. The rough scale will be tens of videos per channel. I would like a lightweight web UI which will run locally. The video discovery can get the title, thumnbnail, upload date, duration, description. Just get the youtube captions when available. No speech to text needed. I don't need timestamps - just cleaned transcript text. It will be mainly english. The raw files can have yaml metadata. Eventually the next stage will be to turn transcripts into a wiki using an llm but don't worry about this now. I only want the transcription to work for now


Based on your requirements, I would build this as a **small Python + Streamlit application**, with YouTube discovery and transcript extraction separated into modules. There is no need for a separate microservice in the first version.

## Recommended architecture

```text
YouTube channel URL
        │
        ▼
┌─────────────────────┐
│ Channel discovery   │
│ YouTube Data API    │
└─────────┬───────────┘
          │
          ▼
  List of videos
  - title
  - URL
  - thumbnail
  - upload date
  - duration
  - description
  - livestream status
          │
          ▼
┌─────────────────────┐
│ Streamlit UI        │
│                     │
│ ☑ Video A           │
│ ☐ Video B           │
│ ☑ Video C           │
│                     │
│ [Extract selected]  │
└─────────┬───────────┘
          │
          ▼
┌──────────────────────────┐
│ Transcript extractor     │
│ youtube-transcript-api   │
│ + optional yt-dlp fallback│
└─────────┬────────────────┘
          │
          ▼
     Clean text
          │
          ▼
raw/
└── channel-name/
    ├── video-a.md
    ├── video-c.md
    └── ...
```

### 1. Local UI — Streamlit

**Streamlit is a particularly good fit here.** It runs as a local web server from a normal Python script and already provides interactive tables, editable checkbox columns, buttons, images and forms. ([Streamlit Docs][1])

The UI could be:

```text
YouTube Transcript Collector

Channel URL:
[ https://youtube.com/@example                 ]

[ Load videos ]

─────────────────────────────────────────────────────────
  Select   Thumbnail   Title       Date      Duration
─────────────────────────────────────────────────────────
   ☑       [image]     Video 1     Aug 10      34:20
   ☐       [image]     Video 2     Aug 03      18:12
   ☑       [image]     Stream 3    Jul 28    1:42:50
─────────────────────────────────────────────────────────

Selected: 2 videos

[ Extract transcripts ]

✓ Video 1 → raw/example/video-1.md
✓ Stream 3 → raw/example/stream-3.md
```

I would also add:

* search by title
* sort by upload date
* `Select all`
* `Select unprocessed`
* transcript status: `Available / Extracted / Failed`
* open YouTube URL
* thumbnail preview

---

# 2. Discovering channel videos

There are two sensible approaches.

### Option A — YouTube Data API v3

This is what I recommend for **video discovery**.

YouTube provides an official API for obtaining channel and video metadata. A channel resource contains an `uploads` playlist ID. You can retrieve that playlist and enumerate the channel's uploaded videos with `playlistItems.list`. ([Google for Developers][2])

Then call `videos.list` in batches to retrieve:

* title
* description
* thumbnails
* publish date
* duration
* livestream information

The `videos` resource specifically exposes `snippet`, `contentDetails`, and `liveStreamingDetails`; the latter is populated for upcoming, active and completed live broadcasts. ([Google for Developers][3])

For your scale, API quota should not be an issue. `playlistItems.list` and `videos.list` currently cost one quota unit per request. ([Google for Developers][4])

The downside is that you need a Google Cloud project and YouTube Data API key.

### Option B — `yt-dlp`

`yt-dlp` can scrape an entire YouTube channel without requiring a YouTube API key. It understands channel URLs and individual tabs, and can output metadata as JSON without downloading videos. ([GitHub][5])

For example, internally your Python app can use its Python API rather than executing shell commands.

It can retrieve metadata including fields such as title, description, duration and thumbnails. ([GitHub][6])

### My choice

Use:

**YouTube Data API → primary metadata source**

and optionally keep:

**yt-dlp → fallback**

This keeps the relatively fragile scraping logic away from basic channel discovery.

---

# 3. Transcript extraction

The most useful existing library for your particular use case is:

### `youtube-transcript-api`

It is almost exactly what you need.

It retrieves YouTube transcripts directly, works with manually created **and automatically generated subtitles**, does not require a browser, and does not require an API key. ([GitHub][7])

You can request English:

```python
YouTubeTranscriptApi().fetch(
    video_id,
    languages=["en"]
)
```

The result consists of transcript segments:

```python
[
    {
        "text": "Today we're going to discuss polar codes",
        "start": 4.2,
        "duration": 3.1
    },
    ...
]
```

Since you do not want timestamps, you simply retain `text`. The library also provides a `TextFormatter`. ([GitHub][8])

Importantly, it prefers manually created subtitles over automatically generated ones when both exist. ([GitHub][8])

That matches your desired behaviour quite well.

---

# 4. `yt-dlp` as transcript fallback

I would also implement a fallback:

```text
youtube-transcript-api
        │
        ├── Success → save
        │
        └── Failure
              │
              ▼
           yt-dlp
```

`yt-dlp` can retrieve both manually created and automatically generated subtitles without downloading the actual video:

```bash
yt-dlp \
  --skip-download \
  --write-subs \
  --write-auto-subs \
  --sub-langs "en.*" \
  VIDEO_URL
```

Those options are officially supported by yt-dlp. ([GitHub][6])

You would parse the resulting VTT/JSON subtitle data into plain text.

This fallback is useful because YouTube periodically changes its internal interfaces. Both projects actively deal with these changes, although neither unofficial caption method can guarantee permanent compatibility. `youtube-transcript-api` explicitly documents YouTube IP blocking as one current limitation, particularly on cloud servers—which is less concerning for your local-only application. ([GitHub][8])

---

# 5. Livestreams

There is an important distinction.

**Completed livestream/VOD:** treat it like any other video. If YouTube exposes a transcript after the stream finishes, extract it normally.

**Currently live stream:** I would **not support live transcript capture in MVP v1**.

There has historically been separate handling required for live captions; `youtube-transcript-api` has an open feature discussion around retrieving captions while a stream is actually live. ([GitHub][9])

`yt-dlp` has some live subtitle support, but live captions are delivered differently and YouTube continues to modify the relevant mechanisms. ([GitHub][10])

So I would define:

```text
Normal video               → supported
Completed livestream       → supported if transcript available
Currently live livestream  → show "LIVE — transcript unavailable yet"
Upcoming livestream        → show "UPCOMING"
```

That keeps the first implementation considerably cleaner.

---

# 6. Markdown output

I'd use one Markdown file per video:

```text
data/
└── raw/
    ├── 3blue1brown/
    │   ├── neural-networks.md
    │   └── transformers.md
    │
    └── another-channel/
        └── video.md
```

Example:

```markdown
---
youtube_id: aircAruvnKk
title: "But what is a neural network?"
channel: "3Blue1Brown"
url: "https://www.youtube.com/watch?v=aircAruvnKk"
published: 2017-10-05
duration_seconds: 1157
thumbnail: "https://..."
transcript_language: "en"
transcript_type: "manual"
retrieved: 2026-08-12
---

# But what is a neural network?

What is a neural network? To start things off...
```

I suggest using the **video ID as the internal unique identifier**, even if filenames are based on titles. Titles can change.

---

# 7. Transcript cleaning

Keep cleaning deliberately conservative.

Pipeline:

```text
YouTube captions
      ↓
remove timestamps
      ↓
HTML decode
      ↓
remove caption markers such as:
[Music]
[Applause]
      ↓
join broken caption lines
      ↓
normalize whitespace
      ↓
preserve paragraph-sized chunks
      ↓
Markdown
```

I would **not use an LLM for this stage**. You want `/raw` to remain close to the original source. The later wiki-generation pipeline can perform semantic restructuring.

---

# 8. Suggested code structure

```text
youtube-wiki/
│
├── app.py
│
├── requirements.txt
│
├── .env
│
│
├── src/
│   ├── youtube/
│   │   ├── discovery.py
│   │   ├── metadata.py
│   │   └── transcripts.py
│   │
│   ├── processing/
│   │   └── clean_transcript.py
│   │
│   ├── storage/
│   │   ├── markdown.py
│   │   └── state.py
│   │
│   └── models/
│       └── video.py
│
├── data/
│   ├── raw/
│   └── cache/
│
└── tests/
    ├── test_transcripts.py
    └── test_cleaning.py
```

I would keep `transcripts.py` behind a simple interface:

```python
get_transcript(video_id) -> TranscriptResult
```

That way you can later replace it with another scraper, HTTP service or microservice without touching the UI.

---

# 9. MVP development plan

I'd build it in four small stages:

1. **Discovery**

   * enter channel URL
   * retrieve videos
   * show title, thumbnail, date, description and duration

2. **Selection UI**

   * checkbox table
   * search/filter
   * persistent `processed` status

3. **Transcript extraction**

   * `youtube-transcript-api`
   * English manual captions preferred
   * automatic English captions fallback
   * `yt-dlp` fallback
   * error/status handling

4. **Markdown writer**

   * clean text
   * YAML metadata
   * safe filenames
   * avoid duplicate video IDs
   * `/data/raw/<channel>/...`

## Recommended stack

| Component           | Choice                        |
| ------------------- | ----------------------------- |
| Language            | Python                        |
| Local UI            | **Streamlit**                 |
| Video discovery     | **YouTube Data API v3**       |
| Primary transcripts | **youtube-transcript-api**    |
| Transcript fallback | **yt-dlp**                    |
| Data format         | Markdown + YAML               |
| State/cache         | SQLite or small JSON database |
| Python models       | Pydantic                      |
| Config              | `.env`                        |
| Later wiki          | Obsidian / MkDocs / Quartz    |

The overall architecture is therefore quite small. **I would avoid FastAPI, Docker, databases beyond SQLite, queues, Celery, React, or separate microservices for the initial implementation.** They add little at your current scale. A single Streamlit Python process with well-separated modules is sufficient; the transcript module can be extracted into a service later if necessary.

[1]: https://docs.streamlit.io/?utm_source=chatgpt.com "Streamlit documentation"
[2]: https://developers.google.com/youtube/v3/docs/channels "Channels  |  YouTube Data API  |  Google for Developers"
[3]: https://developers.google.com/youtube/v3/docs/videos?utm_source=chatgpt.com "Videos | YouTube Data API"
[4]: https://developers.google.com/youtube/v3/docs/playlistItems/list?utm_source=chatgpt.com "PlaylistItems: list | YouTube Data API"
[5]: https://github.com/yt-dlp/yt-dlp?utm_source=chatgpt.com "yt-dlp/yt-dlp: A feature-rich command-line audio/video ..."
[6]: https://github.com/yt-dlp/yt-dlp "GitHub - yt-dlp/yt-dlp: A feature-rich command-line audio/video downloader · GitHub"
[7]: https://github.com/jdepoix/youtube-transcript-api?utm_source=chatgpt.com "jdepoix/youtube-transcript-api"
[8]: https://github.com/jdepoix/youtube-transcript-api "GitHub - jdepoix/youtube-transcript-api: This is a python API which allows you to get the transcript/subtitles for a given YouTube video. It also works for automatically generated subtitles and it does not require an API key nor a headless browser, like other selenium based solutions do! · GitHub"
[9]: https://github.com/jdepoix/youtube-transcript-api/issues/98?utm_source=chatgpt.com "Live Stream transcripts · Issue #98 · jdepoix/youtube-transcript-api"
[10]: https://github.com/yt-dlp/yt-dlp/issues/2039?utm_source=chatgpt.com "[youtube] auto-generated subtitles from livestreams #2039"
