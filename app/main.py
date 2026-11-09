from array import array
import importlib.util
from pathlib import Path
import math
import re
import shutil
import subprocess
import tempfile
import uuid
import wave

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "uploads"
OUTPUTS = ROOT / "outputs"
STATIC = ROOT / "static"
for folder in (UPLOADS, OUTPUTS, STATIC):
    folder.mkdir(exist_ok=True)

ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
HIGHLIGHT_WORDS = {
    "wow", "what", "no", "bro", "insane", "crazy", "lets go", "let's go",
    "oh my god", "wait", "help", "nej", "va", "sjukt", "herregud", "fan",
    "jävlar", "kom igen", "seriöst", "hahaha", "haha", "no way", "what the",
    "mission", "heist", "wanted level", "five stars", "police", "cop",
    "explosion", "crash", "chase", "getaway", "busted", "survived",
    "headshot", "sniper", "gang", "casino", "rån", "polis", "sprängde"
}


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_clip_subtitles(job_id: str, clip_number: int, start: float, end: float, transcript):
    """Write a standard SRT subtitle file for the selected clip."""
    if transcript is None:
        return None
    entries = [
        item for item in transcript
        if item["end"] > start and item["start"] < end
    ]
    if not entries:
        return None
    subtitle_path = OUTPUTS / f"{job_id}_clip_{clip_number}.srt"
    lines = []
    for number, item in enumerate(entries, 1):
        local_start = max(0.0, item["start"] - start)
        local_end = min(end - start, item["end"] - start)
        if local_end <= local_start:
            continue
        lines.extend([
            str(number),
            f"{srt_timestamp(local_start)} --> {srt_timestamp(local_end)}",
            item["text"].replace("-->", "→").strip(),
            ""
        ])
    if not lines:
        return None
    subtitle_path.write_text("\\n".join(lines), encoding="utf-8")
    return subtitle_path.name

app = FastAPI(title="AI Viral Video Clipper")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def run_command(command):
    return subprocess.run(command, capture_output=True, text=True)


def get_duration(source: Path) -> float:
    result = run_command([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(source)
    ])
    try:
        return float(result.stdout.strip())
    except (ValueError, TypeError):
        raise HTTPException(400, "Could not read video duration")


def audio_levels(source: Path):
    """Return one RMS audio level per second, or an empty list if audio is unavailable."""
    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = Path(temp_dir) / "audio.wav"
        result = run_command([
            "ffmpeg", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "8000",
            "-c:a", "pcm_s16le", str(audio_path)
        ])
        if result.returncode != 0 or not audio_path.exists():
            return []
        levels = []
        try:
            with wave.open(str(audio_path), "rb") as audio:
                while True:
                    raw = audio.readframes(8000)
                    if not raw:
                        break
                    samples = array("h")
                    samples.frombytes(raw[:len(raw) - (len(raw) % 2)])
                    if not samples:
                        levels.append(0.0)
                    else:
                        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
                        levels.append(rms / 32768.0)
        except (wave.Error, OSError):
            return []
        return levels


def transcribe_audio(source: Path):
    """Optional Whisper transcription. Returns None when the optional package is absent."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None

    model_size = "small"
    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(source), vad_filter=True, word_timestamps=False)
        transcript = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                transcript.append({
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": text
                })
        return transcript
    except Exception:
        # A failed optional model should not prevent basic clip generation.
        return None


def score_windows(duration: float, clip_len: float, levels, transcript, clip_count: int):
    latest_start = max(0.0, duration - clip_len)
    step = max(3.0, min(8.0, clip_len / 5))
    starts = []
    current = 0.0
    while current <= latest_start:
        starts.append(current)
        current += step
    if latest_start not in starts:
        starts.append(latest_start)

    scored = []
    for start in starts:
        end = start + clip_len
        level_slice = levels[int(start):max(int(start) + 1, int(math.ceil(end)))]
        audio_score = sum(level_slice) / len(level_slice) if level_slice else 0.0
        words = []
        if transcript:
            words = [item for item in transcript if item["end"] >= start and item["start"] <= end]
        word_count = sum(len(item["text"].split()) for item in words)
        spoken_seconds = sum(max(0.0, min(end, item["end"]) - max(start, item["start"])) for item in words)
        text = " ".join(item["text"].lower() for item in words)
        matched_phrases = [phrase for phrase in HIGHLIGHT_WORDS if phrase in text]
        keyword_hits = len(matched_phrases)
        speech_density = word_count / max(clip_len, 1)
        # Transcription is the strongest signal; audio energy provides a fallback/tie-breaker.
        score = (speech_density * 65) + (keyword_hits * 8) + (audio_score * 20)
        if not transcript:
            score = audio_score * 100
        reason = (
            f"{word_count} transcribed words · {keyword_hits} reaction phrases"
            if transcript is not None else "Selected using audio activity"
        )
        scored.append({
            "start": start, "end": end, "score": score,
            "reason": reason, "audio_activity": round(audio_score, 3),
            "matched_phrases": matched_phrases
        })

    scored.sort(key=lambda item: item["score"], reverse=True)
    selected = []
    for candidate in scored:
        if all(candidate["end"] <= item["start"] or candidate["start"] >= item["end"] for item in selected):
            selected.append(candidate)
        if len(selected) >= clip_count:
            break
    if len(selected) < clip_count:
        for candidate in sorted(scored, key=lambda item: item["start"]):
            if candidate not in selected:
                selected.append(candidate)
            if len(selected) >= clip_count:
                break
    return sorted(selected, key=lambda item: item["score"], reverse=True)


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "whisper_available": importlib.util.find_spec("faster_whisper") is not None
    }


@app.post("/api/upload")
async def upload_video(video: UploadFile = File(...)):
    suffix = Path(video.filename or "video.mp4").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, "Unsupported video format")
    job_id = uuid.uuid4().hex[:12]
    source = UPLOADS / f"{job_id}{suffix}"
    size = 0
    try:
        with source.open("wb") as target:
            while chunk := await video.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    target.close()
                    source.unlink(missing_ok=True)
                    raise HTTPException(413, "Video is larger than the 2 GB upload limit")
                target.write(chunk)
    finally:
        await video.close()
    return {"job_id": job_id, "filename": source.name, "size_bytes": size}


@app.post("/api/process/{job_id}")
def process_video(job_id: str, clip_count: int = 3, clip_length: int = 30):
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        raise HTTPException(400, "Invalid job ID")
    if not 1 <= clip_count <= 8:
        raise HTTPException(400, "Choose between 1 and 8 clips")
    if not 15 <= clip_length <= 60:
        raise HTTPException(400, "Clip length must be between 15 and 60 seconds")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(500, "Install FFmpeg and make sure ffmpeg/ffprobe are on PATH")

    matches = list(UPLOADS.glob(f"{job_id}.*"))
    if not matches:
        raise HTTPException(404, "Video not found")
    source = matches[0]
    duration = get_duration(source)
    if duration < 5:
        raise HTTPException(400, "Video is too short to create clips")

    actual_clip_len = min(float(clip_length), duration)
    levels = audio_levels(source)
    transcript = transcribe_audio(source)
    candidates = score_windows(duration, actual_clip_len, levels, transcript, clip_count)

    results = []
    for index, candidate in enumerate(candidates, 1):
        out = OUTPUTS / f"{job_id}_clip_{index}.mp4"
        command = [
            "ffmpeg", "-y", "-ss", str(candidate["start"]), "-i", str(source),
            "-t", str(actual_clip_len), "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)
        ]
        run = run_command(command)
        if run.returncode == 0 and out.exists():
            subtitle_name = write_clip_subtitles(
                job_id, index, candidate["start"], candidate["end"], transcript
            )
            results.append({
                "name": out.name,
                "url": f"/api/clips/{out.name}",
                "subtitle_name": subtitle_name,
                "subtitle_url": f"/api/subtitles/{subtitle_name}" if subtitle_name else None,
                "start": round(candidate["start"], 1),
                "score": round(candidate["score"], 2),
                "reason": candidate["reason"],
                "matched_phrases": candidate["matched_phrases"]
            })

    if not results:
        raise HTTPException(500, "FFmpeg could not render any clips")
    method = "Whisper transcript + audio activity" if transcript is not None else "Audio activity fallback"
    return {
        "job_id": job_id,
        "clips": results,
        "analysis": method,
        "transcript_available": transcript is not None,
        "note": "Scores are heuristic estimates, not a guarantee that a clip will go viral."
    }


@app.get("/api/subtitles/{filename}")
def get_subtitles(filename: str):
    if not re.fullmatch(r"[a-f0-9]{12}_clip_[1-8]\\.srt", filename):
        raise HTTPException(400, "Invalid subtitle name")
    path = OUTPUTS / filename
    if not path.is_file():
        raise HTTPException(404, "Subtitles not found")
    return FileResponse(path, media_type="application/x-subrip", filename=path.name)


@app.get("/api/clips/{filename}")
def get_clip(filename: str):
    if not re.fullmatch(r"[a-f0-9]{12}_clip_[1-8]\.mp4", filename):
        raise HTTPException(400, "Invalid clip name")
    path = OUTPUTS / filename
    if not path.is_file():
        raise HTTPException(404, "Clip not found")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
