from array import array
import importlib.util
import zipfile
from pathlib import Path
import math
import re
import shutil
import subprocess
import tempfile
import uuid
import wave

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
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
STREAMER_FUNNY_PHRASES = {
    "hahaha", "hahah", "haha", "hehe", "lol", "lmao", "rofl", "skrattar",
    "jag dör", "kan inte", "vad gör jag", "vad håller jag på med",
    "är du seriös", "men herregud", "nej nej nej", "what am i doing",
    "i'm dead", "im dead", "i can't", "you are kidding", "are you serious",
    "bro what", "that was so stupid", "this is embarrassing", "i messed up",
    "my bad", "bruh", "no shot", "ain't no way"
}
STREAMER_REACTION_PHRASES = {
    "WHAT", "WHAT THE", "OH MY GOD", "NO WAY", "LET'S GO", "LETS GO",
    "BRO", "WAIT", "HELP", "NEJ", "VA", "SJUKT", "HERREGUD", "JÄVLAR",
    "KOM IGEN", "SERIÖST", "FAN", "ARE YOU KIDDING", "I CAN'T BELIEVE",
    "HOW DID I", "DID THAT JUST"
}
GAME_EVENT_PHRASES = {
    "mission", "heist", "wanted level", "five stars", "police", "cop",
    "explosion", "crash", "chase", "getaway", "busted", "survived",
    "headshot", "sniper", "gang", "casino", "rån", "polis", "sprängde"
}
LAUGHTER_PATTERN = re.compile(
    r"\b(?:ha{2,}|he{2,}|h[eä]h[eä]|lol|lmao|rofl|skrattar|laugh(?:ing|ter)?)\b",
    re.IGNORECASE
)


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
    subtitle_path.write_text("\n".join(lines), encoding="utf-8")
    return subtitle_path.name

app = FastAPI(title="AI Viral Video Clipper")
BATCH_JOBS = {}
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



def analyze_visual_reactions(source: Path):
    """Optional webcam-face analysis using OpenCV Haar cascades.
    Returns coarse face/smile/movement cues sampled every 1.5 seconds.
    It does not identify people or reliably infer emotions.
    """
    try:
        import cv2
    except ImportError:
        return None

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        return None
    face_xml = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    smile_xml = Path(cv2.data.haarcascades) / "haarcascade_smile.xml"
    face_detector = cv2.CascadeClassifier(str(face_xml))
    smile_detector = cv2.CascadeClassifier(str(smile_xml))
    if face_detector.empty():
        capture.release()
        return None

    samples = []
    previous_gray = None
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    frame_step = max(1, int(fps * 1.5))
    frame_index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame_index % frame_step == 0:
            height, width = frame.shape[:2]
            scale = min(1.0, 640.0 / max(width, height))
            if scale < 1.0:
                frame = cv2.resize(frame, (int(width * scale), int(height * scale)))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            faces = face_detector.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(36, 36)
            )
            smile_count = 0
            largest_face = 0.0
            for (x, y, w, h) in faces:
                largest_face = max(largest_face, (w * h) / max(1, gray.shape[0] * gray.shape[1]))
                if smile_detector.empty():
                    continue
                lower_face = gray[y + int(h * 0.35):y + h, x:x + w]
                if lower_face.size:
                    smiles = smile_detector.detectMultiScale(
                        lower_face, scaleFactor=1.7, minNeighbors=18,
                        minSize=(max(12, w // 5), max(8, h // 12))
                    )
                    smile_count += len(smiles)
            motion = 0.0
            if previous_gray is not None and previous_gray.shape == gray.shape:
                motion = float(cv2.absdiff(gray, previous_gray).mean()) / 255.0
            previous_gray = gray
            timestamp = frame_index / fps
            samples.append({
                "time": timestamp,
                "faces": len(faces),
                "smiles": min(smile_count, 2),
                "face_area": largest_face,
                "motion": motion
            })
        frame_index += 1
    capture.release()
    return samples


def visual_window_signals(visual_samples, start: float, end: float):
    if not visual_samples:
        return {"visual_score": 0.0, "smile_samples": 0, "face_samples": 0, "motion_score": 0.0}
    selected = [sample for sample in visual_samples if start <= sample["time"] <= end]
    if not selected:
        return {"visual_score": 0.0, "smile_samples": 0, "face_samples": 0, "motion_score": 0.0}
    smile_samples = sum(1 for sample in selected if sample["smiles"] > 0)
    face_samples = sum(1 for sample in selected if sample["faces"] > 0)
    motion_score = sum(sample["motion"] for sample in selected) / len(selected)
    # Smile detections are a weak positive cue; movement only provides context.
    visual_score = min(smile_samples * 3.0, 12.0) + min(motion_score * 20.0, 4.0)
    return {
        "visual_score": round(visual_score, 2),
        "smile_samples": smile_samples,
        "face_samples": face_samples,
        "motion_score": round(motion_score, 3)
    }

def find_reaction_anchors(duration: float, levels, transcript, visual_samples=None):
    """Find approximate reaction timestamps from speech, laughter, audio peaks and weak visual cues."""
    anchors = []
    for item in transcript or []:
        text = item["text"].lower()
        funny = any(phrase in text for phrase in STREAMER_FUNNY_PHRASES)
        reaction = any(phrase in text.upper() for phrase in STREAMER_REACTION_PHRASES)
        laughter = bool(LAUGHTER_PATTERN.search(text))
        if funny or reaction or laughter:
            anchors.append({
                "time": max(0.0, min(duration, (item["start"] + item["end"]) / 2)),
                "kind": "speech"
            })

    if levels:
        baseline = sorted(levels)[len(levels) // 2]
        threshold = max(0.055, baseline * 1.9)
        for index, level in enumerate(levels):
            before = levels[index - 1] if index > 0 else 0.0
            after = levels[index + 1] if index + 1 < len(levels) else 0.0
            if level >= threshold and level >= before and level >= after:
                anchors.append({"time": min(duration, index + 0.5), "kind": "audio"})

    for sample in visual_samples or []:
        if sample.get("smiles", 0) > 0:
            anchors.append({"time": sample["time"], "kind": "visual"})

    # Merge nearby signals so one reaction does not create many almost identical windows.
    anchors.sort(key=lambda item: item["time"])
    merged = []
    for anchor in anchors:
        if merged and anchor["time"] - merged[-1]["time"] < 3.0:
            if anchor["kind"] == "speech":
                merged[-1] = anchor
        else:
            merged.append(anchor)
    return merged


def score_windows(duration: float, clip_len: float, levels, transcript, clip_count: int, visual_samples=None, allow_overlap=True):
    latest_start = max(0.0, duration - clip_len)
    step = max(3.0, min(8.0, clip_len / 5))
    starts = []
    current = 0.0
    while current <= latest_start:
        starts.append(current)
        current += step
    if latest_start not in starts:
        starts.append(latest_start)

    anchors = find_reaction_anchors(duration, levels, transcript, visual_samples)
    pre_roll = min(8.0, max(4.0, clip_len * 0.25))
    for anchor in anchors:
        centered_start = max(0.0, min(latest_start, anchor["time"] - pre_roll))
        starts.append(centered_start)
    starts = sorted(set(round(value, 2) for value in starts))

    scored = []
    for start in starts:
        end = start + clip_len
        level_slice = levels[int(start):max(int(start) + 1, int(math.ceil(end)))]
        audio_score = sum(level_slice) / len(level_slice) if level_slice else 0.0
        words = [item for item in (transcript or []) if item["end"] >= start and item["start"] <= end]
        word_count = sum(len(item["text"].split()) for item in words)
        text = " ".join(item["text"].lower() for item in words)
        upper_text = text.upper()
        funny_hits = [phrase for phrase in STREAMER_FUNNY_PHRASES if phrase in text]
        reaction_hits = [phrase for phrase in STREAMER_REACTION_PHRASES if phrase in upper_text]
        game_hits = [phrase for phrase in GAME_EVENT_PHRASES if phrase in text]
        laughter_hits = len(LAUGHTER_PATTERN.findall(text))
        exclamations = sum(item["text"].count("!") for item in words)
        questions = sum(item["text"].count("?") for item in words)
        speech_density = word_count / max(clip_len, 1)
        visual = visual_window_signals(visual_samples, start, end)

        # Streamer personality is the primary signal; GTA keywords are secondary.
        streamer_score = (
            len(funny_hits) * 15 + len(reaction_hits) * 10
            + min(laughter_hits, 4) * 12 + min(exclamations, 5) * 2
            + min(questions, 4) * 1.5
        )
        game_score = len(game_hits) * 3
        speech_score = min(speech_density * 25, 18)
        audio_score_points = min(audio_score * 18, 12)
        score = streamer_score + game_score + speech_score + audio_score_points + visual["visual_score"]

        categories = []
        if funny_hits or laughter_hits:
            categories.append("Streamerhumor")
        if reaction_hits:
            categories.append("Streamerreaktion")
        if visual["smile_samples"] > 0:
            categories.append("Visuell möjlig skrattreaktion")
        if game_hits:
            categories.append("GTA-händelse")
        if not categories and (speech_density > 0.35 or audio_score > 0.025):
            categories.append("Aktivt ögonblick")

        matched_phrases = list(dict.fromkeys(funny_hits + reaction_hits + game_hits))
        reason_parts = []
        if funny_hits or laughter_hits:
            reason_parts.append("rolig kommentar/skrattsignal")
        if reaction_hits:
            reason_parts.append("stark spontan reaktion")
        if game_hits:
            reason_parts.append("GTA-relaterat uttryck")
        if not reason_parts:
            reason_parts.append("tal- och ljudaktivitet")

        scored.append({
            "start": start, "end": end, "score": score,
            "reason": " · ".join(reason_parts),
            "audio_activity": round(audio_score, 3),
            "matched_phrases": matched_phrases,
            "categories": categories,
            "streamer_score": round(streamer_score, 2),
            "game_score": round(game_score, 2),
            "visual_score": visual["visual_score"],
            "smile_samples": visual["smile_samples"],
            "face_samples": visual["face_samples"],
            "motion_score": visual["motion_score"],
            "reaction_anchor": min(
                (anchor["time"] for anchor in anchors if start <= anchor["time"] <= end),
                key=lambda value: abs(value - ((start + end) / 2)),
                default=None
            )
        })

    scored.sort(key=lambda item: item["score"], reverse=True)
    selected = []
    for candidate in scored:
        if all(candidate["end"] <= item["start"] or candidate["start"] >= item["end"] for item in selected):
            selected.append(candidate)
        if len(selected) >= clip_count:
            break
    if allow_overlap and len(selected) < clip_count:
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
    visual_samples = analyze_visual_reactions(source)
    candidates = score_windows(duration, actual_clip_len, levels, transcript, clip_count, visual_samples)

    results = []
    for index, candidate in enumerate(candidates, 1):
        out = OUTPUTS / f"{job_id}_clip_{index}.mp4"
        candidate_length = max(5.0, candidate["end"] - candidate["start"])
        command = [
            "ffmpeg", "-y", "-ss", str(candidate["start"]), "-i", str(source),
            "-t", str(candidate_length), "-vf",
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
                "end": round(candidate["end"], 1),
                "duration": round(candidate_length, 1),
                "reaction_anchor": round(candidate["reaction_anchor"], 1) if candidate["reaction_anchor"] is not None else None,
                "score": round(candidate["score"], 2),
                "reason": candidate["reason"],
                "matched_phrases": candidate["matched_phrases"],
                "categories": candidate["categories"],
                "streamer_score": candidate["streamer_score"],
                "game_score": candidate["game_score"],
                "visual_score": candidate["visual_score"],
                "smile_samples": candidate["smile_samples"],
                "face_samples": candidate["face_samples"]
            })

    if not results:
        raise HTTPException(500, "FFmpeg could not render any clips")
    method = "Whisper transcript + audio activity" if transcript is not None else "Audio activity fallback"
    return {
        "job_id": job_id,
        "clips": results,
        "analysis": method,
        "ranking_focus": "Streamerhumor, reaktioner och visuella skrattindikatorer prioriteras",
        "visual_analysis_available": visual_samples is not None,
        "transcript_available": transcript is not None,
        "note": "Scores are heuristic estimates, not a guarantee that a clip will go viral."
    }


def render_batch_job(batch_id, job_id, short_count, long_count, short_length, long_length):
    """Background worker. Progress is updated after each real export attempt."""
    state = BATCH_JOBS[batch_id]
    state["status"] = "running"
    try:
        matches = list(UPLOADS.glob(f"{job_id}.*"))
        if not matches:
            raise RuntimeError("Source video not found")
        source = matches[0]
        duration = get_duration(source)
        if duration < 5:
            raise RuntimeError("Video is too short to create clips")

        state["stage"] = "Analyserar ljud, tal och bild"
        levels = audio_levels(source)
        transcript = transcribe_audio(source)
        visual_samples = analyze_visual_reactions(source)
        short_duration = min(float(short_length), duration)
        short_candidates = score_windows(
            duration, short_duration, levels, transcript, short_count,
            visual_samples, allow_overlap=False
        )
        long_candidates = []
        if long_count and duration >= 180:
            actual_long_length = min(float(long_length), duration)
            long_candidates = score_windows(
                duration, actual_long_length, levels, transcript, long_count,
                visual_samples, allow_overlap=False
            )

        recipes = [
            {"id": "v1", "label": "Clean intro · original audio",
             "video_filter": "fade=t=in:st=0:d=0.55", "audio_filter": None},
            {"id": "v2", "label": "Flash intro · normalized audio",
             "video_filter": "eq=brightness=0.07:contrast=1.12:enable='between(t,0,1.1)',fade=t=in:st=0:d=0.25",
             "audio_filter": "loudnorm=I=-16:TP=-1.5:LRA=11"},
            {"id": "v3", "label": "Color intro · compressed audio",
             "video_filter": "hue=h=8:s=1.18:enable='between(t,0,1.4)',fade=t=in:st=0:d=0.4",
             "audio_filter": "acompressor=threshold=0.089:ratio=2:attack=20:release=250,volume=1.15"}
        ]

        groups = [
            ("short", short_candidates, short_duration),
            ("long", long_candidates, min(float(long_length), duration))
        ]
        planned = sum(len(candidates) * len(recipes) for _, candidates, _ in groups)
        state.update({"total": planned, "stage": "Renderar videor"})
        results, failures = [], []
        for media_type, candidates, clip_duration in groups:
            for clip_index, candidate in enumerate(candidates, 1):
                for recipe in recipes:
                    filename = f"{job_id}_{media_type}_{clip_index:02d}_{recipe['id']}.mp4"
                    out = OUTPUTS / filename
                    if media_type == "short":
                        framing = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
                    else:
                        framing = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
                    command = [
                        "ffmpeg", "-y", "-ss", str(candidate["start"]), "-i", str(source),
                        "-t", str(clip_duration), "-vf", framing + "," + recipe["video_filter"],
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23"
                    ]
                    if recipe["audio_filter"]:
                        command += ["-af", recipe["audio_filter"]]
                    command += ["-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
                    rendered = run_command(command)
                    state["completed"] += 1
                    if rendered.returncode != 0 or not out.exists():
                        failures.append(filename)
                        state["last_error"] = (rendered.stderr or "FFmpeg error")[-500:]
                        continue
                    results.append({
                        "name": filename, "url": f"/api/clips/{filename}",
                        "type": media_type, "clip_number": clip_index,
                        "variant": recipe["id"], "variant_label": recipe["label"],
                        "start": round(candidate["start"], 1),
                        "end": round(candidate["start"] + clip_duration, 1),
                        "duration": round(clip_duration, 1),
                        "score": round(candidate["score"], 2),
                        "reason": candidate["reason"], "categories": candidate["categories"]
                    })
                    state["results"] = results

        if not results:
            raise RuntimeError("No videos could be rendered. Check FFmpeg and the source file.")
        zip_path = OUTPUTS / f"{batch_id}_drafts.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in results:
                path = OUTPUTS / item["name"]
                if path.is_file():
                    archive.write(path, arcname=item["name"])
        state.update({
            "status": "completed", "stage": "Klart",
            "zip_url": f"/api/batch/download/{batch_id}",
            "created": {
                "shorts": sum(1 for item in results if item["type"] == "short") // 3,
                "long_videos": sum(1 for item in results if item["type"] == "long") // 3,
                "files": len(results)
            },
            "requested": {"shorts": short_count, "long_videos": long_count, "variants_per_video": 3},
            "failed_files": failures,
            "analysis": "Whisper transcript + audio activity" if transcript is not None else "Audio activity fallback",
            "visual_analysis_available": visual_samples is not None,
            "transcript_available": transcript is not None,
            "publishing": "manual_only",
            "note": "All exports are saved as drafts. Nothing is uploaded or published automatically. Variants use different intro effects and audio mastering, not different music tracks."
        })
    except Exception as exc:
        state.update({"status": "failed", "stage": "Fel", "error": str(exc)})


@app.post("/api/batch/{job_id}", status_code=202)
def create_daily_batch(
    job_id: str,
    background_tasks: BackgroundTasks,
    short_count: int = 25,
    long_count: int = 5,
    variants: int = 3,
    short_length: int = 30,
    long_length: int = 300
):
    """Queue a review-only batch and return immediately."""
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        raise HTTPException(400, "Invalid job ID")
    if not 1 <= short_count <= 25 or not 0 <= long_count <= 5:
        raise HTTPException(400, "Batch size is limited to 25 Shorts and 5 long videos")
    if variants != 3:
        raise HTTPException(400, "Exactly 3 variants are supported")
    if not 15 <= short_length <= 60:
        raise HTTPException(400, "Short length must be between 15 and 60 seconds")
    if not 180 <= long_length <= 600:
        raise HTTPException(400, "Long video length must be between 180 and 600 seconds")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(500, "Install FFmpeg and make sure ffmpeg/ffprobe are on PATH")
    if not list(UPLOADS.glob(f"{job_id}.*")):
        raise HTTPException(404, "Video not found")

    batch_id = uuid.uuid4().hex[:12]
    BATCH_JOBS[batch_id] = {
        "batch_id": batch_id, "job_id": job_id, "status": "queued",
        "stage": "Väntar på start", "completed": 0, "total": 0,
        "results": [], "created": None
    }
    background_tasks.add_task(
        render_batch_job, batch_id, job_id, short_count, long_count, short_length, long_length
    )
    return {"batch_id": batch_id, "status": "queued", "status_url": f"/api/batch/status/{batch_id}"}


@app.get("/api/batch/status/{batch_id}")
def get_batch_status(batch_id: str):
    if not re.fullmatch(r"[a-f0-9]{12}", batch_id):
        raise HTTPException(400, "Invalid batch ID")
    state = BATCH_JOBS.get(batch_id)
    if not state:
        raise HTTPException(404, "Batch not found (server may have restarted)")
    total = state.get("total", 0)
    return {
        "batch_id": batch_id, "status": state["status"], "stage": state["stage"],
        "completed": state["completed"], "total": total,
        "progress": round(state["completed"] / total * 100) if total else 0,
        "created": state.get("created"), "error": state.get("error"),
        "zip_url": state.get("zip_url"), "videos": state.get("results", []),
        "failed_files": state.get("failed_files", [])
    }


@app.get("/api/batch/download/{batch_id}")
def download_batch(batch_id: str):
    if not re.fullmatch(r"[a-f0-9]{12}", batch_id):
        raise HTTPException(400, "Invalid batch ID")
    state = BATCH_JOBS.get(batch_id)
    if not state or state.get("status") != "completed":
        raise HTTPException(404, "Batch ZIP is not ready")
    path = OUTPUTS / f"{batch_id}_drafts.zip"
    if not path.is_file():
        raise HTTPException(404, "Batch ZIP not found")
    return FileResponse(path, media_type="application/zip", filename="videobatch-utkast.zip")


@app.get("/api/subtitles/{filename}")
def get_subtitles(filename: str):
    if not re.fullmatch(r"[a-f0-9]{12}_clip_[1-8]\.srt", filename):
        raise HTTPException(400, "Invalid subtitle name")
    path = OUTPUTS / filename
    if not path.is_file():
        raise HTTPException(404, "Subtitles not found")
    return FileResponse(path, media_type="application/x-subrip", filename=path.name)


@app.get("/api/clips/{filename}")
def get_clip(filename: str):
    if not re.fullmatch(r"[a-f0-9]{12}_(?:clip_[1-8]|(?:short_\d{2}_v[1-3]|long_\d{2}_v[1-3]))\.mp4", filename):
        raise HTTPException(400, "Invalid clip name")
    path = OUTPUTS / filename
    if not path.is_file():
        raise HTTPException(404, "Clip not found")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
