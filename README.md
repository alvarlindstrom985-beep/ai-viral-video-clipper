# AI Viral Video Clipper

A local-first app that ranks moments in uploaded videos and renders vertical clips.

## What it does
- Upload MP4, MOV, M4V, MKV, or WebM videos (up to 2 GB)
- Analyze audio activity to find candidate moments
- Optionally transcribe speech with Faster-Whisper and prioritize streamer humor, laughter cues, spontaneous reactions, and funny comments; GTA event terms are secondary signals
- Optionally analyze sampled video frames with OpenCV to detect faces, possible smiles, and movement as weak visual reaction cues
- Build candidate clip windows around approximate reaction timestamps from laughter/funny speech, sudden audio peaks, and weak visual smile cues, alongside the regular timeline scan
- Generate downloadable, time-synced SRT subtitle files for each clip when transcription is available
- Render 9:16 clips in 1080 × 1920 with FFmpeg
- Choose 1–8 clips and a duration of 15–60 seconds
- Preview and download the generated clips

## Requirements
- Python 3.10+
- FFmpeg and FFprobe installed and available on PATH

## Run locally
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000.

## Enable speech-aware ranking (optional)
Install the optional AI dependency:
```bash
pip install -r requirements-ai.txt
```
The first run downloads the Whisper small model, so allow extra time and disk space. CPU transcription can be slow. If Faster-Whisper is not installed or fails to load, the app falls back to audio-activity ranking.

## Enable visual reaction cues (optional)

Install the optional OpenCV dependency:
```bash
pip install -r requirements-vision.txt
```

The visual pass samples frames and uses basic face/smile detectors. It is only a rough signal: it can miss webcam overlays, mistake facial patterns for smiles, and cannot understand jokes, sarcasm, or emotions reliably.

## Daily batch exports (manual publishing)

The batch endpoint creates up to 25 unique Shorts and 5 unique longer videos from one uploaded source. Each selected moment is exported in three edit variants, for up to 90 files total:
- Variant 1: clean fade-in and original audio
- Variant 2: brief brightness/contrast intro effect and loudness-normalized audio
- Variant 3: brief color intro effect and compressed/boosted audio

Shorts are rendered vertically at 1080 × 1920. Longer videos are rendered in 16:9 at 1920 × 1080. The default UI settings use 30-second Shorts and 3-minute longer videos. You can adjust the counts and durations in the dashboard.

Run a batch by uploading a source video in the dashboard. The API endpoint is `POST /api/batch/{job_id}`. The app selects non-overlapping moments where enough source footage is available. If the recording is too short, it creates fewer unique clips instead of pretending it made the full batch. Rendering up to 90 files can take a long time and requires enough disk space and processing power.

**Manual publishing only:** this app does not connect to YouTube, TikTok, or Instagram and does not upload or publish anything. Every export is a draft for you to review and post yourself. The three audio variants use different audio processing; they do not add licensed or external music tracks.

## Important limitations
This is an early MVP, not a trained viral prediction model. It does not visually understand GTA gameplay or reliably detect specific events such as kills, crashes, or mission completions. It creates separate SRT subtitle files when speech transcription is available; captions are not yet burned into the video. Streamer-humor and visual signals are heuristics, not true emotion recognition; sarcasm, facial expressions, webcam layout, visual jokes, and context can be missed. Scores should be reviewed before posting. Only upload videos you own or have permission to use.


## Twitch live monitoring (read-only)

The dashboard can check up to 20 Twitch channel logins using Twitch's official Helix API. Configure these server environment variables using a Twitch developer application:
- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`

The browser refreshes live status every 60 seconds while the dashboard is open and monitoring is enabled. This is browser-session monitoring, not a persistent 24/7 background service. The integration only displays live status, stream title, game, viewer count, and a link to the channel. It does not join chats, record, download, or clip other creators' streams. Use only source recordings/VODs you own or have permission to process. Keep the client secret on the server; never put it in frontend code.
