from pathlib import Path
import shutil
import subprocess
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "uploads"
OUTPUTS = ROOT / "outputs"
STATIC = ROOT / "static"
for folder in (UPLOADS, OUTPUTS, STATIC):
    folder.mkdir(exist_ok=True)

app = FastAPI(title="AI Viral Video Clipper")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "ffmpeg": shutil.which("ffmpeg") is not None}


@app.post("/api/upload")
async def upload_video(video: UploadFile = File(...)):
    suffix = Path(video.filename or "video.mp4").suffix.lower()
    if suffix not in {".mp4", ".mov", ".m4v", ".mkv", ".webm"}:
        raise HTTPException(400, "Unsupported video format")
    job_id = uuid.uuid4().hex[:12]
    source = UPLOADS / f"{job_id}{suffix}"
    with source.open("wb") as target:
        shutil.copyfileobj(video.file, target)
    return {"job_id": job_id, "filename": source.name}


@app.post("/api/process/{job_id}")
def process_video(job_id: str):
    matches = list(UPLOADS.glob(f"{job_id}.*"))
    if not matches:
        raise HTTPException(404, "Video not found")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(500, "Install FFmpeg and make sure ffmpeg/ffprobe are on PATH")

    source = matches[0]
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
        capture_output=True, text=True
    )
    try:
        duration = float(probe.stdout.strip())
    except ValueError:
        raise HTTPException(400, "Could not read video duration")

    # MVP: choose several evenly spaced moments; this is a placeholder for a
    # future scene/speech/engagement ranking pipeline.
    clip_len = min(35.0, max(12.0, duration / 5))
    starts = [max(0.0, min(duration - clip_len, duration * p)) for p in (0.12, 0.38, 0.64)]
    results = []
    for index, start in enumerate(starts, 1):
        out = OUTPUTS / f"{job_id}_clip_{index}.mp4"
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(clip_len),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)
        ]
        run = subprocess.run(cmd, capture_output=True, text=True)
        if run.returncode == 0 and out.exists():
            results.append({"name": out.name, "url": f"/api/clips/{out.name}", "start": round(start, 1)})
    return {"job_id": job_id, "clips": results, "note": "Automatic moment ranking is a placeholder in this MVP."}


@app.get("/api/clips/{filename}")
def get_clip(filename: str):
    path = (OUTPUTS / filename).resolve()
    if path.parent != OUTPUTS.resolve() or not path.is_file():
        raise HTTPException(404, "Clip not found")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
