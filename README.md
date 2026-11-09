# AI Viral Video Clipper

A local-first starter app for turning uploaded long-form videos into short vertical clips.

## Features
- Upload an MP4/MOV video
- Detect candidate moments using audio energy and scene changes
- Create 9:16 clips with FFmpeg
- Review generated clips in a simple browser dashboard

## Requirements
- Python 3.10+
- FFmpeg installed and available on PATH

## Run locally
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000.

## Notes
This is an MVP scaffold, not a trained viral-ranking model. It analyzes media heuristically; review clips before publishing. Upload only videos you own or have permission to use.