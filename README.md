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
- Variant 1: direct-quote hook overlay, clean fade-in, original audio
- Variant 2: reaction-led hook overlay, brief brightness/contrast intro effect, loudness-normalized audio
- Variant 3: curiosity hook overlay, brief color intro effect, compressed/boosted audio

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


## Word-by-word karaoke captions

The batch generator can request word-level timestamps from Faster-Whisper and render an ASS karaoke subtitle track. The active word is highlighted as the streamer speaks. Select **Word by word – karaoke highlight** in the dashboard, or choose sentence captions for conventional subtitles. A standard SRT sidecar is also included for editing and accessibility. The dashboard sends the selected caption mode to the batch API; word-level mode is the default.

Word timing is estimated by speech recognition and may drift or mis-transcribe fast speech, overlapping voices, slang, or game audio. Review the result before publishing. If word timestamps are unavailable, the generator falls back to sentence captions.

## Burned-in captions and subtitle styles

Batch exports can optionally burn captions directly into the video when Faster-Whisper transcription is available. The dashboard offers three styles:
- Classic: bold white text with a dark outline
- Yellow: yellow highlight-style text with a dark outline
- Boxed: white text on a translucent dark background

Choose **Only separate SRT** to keep captions as separate subtitle files instead of rendering them into the picture. SRT sidecars are included in the batch ZIP whenever a transcript is available. Burning captions requires an FFmpeg build with the `subtitles` filter and libass; if the filter is unavailable, those exports may fail, so check the FFmpeg build on the host.

Captions are generated from automatic speech recognition and can contain mistakes. Review spelling, timing, and readability before publishing.

## Automatic highlight selection and review report

When you upload a source recording and start a batch, the analysis selects the highest-scoring non-overlapping moments for Shorts and longer edits. The dashboard now lists each selected moment with source timestamps, score, reason, categories, and a transcript excerpt when available. The ZIP also includes `highlight-report.json` and `highlight-report.csv` so you can review or edit the timeline separately.

The score is a heuristic based on optional speech transcription, audio activity, and weak visual cues; it also gives a small positive bonus for observable hook signals in the first three seconds (early reaction phrases, laughter/humor, speech, and audio activity). A quiet opening is not automatically penalized. The hook score is not a retention prediction and is not a guarantee that a moment will perform well. Review every export before publishing. This workflow processes the uploaded source file only; it does not capture or download third-party live streams or VODs.


## Reaction & Rage Detector

The highlight ranker gives additional weight to explicit rage/frustration phrases in the transcript, alongside laughter, spontaneous reaction phrases, speech density, audio activity, and weak visual cues. The highlight report includes a separate rage score and matched phrases for review.

This is a heuristic signal, not reliable emotion recognition: transcription can be wrong, phrases can be sarcastic or playful, and loud audio alone is not treated as anger. Review clips before publishing and use source recordings you own or have permission to use.


## YouTube performance feedback tracker

The dashboard includes a manual YouTube Studio metrics tracker. Add a published video's format, content category, edit variant, views, engaged views, Shorts "stayed to watch", average view duration, average percentage viewed, long-form CTR, likes, comments, shares, and subscribers gained. The app stores entries in `outputs/performance.json` and compares category and edit-variant averages. It only shows a leading category or variant after at least three entries in that group.

The comparison score is an internal heuristic, not a viral prediction. For useful comparisons, record metrics at roughly the same age after publishing (for example, after 48 hours) and compare Shorts with Shorts and long-form videos with long-form videos. You can now import a CSV exported from YouTube Studio's Advanced mode. The importer supports common English and Swedish metric headers, asks for default category/format/edit variant when those fields are absent, skips unreadable rows, and detects repeated imports of the exact same file. It does not connect to a Google account or import analytics automatically; you export the CSV yourself.


### Cautious feedback-based ranking

Once at least three results exist for a category within the same format (Shorts or long-form), future candidate scores receive a small adjustment based on that category's average historical performance score. The adjustment is capped at ±5 points and is shown in the highlight report/dashboard. This is a lightweight heuristic, not model training; it should not be trusted as a causal conclusion from small or mismatched samples.


## Optional AI clip reviewer (vision + transcript)

A second-pass reviewer can inspect up to three sampled still frames (opening, middle, ending) plus the available speech transcript for each selected highlight. It returns separate editorial scores for the hook, clarity, visual interest, payoff, and story coherence, along with strengths, weaknesses, and one suggested edit. It is a review aid, not a prediction of views or actual audience retention.

To enable it, configure these **server-side** environment variables:
- `OPENAI_API_KEY` — your OpenAI API key
- `OPENAI_CLIP_REVIEW_MODEL` — optional; defaults to `gpt-4.1-mini`
- `OPENAI_CLIP_REVIEW_MAX_CLIPS` — optional; maximum AI-reviewed highlights per batch, defaults to 12 (allowed range 1–30)

The app uses the OpenAI Responses API with image inputs. Without `OPENAI_API_KEY`, no external AI review request is made and the existing local analysis continues as usual. API errors also do not stop video exports. Each reviewed highlight can trigger a separate API request and may incur API charges; check current model pricing before enabling it.

**Privacy:** when enabled, up to three extracted frames and the available transcript excerpt from each reviewed clip are sent to OpenAI for analysis. Configure the key only on the server, never in frontend JavaScript or a public repository. Only process recordings you own or have permission to use. Review OpenAI's current data-use and retention terms before sending footage.

**Limitations:** the reviewer sees still images rather than the full moving video and does not directly listen to the audio. It can miss fast action, timing, sarcasm, context, and important events between sampled frames. Its scores and suggestions need human review.


## Animated hook overlays

Each selected highlight now has up to three transcript-grounded hook options, and the three rendered edit variants use one option each:
- V1 uses a direct quote from the clip.
- V2 uses the most expressive detected reaction line.
- V3 uses a curiosity-led prompt based on the transcript.

When a usable transcript exists, the chosen text is burned into the opening 2.8 seconds of the corresponding video as an animated ASS overlay, with a short fade and subtle scale-up. The hook is positioned near the top so it is visually separate from the regular bottom captions. The three variants retain their distinct visual/audio treatments. If transcription is unavailable or an option cannot be generated, that variant is rendered without hook text rather than inventing dialogue.

Hook text is generated from speech recognition and can contain transcription errors. Review every hook and the finished video before publishing. The hook overlays are drafts only: nothing is uploaded or published automatically. Use only footage you own or have permission to edit.


## Manual edit-point assistant

Each selected highlight now includes conservative trim suggestions based on detected speech timestamps. If there is a clearly long silent lead-in or tail, the report proposes new start/end timestamps and explains the estimated time saved. It preserves a short lead-in before the first detected words and a short pause after the final words. If transcript timing is unavailable or a trim would make the clip too short, it recommends keeping the original timestamps.

These are manual suggestions only: the renderer does not apply them, overwrite the source, or change the selected clips. Check suggested cut points in an editor before using them. Transcript timestamps can be imperfect, and the helper cannot understand visual context, music, sound effects, or whether a pause is intentionally funny.


## Three-option hook generator

Every selected highlight now receives up to three alternative opening text hooks: a direct quote, a reaction-led option, and a curiosity-led option. They are composed from words found in the clip transcript, not invented descriptions of unseen events. If no usable transcript is available, the app returns no hook options rather than fabricating a quote. The dashboard displays the alternatives for manual comparison.

These are text suggestions only: they are not automatically burned into the video or published. Add the chosen line in your editor and check that it accurately represents the footage. The generator uses local templates and transcript cues; it does not make an extra paid AI request and does not predict which hook will perform best.
