from array import array
import base64
import importlib.util
import difflib
import zipfile
from pathlib import Path
import math
import re
import shutil
import subprocess
import tempfile
import uuid
import wave
import json
import csv
import hashlib
import unicodedata
import io
import os
import time
import urllib.parse
import urllib.request

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "uploads"
OUTPUTS = ROOT / "outputs"
PERFORMANCE_FILE = OUTPUTS / "performance.json"
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
RAGE_PHRASES = {
    "what the hell", "what the fuck", "are you kidding me", "you have got to be kidding",
    "i am so done", "i'm so done", "im so done", "this is ridiculous",
    "stop doing that", "shut up", "you ruined it", "i hate this",
    "jag blir galen", "jag blir förbannad", "blir tokig", "lägg av",
    "vad fan", "håll käften", "jag orkar inte", "det här är löjligt",
    "nu räcker det"
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

def write_batch_subtitles(batch_id: str, media_type: str, clip_number: int,
                          start: float, end: float, transcript):
    """Create a clip-local SRT file for optional burned-in captions."""
    if not transcript:
        return None
    entries = [item for item in transcript if item["end"] > start and item["start"] < end]
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
    subtitle_path = OUTPUTS / f"{batch_id}_{media_type}_{clip_number:02d}.srt"
    subtitle_path.write_text("\n".join(lines), encoding="utf-8")
    return subtitle_path



def write_word_karaoke_ass(batch_id: str, media_type: str, clip_number: int,
                           start: float, end: float, transcript):
    """Write ASS karaoke captions using Whisper word-level timestamps."""
    events = []
    for segment in transcript or []:
        words = [word for word in segment.get("words", [])
                 if word["end"] > start and word["start"] < end]
        if not words:
            continue
        karaoke = []
        for word in words:
            local_start = max(0.0, word["start"] - start)
            local_end = min(end - start, word["end"] - start)
            duration_cs = max(1, int(round((local_end - local_start) * 100)))
            token = word["text"].replace("{", "(").replace("}", ")").replace("\\", "")
            karaoke.append(f"{{\\k{duration_cs}}}{token}")
        if karaoke:
            first = max(0.0, words[0]["start"] - start)
            last = max(first + 0.01, min(end - start, words[-1]["end"] - start))
            events.append((first, last, " ".join(karaoke)))
    if not events:
        return None

    font_size = 58 if media_type == "short" else 42
    ass = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Arial,{font_size},&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,1,0,1,4,1,2,70,70,150,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    def ass_time(seconds):
        total_cs = max(0, int(round(seconds * 100)))
        hours, rem = divmod(total_cs, 360000)
        minutes, rem = divmod(rem, 6000)
        secs, cs = divmod(rem, 100)
        return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"
    for event_start, event_end, text in events:
        ass.append(f"Dialogue: 0,{ass_time(event_start)},{ass_time(event_end)},Default,,0,0,0,,{text}")
    path = OUTPUTS / f"{batch_id}_{media_type}_{clip_number:02d}_karaoke.ass"
    path.write_text("\n".join(ass) + "\n", encoding="utf-8")
    return path

def ffmpeg_subtitle_filter(subtitle_path: Path, style: str, media_type: str):
    """Build a safely escaped FFmpeg subtitles filter using a fixed style allowlist."""
    styles = {
        "classic": "FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Bold=1,Alignment=2,MarginV=95",
        "yellow": "FontName=Arial,FontSize=23,PrimaryColour=&H0000D7FF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Bold=1,Alignment=2,MarginV=105",
        "boxed": "FontName=Arial,FontSize=21,PrimaryColour=&H00FFFFFF,BackColour=&H90000000,BorderStyle=3,Outline=1,Shadow=0,Bold=1,Alignment=2,MarginV=90"
    }
    selected_style = styles.get(style, styles["classic"])
    if media_type == "long":
        selected_style = selected_style.replace("FontSize=22", "FontSize=18").replace("FontSize=23", "FontSize=19").replace("FontSize=21", "FontSize=17")
    path = subtitle_path.resolve().as_posix().replace(":", r"\\:").replace("'", r"\\'")
    return f"subtitles=filename='{path}':force_style='{selected_style}'"

BATCH_JOBS = {}

TWITCH_APP_TOKEN = {"value": None, "expires_at": 0}

def twitch_app_access_token():
    """Get/cache a Twitch app token using official Client Credentials OAuth."""
    client_id = os.getenv("TWITCH_CLIENT_ID", "").strip()
    client_secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise HTTPException(503, "Twitch är inte konfigurerat. Lägg till TWITCH_CLIENT_ID och TWITCH_CLIENT_SECRET som miljövariabler.")
    if TWITCH_APP_TOKEN["value"] and TWITCH_APP_TOKEN["expires_at"] > time.time() + 60:
        return TWITCH_APP_TOKEN["value"]
    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }).encode()
    request = urllib.request.Request(
        "https://id.twitch.tv/oauth2/token", data=payload, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            token_data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(502, "Kunde inte ansluta till Twitch OAuth.") from exc
    TWITCH_APP_TOKEN["value"] = token_data["access_token"]
    TWITCH_APP_TOKEN["expires_at"] = time.time() + int(token_data.get("expires_in", 3600))
    return TWITCH_APP_TOKEN["value"]


@app.get("/api/streamers/live")
def get_live_streamers(channels: str = ""):
    """Read-only live status for channel logins; never downloads or records streams."""
    names = list(dict.fromkeys(
        item.strip().lower().lstrip("@")
        for item in channels.split(",")
        if item.strip()
    ))
    if not names or len(names) > 20 or any(not re.fullmatch(r"[a-z0-9_]{1,25}", name) for name in names):
        raise HTTPException(400, "Ange 1–20 giltiga Twitch-kanalnamn, separerade med kommatecken.")
    token = twitch_app_access_token()
    client_id = os.getenv("TWITCH_CLIENT_ID", "").strip()
    query = urllib.parse.urlencode([("user_login", name) for name in names])
    request = urllib.request.Request(
        "https://api.twitch.tv/helix/streams?" + query,
        headers={"Client-ID": client_id, "Authorization": "Bearer " + token}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8")).get("data", [])
    except Exception as exc:
        raise HTTPException(502, "Kunde inte hämta live-status från Twitch.") from exc
    live_by_login = {item["user_login"].lower(): item for item in data}
    return {
        "checked_at": int(time.time()),
        "channels": [
            {
                "login": name,
                "is_live": name in live_by_login,
                "title": live_by_login[name].get("title", "") if name in live_by_login else "",
                "game_name": live_by_login[name].get("game_name", "") if name in live_by_login else "",
                "viewer_count": live_by_login[name].get("viewer_count", 0) if name in live_by_login else 0,
                "started_at": live_by_login[name].get("started_at") if name in live_by_login else None,
                "url": "https://www.twitch.tv/" + name
            }
            for name in names
        ]
    }

app.mount("/static", StaticFiles(directory=STATIC), name="static")


def run_command(command):
    return subprocess.run(command, capture_output=True, text=True)


def inspect_render_quality(path: Path, expected_duration: float, expected_width: int, expected_height: int):
    if not path.is_file() or path.stat().st_size < 10000:
        return {"passed": False, "reason": "Filen saknas eller är för liten", "warnings": []}
    probe = run_command(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)])
    if probe.returncode != 0:
        return {"passed": False, "reason": "FFprobe kunde inte läsa filen", "warnings": []}
    try:
        data = json.loads(probe.stdout or "{}")
        duration = float(data.get("format", {}).get("duration", 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        return {"passed": False, "reason": "Ogiltig videometadata", "warnings": []}
    streams = data.get("streams", [])
    video = next((x for x in streams if x.get("codec_type") == "video"), None)
    audio = next((x for x in streams if x.get("codec_type") == "audio"), None)
    valid_video = video is not None and int(video.get("width", 0)) == expected_width and int(video.get("height", 0)) == expected_height
    valid_duration = expected_duration * 0.90 <= duration <= expected_duration + 1.5
    warnings = [] if audio else ["Inget ljudspår hittades"]
    return {"passed": bool(valid_video and valid_duration), "reason": "OK" if valid_video and valid_duration else "Fel upplösning, saknat videospår eller fel längd", "warnings": warnings, "duration": round(duration, 2)}



def normalize_ai_review(payload):
    """Validate and clamp structured reviewer output before it reaches the UI."""
    if not isinstance(payload, dict):
        raise ValueError("AI-granskaren returnerade inte ett JSON-objekt")
    def bounded(value, default=0):
        try:
            return max(0, min(100, int(round(float(value)))))
        except (TypeError, ValueError):
            return default
    def short_list(value, limit=4):
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:180] for item in value if str(item).strip()][:limit]
    verdict = str(payload.get("verdict", "Behöver manuell granskning")).strip()[:80]
    return {
        "status": "completed",
        "score": bounded(payload.get("score")),
        "hook_score": bounded(payload.get("hook_score")),
        "clarity_score": bounded(payload.get("clarity_score")),
        "visual_interest_score": bounded(payload.get("visual_interest_score")),
        "payoff_score": bounded(payload.get("payoff_score")),
        "story_coherence_score": bounded(payload.get("story_coherence_score")),
        "verdict": verdict or "Behöver manuell granskning",
        "strengths": short_list(payload.get("strengths")),
        "weaknesses": short_list(payload.get("weaknesses")),
        "suggestion": str(payload.get("suggestion", "")).strip()[:300]
    }


def review_clip_with_ai(source: Path, start: float, end: float, transcript):
    """Optionally review three sampled frames plus transcript using the OpenAI Responses API."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"status": "not_configured", "message": "AI-granskning är inte aktiverad"}
    model = os.getenv("OPENAI_CLIP_REVIEW_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    transcript_text = " ".join(
        item.get("text", "") for item in (transcript or [])
        if item.get("end", 0) >= start and item.get("start", 0) <= end
    )[:3500]
    frame_data = []
    sample_times = sorted(set([
        min(end, start + min(1.0, max(0.2, (end - start) * 0.08))),
        start + (end - start) * 0.5,
        max(start, end - min(1.0, max(0.2, (end - start) * 0.08)))
    ]))
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            for index, timestamp in enumerate(sample_times):
                frame_path = Path(temp_dir) / f"review_{index}.jpg"
                result = run_command([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{timestamp:.3f}", "-i", str(source),
                    "-frames:v", "1", "-vf", "scale=512:-2",
                    "-q:v", "7", str(frame_path)
                ])
                if result.returncode == 0 and frame_path.is_file():
                    encoded = base64.b64encode(frame_path.read_bytes()).decode("ascii")
                    frame_data.append({
                        "type": "input_image",
                        "image_url": "data:image/jpeg;base64," + encoded,
                        "detail": "low"
                    })
        if not frame_data:
            return {"status": "unavailable", "message": "Kunde inte skapa granskningsbilder"}
        prompt = (
            "Du är en försiktig videoredaktör som granskar ett kort klipp för publikens tittarintresse. "
            "Du får tre stillbilder från början, mitten och slutet samt eventuellt ett taltranskript. "
            "Bedöm bara sådant som underlaget faktiskt visar; hitta inte på händelser eller känslor. "
            "Stillbilder kan inte bevisa rörelse eller exakt timing. Bedöm om början snabbt ger sammanhang, "
            "om händelsen går att förstå, om bilderna verkar visuellt intressanta och om slutet ger en payoff. "
            "Svara på svenska med ENDAST ett JSON-objekt med nycklarna score, hook_score, clarity_score, "
            "visual_interest_score, payoff_score, story_coherence_score (heltal 0-100), verdict (kort text), "
            "strengths (lista med max 3 korta punkter), weaknesses (lista med max 3 korta punkter), "
            "suggestion (en konkret redigeringsidé). Poängen är redaktionella uppskattningar, inte "
            "förutsägelser om faktisk tittarretention. Om transkript saknas ska du inte låtsas att du hört ljud.\n\n"
            "Transkript: " + (transcript_text or "[Inget transkript tillgängligt]")
        )
        content = [{"type": "input_text", "text": prompt}] + frame_data
        body = json.dumps({
            "model": model,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": 450
        }).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=body,
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(request, timeout=55) as response:
            response_data = json.loads(response.read().decode("utf-8"))
        output_text = ""
        for output_item in response_data.get("output", []):
            if output_item.get("type") == "message":
                for part in output_item.get("content", []):
                    if part.get("type") == "output_text":
                        output_text += part.get("text", "")
        if not output_text:
            raise ValueError("AI-granskaren returnerade inget textresultat")
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError:
            first, last = output_text.find("{"), output_text.rfind("}")
            if first < 0 or last <= first:
                raise
            parsed = json.loads(output_text[first:last + 1])
        review = normalize_ai_review(parsed)
        review["model"] = model
        review["frames_reviewed"] = len(frame_data)
        return review
    except Exception:
        # An optional reviewer must never stop local clip generation.
        return {"status": "error", "message": "AI-granskningen kunde inte slutföras; exporten fortsätter ändå"}


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
        segments, _ = model.transcribe(str(source), vad_filter=True, word_timestamps=True)
        transcript = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                words = []
                for word in (segment.words or []):
                    if word.start is None or word.end is None:
                        continue
                    token = word.word.strip()
                    if token:
                        words.append({
                            "start": float(word.start),
                            "end": float(word.end),
                            "text": token
                        })
                transcript.append({
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": text,
                    "words": words
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
        rage = any(phrase in text for phrase in RAGE_PHRASES)
        laughter = bool(LAUGHTER_PATTERN.search(text))
        if funny or reaction or rage or laughter:
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


def learned_category_bonus(categories, media_format):
    """Apply a small, cautious ranking adjustment from previously recorded channel results."""
    category_map = {
        "Rage/ilska-signal": "Rage/ilska",
        "Streamerreaktion": "Stark reaktion",
        "Streamerhumor": "Humor/skratt",
        "Visuell möjlig skrattreaktion": "Humor/skratt",
        "GTA-händelse": "GTA-händelse",
        "Aktivt ögonblick": "Annat"
    }
    entries = [item for item in read_performance_entries() if item.get("format") == media_format]
    if len(entries) < 3:
        return 0.0
    overall = sum(item.get("performance_score", 0) for item in entries) / len(entries)
    possible = []
    for signal in categories:
        label = category_map.get(signal)
        if not label:
            continue
        matching = [item for item in entries if item.get("category") == label]
        if len(matching) >= 3:
            average = sum(item.get("performance_score", 0) for item in matching) / len(matching)
            possible.append(max(-5.0, min(5.0, (average - overall) * 0.15)))
    return round(max(possible, default=0.0), 2)


def score_opening_hook(start: float, levels, transcript, hook_seconds: float = 3.0):
    """Score only positive, observable signals in the first seconds of a candidate clip."""
    hook_end = start + hook_seconds
    opening_items = [
        item for item in (transcript or [])
        if item["end"] > start and item["start"] < hook_end
    ]
    opening_text = " ".join(item["text"].lower() for item in opening_items)
    upper_text = opening_text.upper()
    reaction_hits = [phrase for phrase in STREAMER_REACTION_PHRASES if phrase in upper_text]
    funny_hits = [phrase for phrase in STREAMER_FUNNY_PHRASES if phrase in opening_text]
    laughter_hits = len(LAUGHTER_PATTERN.findall(opening_text))
    word_count = sum(len(item["text"].split()) for item in opening_items)
    opening_levels = levels[max(0, int(start)):max(0, int(math.ceil(hook_end)))]
    average_audio = sum(opening_levels) / len(opening_levels) if opening_levels else 0.0

    # This is a small bonus, not a penalty: quiet or context-setting openings are not assumed bad.
    score = (
        min(len(reaction_hits), 2) * 3.0
        + min(len(funny_hits), 2) * 2.0
        + min(laughter_hits, 2) * 2.0
        + (1.0 if word_count >= 5 else 0.5 if word_count >= 2 else 0.0)
        + (1.0 if average_audio >= 0.08 else 0.0)
    )
    signals = []
    if reaction_hits:
        signals.append("reaktionsfras tidigt")
    if funny_hits or laughter_hits:
        signals.append("humor/skrattsignal tidigt")
    if word_count >= 5:
        signals.append("tydligt tal direkt")
    if average_audio >= 0.08:
        signals.append("aktivt ljud direkt")
    return {
        "score": round(min(score, 12.0), 2),
        "signals": signals,
        "reaction_hits": reaction_hits,
        "funny_hits": funny_hits,
        "laughter_hits": laughter_hits
    }



def candidate_similarity(candidate, existing):


def retention_signal_score(hook_score: float, active_buckets: int,
                           signal_families: int, payoff_score: float,
                           speech_density: float):
    """Estimate observable clip structure; this is not a prediction of real viewer retention."""
    parts = {
        "hook": min(max(hook_score, 0.0) / 12.0, 1.0) * 30.0,
        "continuity": min(max(active_buckets, 0), 4) / 4.0 * 25.0,
        "signal_variety": min(max(signal_families, 0), 6) / 6.0 * 15.0,
        "payoff": min(max(payoff_score, 0.0) / 2.0, 1.0) * 15.0,
        "speech_flow": min(max(speech_density, 0.0) / 1.2, 1.0) * 15.0,
    }
    score = round(sum(parts.values()))
    reasons = []
    if parts["hook"] >= 20:
        reasons.append("stark öppning")
    elif parts["hook"] < 8:
        reasons.append("öppningen kan behöva snabbare kontext eller en tydligare krok")
    if parts["continuity"] >= 18.75:
        reasons.append("aktivitet genom större delen av klippet")
    elif parts["continuity"] <= 6.25:
        reasons.append("risk för lugna partier")
    if parts["payoff"] >= 15:
        reasons.append("reaktion eller payoff mot slutet")
    if parts["signal_variety"] >= 10:
        reasons.append("flera oberoende händelsesignaler")
    if not reasons:
        reasons.append("blandade tittarhållningssignaler")
    label = "Starka signaler" if score >= 75 else "Lovande signaler" if score >= 55 else "Behöver manuell granskning"
    return {"score": score, "label": label, "reasons": reasons, "components": {key: round(value, 1) for key, value in parts.items()}}

    """Compare two candidate clips using time overlap and transcript similarity."""
    start_a, end_a = candidate["start"], candidate["end"]
    start_b, end_b = existing["start"], existing["end"]
    intersection = max(0.0, min(end_a, end_b) - max(start_a, start_b))
    shorter = max(0.001, min(end_a - start_a, end_b - start_b))
    union = max(end_a, end_b) - min(start_a, start_b)
    overlap_ratio = intersection / shorter
    iou = intersection / max(0.001, union)
    text_a = re.sub(r"[^a-z0-9åäö]+", " ", candidate.get("_similarity_text", "").lower()).strip()
    text_b = re.sub(r"[^a-z0-9åäö]+", " ", existing.get("_similarity_text", "").lower()).strip()
    text_ratio = difflib.SequenceMatcher(None, text_a, text_b).ratio() if text_a and text_b else 0.0
    return {"time_iou": iou, "overlap_ratio": overlap_ratio, "text_similarity": text_ratio}


def is_near_duplicate(candidate, existing):
    """Reject near-identical time windows or highly similar overlapping transcripts."""
    similarity = candidate_similarity(candidate, existing)
    return similarity["time_iou"] >= 0.68 or (
        similarity["overlap_ratio"] >= 0.35 and similarity["text_similarity"] >= 0.78
    )


def score_windows(duration: float, clip_len: float, levels, transcript, clip_count: int, visual_samples=None, allow_overlap=True, media_format='short'):
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
        rage_hits = [phrase for phrase in RAGE_PHRASES if phrase in text]
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
        # Explicit rage phrases are a strong ranking signal; loud audio alone is not treated as anger.
        rage_score = min(len(rage_hits) * 16, 48)
        game_score = len(game_hits) * 3
        speech_score = min(speech_density * 25, 18)
        audio_score_points = min(audio_score * 18, 12)
        score = streamer_score + rage_score + game_score + speech_score + audio_score_points + visual["visual_score"]

        categories = []
        if funny_hits or laughter_hits:
            categories.append("Streamerhumor")
        if reaction_hits:
            categories.append("Streamerreaktion")
        if rage_hits:
            categories.append("Rage/ilska-signal")
        if visual["smile_samples"] > 0:
            categories.append("Visuell möjlig skrattreaktion")
        if game_hits:
            categories.append("GTA-händelse")
        if not categories and (speech_density > 0.35 or audio_score > 0.025):
            categories.append("Aktivt ögonblick")

        hook = score_opening_hook(start, levels, transcript)
        hook_bonus = hook["score"]
        learning_bonus = learned_category_bonus(categories, media_format)

        # Measure whether activity is sustained across the clip, rather than one isolated spike.
        # Four buckets combine speech presence and audio activity; these are ranking hints, not
        # predictions of audience retention.
        bucket_count = 4
        bucket_activity = []
        for bucket in range(bucket_count):
            bucket_start = start + clip_len * bucket / bucket_count
            bucket_end = start + clip_len * (bucket + 1) / bucket_count
            bucket_words = sum(
                len(item["text"].split()) for item in words
                if item["end"] > bucket_start and item["start"] < bucket_end
            )
            left = max(0, int(bucket_start))
            right = min(len(levels), max(left + 1, int(math.ceil(bucket_end))))
            bucket_audio = sum(levels[left:right]) / len(levels[left:right]) if right > left else 0.0
            bucket_activity.append(bucket_words > 0 or bucket_audio >= 0.025)
        pacing_score = round(sum(bucket_activity) * 1.5, 2)

        # Reward more than one independent signal family, but cap the bonus.
        signal_families = sum(bool(value) for value in (
            funny_hits or laughter_hits, reaction_hits, rage_hits, game_hits,
            visual["smile_samples"] > 0, audio_score >= 0.06
        ))
        diversity_score = round(min(max(0, signal_families - 1) * 1.25, 5.0), 2)

        # A reaction or laugh late in the clip can provide a clearer payoff.
        payoff_start = start + clip_len * 0.65
        payoff_words = [
            item for item in words
            if item["end"] > payoff_start and item["start"] < end
        ]
        payoff_text = " ".join(item["text"].lower() for item in payoff_words)
        payoff_phrases = (
            STREAMER_FUNNY_PHRASES | RAGE_PHRASES | GAME_EVENT_PHRASES
            | {phrase.lower() for phrase in STREAMER_REACTION_PHRASES}
        )
        payoff_signal = any(phrase in payoff_text for phrase in payoff_phrases)
        payoff_signal = payoff_signal or bool(LAUGHTER_PATTERN.search(payoff_text))
        payoff_score = 2.0 if payoff_signal else 0.0

        retention = retention_signal_score(
            hook_bonus, sum(bucket_activity), signal_families,
            payoff_score, speech_density
        )
        score += learning_bonus + hook_bonus + pacing_score + diversity_score + payoff_score

        matched_phrases = list(dict.fromkeys(funny_hits + reaction_hits + rage_hits + game_hits))
        reason_parts = []
        if funny_hits or laughter_hits:
            reason_parts.append("rolig kommentar/skrattsignal")
        if reaction_hits:
            reason_parts.append("stark spontan reaktion")
        if rage_hits:
            reason_parts.append("rage/ilska-uttryck i transkriptet")
        if game_hits:
            reason_parts.append("GTA-relaterat uttryck")
        if not reason_parts:
            reason_parts.append("tal- och ljudaktivitet")

        scored.append({
            "start": start, "end": end, "score": score,
            "_similarity_text": text,
            "learning_bonus": learning_bonus,
            "hook_score": hook_bonus,
            "hook_signals": hook["signals"],
            "pacing_score": pacing_score,
            "pacing_buckets_active": sum(bucket_activity),
            "signal_diversity_score": diversity_score,
            "signal_families": signal_families,
            "payoff_score": payoff_score,
            "retention_score": retention["score"],
            "retention_label": retention["label"],
            "retention_reasons": retention["reasons"],
            "retention_components": retention["components"],
            "viral_ranking_score": round(score, 2),
            "reason": " · ".join(reason_parts + (["stark öppning"] if hook_bonus >= 4 else []) + (["aktivt genom klippet"] if pacing_score >= 4.5 else []) + (["tydlig payoff mot slutet"] if payoff_score else [])),
            "audio_activity": round(audio_score, 3),
            "matched_phrases": matched_phrases,
            "categories": categories,
            "streamer_score": round(streamer_score, 2),
            "rage_score": round(rage_score, 2),
            "rage_phrases": rage_hits,
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
        # Do not fill the batch with near-identical moments just to reach the requested count.
        if any(is_near_duplicate(candidate, item) for item in selected):
            continue
        if not allow_overlap and any(
            candidate["end"] > item["start"] and candidate["start"] < item["end"]
            for item in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= clip_count:
            break

    # Internal transcript text is only used for duplicate detection, never returned to the UI.
    for item in selected:
        item.pop("_similarity_text", None)
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
                "rage_score": candidate["rage_score"],
                "rage_phrases": candidate["rage_phrases"],
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


def render_batch_job(batch_id, job_id, short_count, long_count, short_length, long_length, burn_subtitles=True, subtitle_style='classic', caption_mode='word_by_word'):
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
                visual_samples, allow_overlap=False, media_format="long"
            )

        # Optional vision-language review. Limit API calls to keep usage predictable.
        ai_review_count = 0
        try:
            ai_review_limit = max(1, min(30, int(os.getenv("OPENAI_CLIP_REVIEW_MAX_CLIPS", "12"))))
        except ValueError:
            ai_review_limit = 12

        # Save an editable timestamp index for every selected highlight.
        highlights = []
        for media_type, candidates, clip_duration in (
            ("short", short_candidates, short_duration),
            ("long", long_candidates, min(float(long_length), duration))
        ):
            for index, candidate in enumerate(candidates, 1):
                if os.getenv("OPENAI_API_KEY", "").strip() and ai_review_count < ai_review_limit:
                    state["stage"] = f"AI-granskar {media_type} {index}"
                    ai_review = review_clip_with_ai(
                        source, candidate["start"], candidate["start"] + clip_duration, transcript
                    )
                    ai_review_count += 1
                elif os.getenv("OPENAI_API_KEY", "").strip():
                    ai_review = {"status": "limit_reached", "message": "Granskningsgränsen för denna batch är nådd"}
                else:
                    ai_review = {"status": "not_configured", "message": "Lägg till OPENAI_API_KEY på servern för AI-granskning"}
                nearby_text = [
                    item["text"] for item in (transcript or [])
                    if item["end"] >= candidate["start"] and item["start"] <= candidate["start"] + clip_duration
                ]
                highlights.append({
                    "type": media_type,
                    "number": index,
                    "start_seconds": round(candidate["start"], 2),
                    "end_seconds": round(candidate["start"] + clip_duration, 2),
                    "score": round(candidate["score"], 2),
                    "reason": candidate["reason"],
                    "categories": candidate["categories"],
                    "matched_phrases": candidate["matched_phrases"],
                    "rage_score": candidate["rage_score"],
                    "learning_bonus": candidate["learning_bonus"],
                    "hook_score": candidate.get("hook_score", 0.0),
                    "hook_signals": candidate.get("hook_signals", []),
                    "retention_score": candidate.get("retention_score", 0),
                    "retention_label": candidate.get("retention_label", "Ej bedömd"),
                    "retention_reasons": candidate.get("retention_reasons", []),
                    "retention_components": candidate.get("retention_components", {}),
                    "pacing_buckets_active": candidate.get("pacing_buckets_active", 0),
                    "signal_families": candidate.get("signal_families", 0),
                    "signal_diversity_score": candidate.get("signal_diversity_score", 0),
                    "payoff_score": candidate.get("payoff_score", 0),
                    "rage_phrases": candidate["rage_phrases"],
                    "transcript_excerpt": " ".join(nearby_text)[:1200],
                    "ai_review": ai_review
                })
        state["highlights"] = highlights

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
        quality_checks = []
        for media_type, candidates, clip_duration in groups:
            for clip_index, candidate in enumerate(candidates, 1):
                for recipe in recipes:
                    filename = f"{job_id}_{media_type}_{clip_index:02d}_{recipe['id']}.mp4"
                    out = OUTPUTS / filename
                    if media_type == "short":
                        framing = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
                    else:
                        framing = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
                    subtitle_path = None
                    if transcript:
                        # Keep a conventional SRT sidecar for editing/accessibility in every mode.
                        write_batch_subtitles(
                            batch_id, media_type, clip_index, candidate["start"],
                            candidate["start"] + clip_duration, transcript
                        )
                        if caption_mode == "word_by_word":
                            subtitle_path = write_word_karaoke_ass(
                                batch_id, media_type, clip_index, candidate["start"],
                                candidate["start"] + clip_duration, transcript
                            )
                        if subtitle_path is None:
                            subtitle_path = write_batch_subtitles(
                                batch_id, media_type, clip_index, candidate["start"],
                                candidate["start"] + clip_duration, transcript
                            )
                    video_filter = framing + "," + recipe["video_filter"]
                    if subtitle_path and burn_subtitles:
                        video_filter += "," + ffmpeg_subtitle_filter(subtitle_path, subtitle_style, media_type)
                    command = [
                        "ffmpeg", "-y", "-ss", str(candidate["start"]), "-i", str(source),
                        "-t", str(clip_duration), "-vf", video_filter,
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
                    expected_width, expected_height = (1080, 1920) if media_type == "short" else (1920, 1080)
                    quality = inspect_render_quality(out, clip_duration, expected_width, expected_height)
                    quality_checks.append({"name": filename, **quality})
                    if not quality["passed"]:
                        failures.append(filename)
                        out.unlink(missing_ok=True)
                        continue
                    results.append({
                        "name": filename, "url": f"/api/clips/{filename}",
                        "type": media_type, "clip_number": clip_index,
                        "variant": recipe["id"], "variant_label": recipe["label"],
                        "start": round(candidate["start"], 1),
                        "end": round(candidate["start"] + clip_duration, 1),
                        "duration": round(clip_duration, 1),
                        "score": round(candidate["score"], 2),
                        "rage_score": candidate["rage_score"],
                        "reason": candidate["reason"], "categories": candidate["categories"],
                        "subtitles_burned": bool(subtitle_path)
                    })
                    state["results"] = results

        if not results:
            raise RuntimeError("No videos could be rendered. Check FFmpeg and the source file.")
        report_json = OUTPUTS / f"{batch_id}_highlights.json"
        report_json.write_text(json.dumps({
            "batch_id": batch_id,
            "source_job_id": job_id,
            "note": "Automatiskt urval är en uppskattning. Granska klippen och kontrollera rättigheter innan publicering.",
            "highlights": highlights
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        report_csv = OUTPUTS / f"{batch_id}_highlights.csv"
        with report_csv.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "type", "number", "start_seconds", "end_seconds", "score",
                "reason", "categories", "matched_phrases", "rage_score", "learning_bonus", "rage_phrases", "transcript_excerpt"
            ])
            writer.writeheader()
            for item in highlights:
                row = dict(item)
                row["categories"] = ", ".join(row["categories"])
                row["matched_phrases"] = ", ".join(row["matched_phrases"])
                row["rage_phrases"] = ", ".join(row["rage_phrases"])
                writer.writerow(row)

        zip_path = OUTPUTS / f"{batch_id}_drafts.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in results:
                path = OUTPUTS / item["name"]
                if path.is_file():
                    archive.write(path, arcname=item["name"])
            for pattern in (f"{batch_id}_*.srt", f"{batch_id}_*.ass"):
                for subtitle_file in OUTPUTS.glob(pattern):
                    archive.write(subtitle_file, arcname=f"subtitles/{subtitle_file.name}")
            archive.write(report_json, arcname="highlight-report.json")
            archive.write(report_csv, arcname="highlight-report.csv")
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
            "quality_checks": quality_checks,
            "quality_passed": sum(1 for item in quality_checks if item.get("passed")),
            "quality_rejected": sum(1 for item in quality_checks if not item.get("passed")),
            "analysis": "Whisper transcript + audio activity" if transcript is not None else "Audio activity fallback",
            "visual_analysis_available": visual_samples is not None,
            "transcript_available": transcript is not None,
            "publishing": "manual_only",
            "subtitles_burned": bool(burn_subtitles and transcript is not None),
            "subtitle_style": subtitle_style,
            "caption_mode": caption_mode,
            "note": "All exports are saved as drafts. Nothing is uploaded or published automatically. Variants use different intro effects and audio mastering, not different music tracks."
        })
    except Exception as exc:
        state.update({"status": "failed", "stage": "Fel", "error": str(exc)})


@app.post("/api/batch/{job_id}", status_code=202)
def create_daily_batch(
    job_id: str,
    background_tasks: BackgroundTasks,
    short_count: int = 8,
    long_count: int = 1,
    variants: int = 3,
    short_length: int = 30,
    long_length: int = 300,
    burn_subtitles: bool = True,
    subtitle_style: str = "classic",
    caption_mode: str = "word_by_word"
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
    if subtitle_style not in {"classic", "yellow", "boxed"}:
        raise HTTPException(400, "Invalid subtitle style")
    if caption_mode not in {"word_by_word", "sentence"}:
        raise HTTPException(400, "Invalid caption mode")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(500, "Install FFmpeg and make sure ffmpeg/ffprobe are on PATH")
    if not list(UPLOADS.glob(f"{job_id}.*")):
        raise HTTPException(404, "Video not found")

    batch_id = uuid.uuid4().hex[:12]
    BATCH_JOBS[batch_id] = {
        "batch_id": batch_id, "job_id": job_id, "status": "queued",
        "stage": "Väntar på start", "completed": 0, "total": 0,
        "results": [], "created": None,
        "burn_subtitles": burn_subtitles, "subtitle_style": subtitle_style, "caption_mode": caption_mode
    }
    background_tasks.add_task(
        render_batch_job, batch_id, job_id, short_count, long_count, short_length, long_length,
        burn_subtitles, subtitle_style, caption_mode
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
        "highlights": state.get("highlights", []),
        "report_url": f"/api/batch/report/{batch_id}" if state.get("status") == "completed" else None,
        "subtitles_burned": state.get("subtitles_burned", False),
        "transcript_available": state.get("transcript_available", False),
        "failed_files": state.get("failed_files", []),
        "quality_checks": state.get("quality_checks", []),
        "quality_passed": state.get("quality_passed", 0),
        "quality_rejected": state.get("quality_rejected", 0)
    }


@app.get("/api/batch/report/{batch_id}")
def download_highlight_report(batch_id: str):
    if not re.fullmatch(r"[a-f0-9]{12}", batch_id):
        raise HTTPException(400, "Invalid batch ID")
    state = BATCH_JOBS.get(batch_id)
    if not state or state.get("status") != "completed":
        raise HTTPException(404, "Highlight report is not ready")
    path = OUTPUTS / f"{batch_id}_highlights.json"
    if not path.is_file():
        raise HTTPException(404, "Highlight report not found")
    return FileResponse(path, media_type="application/json", filename="highlight-report.json")



PERFORMANCE_CATEGORIES = {
    "Rage/ilska", "Stark reaktion", "Humor/skratt", "GTA-händelse", "Annat"
}
PERFORMANCE_FORMATS = {"short", "long"}
PERFORMANCE_VARIANTS = {"v1", "v2", "v3"}


def read_performance_entries():
    if not PERFORMANCE_FILE.is_file():
        return []
    try:
        data = json.loads(PERFORMANCE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_performance_entries(entries):
    temporary = PERFORMANCE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(PERFORMANCE_FILE)


def performance_score(entry):
    views = max(1, entry.get("views", 0))
    engagement = min(100.0, ((entry.get("likes", 0) + entry.get("comments", 0) + entry.get("shares", 0)) / views) * 1000.0)
    if entry.get("format") == "short":
        stayed = entry.get("stayed_to_watch_pct")
        retention = entry.get("average_view_percentage")
        values = []
        if stayed is not None:
            values.append((0.40, stayed))
        if retention is not None:
            values.append((0.40, retention))
        values.append((0.20, engagement))
    else:
        retention = entry.get("average_view_percentage")
        ctr = entry.get("click_through_rate_pct")
        values = []
        if retention is not None:
            values.append((0.55 if ctr is not None else 0.70, retention))
        if ctr is not None:
            values.append((0.20, ctr * 5.0))
        values.append((0.25 if ctr is not None else 0.30, engagement))
    weight = sum(item[0] for item in values)
    return round(sum(w * min(100.0, max(0.0, value)) for w, value in values) / weight, 2) if weight else 0.0


def build_performance_summary(entries):
    groups = {}
    for entry in entries:
        for key, label in (("category", entry.get("category", "Annat")), ("variant", entry.get("variant", "okänd"))):
            group_key = (key, label, entry.get("format", "short"))
            groups.setdefault(group_key, []).append(entry)
    summaries = []
    for (key, label, media_format), items in groups.items():
        summaries.append({
            "dimension": key, "label": label, "format": media_format,
            "samples": len(items),
            "average_score": round(sum(item.get("performance_score", 0) for item in items) / len(items), 2),
            "average_views": round(sum(item.get("views", 0) for item in items) / len(items), 1),
            "average_retention": round(sum(item.get("average_view_percentage", 0) for item in items if item.get("average_view_percentage") is not None) / max(1, sum(1 for item in items if item.get("average_view_percentage") is not None)), 2),
            "average_stayed": round(sum(item.get("stayed_to_watch_pct", 0) for item in items if item.get("stayed_to_watch_pct") is not None) / max(1, sum(1 for item in items if item.get("stayed_to_watch_pct") is not None)), 2)
        })
    category_groups = [item for item in summaries if item["dimension"] == "category" and item["samples"] >= 3]
    variant_groups = [item for item in summaries if item["dimension"] == "variant" and item["samples"] >= 3]
    return {
        "total_videos": len(entries),
        "summaries": sorted(summaries, key=lambda item: (item["dimension"], -item["average_score"])),
        "best_category": max(category_groups, key=lambda item: item["average_score"], default=None),
        "best_variant": max(variant_groups, key=lambda item: item["average_score"], default=None),
        "minimum_samples_for_recommendation": 3,
        "note": "Poängen är en intern jämförelsesiffra, inte en prognos för viralitet. Jämför helst videor med liknande ålder och format."
    }


@app.get("/api/performance")
def get_performance():
    entries = read_performance_entries()
    return {"entries": entries, "insights": build_performance_summary(entries)}


@app.post("/api/performance")
def add_performance(payload: dict):
    required = ("title", "category", "format", "variant", "views")
    if any(key not in payload for key in required):
        raise HTTPException(400, "Fyll i titel, kategori, format, variant och visningar.")
    title = str(payload.get("title", "")).strip()[:120]
    category = str(payload.get("category", ""))
    media_format = str(payload.get("format", ""))
    variant = str(payload.get("variant", ""))
    if not title or category not in PERFORMANCE_CATEGORIES or media_format not in PERFORMANCE_FORMATS or variant not in PERFORMANCE_VARIANTS:
        raise HTTPException(400, "Ogiltig titel, kategori, format eller videovariant.")
    numeric_fields = {
        "views": (0, 10**12, True),
        "engaged_views": (0, 10**12, True),
        "stayed_to_watch_pct": (0, 100, False),
        "average_view_duration_sec": (0, 86400, False),
        "average_view_percentage": (0, 1000, False),
        "click_through_rate_pct": (0, 100, False),
        "likes": (0, 10**12, True),
        "comments": (0, 10**12, True),
        "shares": (0, 10**12, True),
        "subscribers_gained": (0, 10**12, True)
    }
    cleaned = {}
    for key, (minimum, maximum, integer_only) in numeric_fields.items():
        value = payload.get(key)
        if value in (None, ""):
            cleaned[key] = None if not integer_only else 0
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise HTTPException(400, f"{key} måste vara ett tal.")
        if not math.isfinite(number) or number < minimum or number > maximum or (integer_only and not number.is_integer()):
            raise HTTPException(400, f"{key} ligger utanför tillåtet intervall.")
        cleaned[key] = int(number) if integer_only else round(number, 2)
    entry = {
        "id": uuid.uuid4().hex[:12],
        "title": title,
        "category": category,
        "format": media_format,
        "variant": variant,
        "recorded_at": int(time.time()),
        **cleaned
    }
    entry["performance_score"] = performance_score(entry)
    entries = read_performance_entries()
    entries.append(entry)
    save_performance_entries(entries)
    return {"entry": entry, "insights": build_performance_summary(entries)}


def normalize_csv_header(value):
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text)


CSV_COLUMN_ALIASES = {
    "title": {"videotitle", "title", "content", "videotitel", "videonamn", "innehall"},
    "views": {"views", "visningar"},
    "engaged_views": {"engagedviews", "engageradevisningar"},
    "average_view_duration_sec": {"averageviewduration", "genomsnittligvisningstid", "genomsnittligvisningslangd"},
    "average_view_percentage": {"averagepercentageviewed", "averageviewedpercentage", "averageviewpercentage", "genomsnittligvisningsprocent", "genomsnittligtvisat"},
    "stayed_to_watch_pct": {"stayedtowatch", "stayedtowatchpercent", "howmanychosetoview", "chosetoview", "valdeattvisa", "valdeattfortsattatitta"},
    "click_through_rate_pct": {"impressionsclickthroughrate", "impressionsclickthroughratepercent", "exponeringarklickfrekvens", "klickfrekvensforvisningar"},
    "likes": {"likes", "gillamarkeringar", "gilla"},
    "comments": {"comments", "kommentarer"},
    "shares": {"shares", "delningar"},
    "subscribers_gained": {"subscribersgained", "prenumeranter", "newsubscribers"},
    "category": {"category", "kategori", "klippkategori"},
    "format": {"format", "videoformat"},
    "variant": {"variant", "redigeringsvariant"}
}


def parse_csv_metric(value, integer_only=False, duration=False):
    raw = str(value or "").strip().replace("\u00a0", " ")
    if not raw or raw in {"—", "-", "N/A", "n/a"}:
        return None
    if duration:
        match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d+))?", raw)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            fraction = float("0." + (match.group(4) or "0"))
            return hours * 3600 + minutes * 60 + seconds + fraction
        unit_match = re.fullmatch(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+(?:[.,]\d+)?)\s*s)?", raw.lower())
        if unit_match and any(unit_match.groups()):
            return int(unit_match.group(1) or 0) * 3600 + int(unit_match.group(2) or 0) * 60 + float((unit_match.group(3) or "0").replace(",", "."))
    cleaned = raw.replace("%", "").replace(" ", "").replace("'", "")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        if integer_only:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    number = float(cleaned)
    if not math.isfinite(number):
        raise ValueError("ogiltigt tal")
    return int(number) if integer_only and number.is_integer() else number


def csv_row_value(row, column_map, key):
    index = column_map.get(key)
    return row[index] if index is not None and index < len(row) else ""


@app.post("/api/performance/import-csv")
async def import_performance_csv(
    file: UploadFile = File(...),
    category: str = Form("Annat"),
    media_format: str = Form("short"),
    variant: str = Form("v1")
):
    if category not in PERFORMANCE_CATEGORIES or media_format not in PERFORMANCE_FORMATS or variant not in PERFORMANCE_VARIANTS:
        raise HTTPException(400, "Ogiltig standardkategori, format eller variant.")
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(400, "Välj en CSV-fil exporterad från YouTube Studio.")
    raw = await file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "CSV-filen får vara högst 10 MB.")
    if not raw:
        raise HTTPException(400, "CSV-filen är tom.")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            decoded = raw.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise HTTPException(400, "Kunde inte läsa CSV-kodningen. Exportera filen som UTF-8 eller UTF-16.") from exc

    sample = decoded[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(decoded, newline=""), dialect)
    try:
        headers = next(reader)
    except StopIteration:
        raise HTTPException(400, "CSV-filen saknar kolumnrubriker.")
    normalized_headers = [normalize_csv_header(item) for item in headers]
    column_map = {}
    for field, aliases in CSV_COLUMN_ALIASES.items():
        for index, header in enumerate(normalized_headers):
            if header in aliases:
                column_map[field] = index
                break
    if "title" not in column_map or "views" not in column_map:
        raise HTTPException(400, "CSV-filen måste innehålla kolumner för videotitel och visningar. Testa exporten Video i YouTube Studio.")
    file_hash = hashlib.sha256(raw).hexdigest()
    entries = read_performance_entries()
    existing_fingerprints = {item.get("import_fingerprint") for item in entries if item.get("import_fingerprint")}
    imported, skipped, duplicates, errors = [], 0, 0, []
    numeric_fields = {
        "views": (0, 10**12, True, False),
        "engaged_views": (0, 10**12, True, False),
        "stayed_to_watch_pct": (0, 100, False, False),
        "average_view_duration_sec": (0, 86400, False, True),
        "average_view_percentage": (0, 1000, False, False),
        "click_through_rate_pct": (0, 100, False, False),
        "likes": (0, 10**12, True, False),
        "comments": (0, 10**12, True, False),
        "shares": (0, 10**12, True, False),
        "subscribers_gained": (0, 10**12, True, False)
    }
    for row_number, row in enumerate(reader, start=2):
        if not row or not any(str(cell).strip() for cell in row):
            continue
        if row_number > 5002:
            raise HTTPException(413, "CSV-importen är begränsad till 5 000 datarader per fil.")
        title = str(csv_row_value(row, column_map, "title")).strip()[:120]
        if not title:
            skipped += 1
            if len(errors) < 5:
                errors.append(f"Rad {row_number}: videotitel saknas.")
            continue
        row_category = str(csv_row_value(row, column_map, "category")).strip()
        row_format = str(csv_row_value(row, column_map, "format")).strip().lower()
        row_variant = str(csv_row_value(row, column_map, "variant")).strip().lower()
        row_category = row_category if row_category in PERFORMANCE_CATEGORIES else category
        row_format = row_format if row_format in PERFORMANCE_FORMATS else media_format
        row_variant = row_variant if row_variant in PERFORMANCE_VARIANTS else variant
        cleaned = {}
        try:
            for key, (minimum, maximum, integer_only, is_duration) in numeric_fields.items():
                raw_value = csv_row_value(row, column_map, key)
                number = parse_csv_metric(raw_value, integer_only=integer_only, duration=is_duration)
                if number is None:
                    number = 0 if integer_only else None
                if number is not None and (number < minimum or number > maximum or (integer_only and not float(number).is_integer())):
                    raise ValueError(f"{key} ligger utanför tillåtet intervall")
                cleaned[key] = int(number) if integer_only and number is not None else (round(number, 2) if number is not None else None)
            if cleaned["views"] is None:
                raise ValueError("visningar saknas")
        except (ValueError, TypeError, OverflowError) as exc:
            skipped += 1
            if len(errors) < 5:
                errors.append(f"Rad {row_number}: {str(exc)[:100]}")
            continue
        fingerprint = hashlib.sha256(f"{file_hash}:{row_number}".encode("utf-8")).hexdigest()
        if fingerprint in existing_fingerprints:
            duplicates += 1
            continue
        entry = {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "category": row_category,
            "format": row_format,
            "variant": row_variant,
            "recorded_at": int(time.time()),
            "import_fingerprint": fingerprint,
            **cleaned
        }
        entry["performance_score"] = performance_score(entry)
        entries.append(entry)
        imported.append(entry)
        existing_fingerprints.add(fingerprint)
    if imported:
        save_performance_entries(entries)
    return {
        "imported": len(imported),
        "skipped": skipped,
        "duplicates": duplicates,
        "errors": errors,
        "insights": build_performance_summary(entries)
    }


TITLE_HOOKS = {
    "Rage/ilska": ["Det här fick honom att tappa det", "Han orkade inte mer…", "Den sjukaste rage-reaktionen"],
    "Stark reaktion": ["Han kunde inte tro sina ögon", "Ingen såg den här reaktionen komma", "Reaktionen säger allt"],
    "Humor/skratt": ["Det här spårade ur totalt", "Försök att inte skratta åt det här", "Det blev ännu roligare än väntat"],
    "GTA-händelse": ["GTA gick från lugnt till kaos", "Det här händer bara i GTA", "Vilket totalt GTA-kaos"],
    "Annat": ["Det här ögonblicket är helt oväntat", "Vänta på vad som händer", "Det här måste du se"]
}


@app.post("/api/metadata")
def generate_metadata(payload: dict):
    """Create editable metadata drafts from user-provided clip context; no external AI call."""
    category = str(payload.get("category", "Annat"))
    media_format = str(payload.get("format", "short"))
    context = re.sub(r"\s+", " ", str(payload.get("context", "")).strip())[:240]
    if category not in PERFORMANCE_CATEGORIES or media_format not in PERFORMANCE_FORMATS:
        raise HTTPException(400, "Ogiltig kategori eller format.")
    if not context:
        raise HTTPException(400, "Beskriv kort vad som händer i klippet.")
    # Keep supplied context factual and compact; avoid inventing events or claims.
    context = re.sub(r"[<>]", "", context)
    hooks = TITLE_HOOKS[category]
    titles = [f"{hook} – {context}" if len(f"{hook} – {context}") <= 95 else hook for hook in hooks]
    titles.extend([
        f"{context[:78]}…" if len(context) > 78 else context,
        f"{'GTA' if category == 'GTA-händelse' else 'Streamer'}: {hooks[0].lower()}"
    ])
    titles = list(dict.fromkeys(title[:100] for title in titles))
    description = (
        f"{context}. Se hela klippet och avgör själv vad du tycker. "
        "Prenumerera för fler klipp."
    )
    tags = ["#shorts", "#gaming", "#gta" if category == "GTA-händelse" else "#streamer", "#gamingclips"]
    if category == "Rage/ilska":
        tags.append("#rage")
    elif category == "Humor/skratt":
        tags.append("#funny")
    elif category == "Stark reaktion":
        tags.append("#reaction")
    return {
        "titles": titles,
        "description": description,
        "hashtags": list(dict.fromkeys(tags)),
        "note": "Mallbaserade förslag – kontrollera att titeln stämmer med klippet. Inga visningar eller händelser garanteras."
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
