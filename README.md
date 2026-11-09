# AI Viral Video Clipper

A local-first app that ranks moments in uploaded videos and renders vertical clips.

## What it does
- Upload MP4, MOV, M4V, MKV, or WebM videos (up to 2 GB)
- Analyze audio activity to find candidate moments
- Optionally transcribe speech with Faster-Whisper and prioritize streamer humor, laughter cues, spontaneous reactions, and funny comments; GTA event terms are secondary signals
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

## Important limitations
This is an early MVP, not a trained viral prediction model. It does not visually understand GTA gameplay or reliably detect specific events such as kills, crashes, or mission completions. It creates separate SRT subtitle files when speech transcription is available; captions are not yet burned into the video. Streamer-humor signals are transcript-based heuristics, not true emotion recognition; sarcasm, visual jokes, facial expressions, and context can be missed. Scores should be reviewed before posting. Only upload videos you own or have permission to use.
