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

## Storage monitoring and safe cleanup

The dashboard's **Lagring och diskutrymme** panel reports filesystem free space, total upload/output usage, and a preview of old generated files. It warns when disk usage reaches 85% or free space drops below a 512 MiB safety reserve. Uploads are rejected with HTTP 507 when writing the next chunk would breach that reserve, and new batches are checked against an estimated render-space requirement before they are queued.

The cleanup preview identifies known generated exports older than 30 days and source uploads older than 30 days. It only considers files matching the app's generated ID-based naming patterns; it never targets the performance data, SQLite job database, or unknown files. Sources and outputs for queued/running jobs are always protected; interrupted/failed jobs are protected for 30 days after their last saved update so there is time to retry them. Cleanup is **manual**: inspect the preview, then press the separate cleanup button. Keep backups of anything you may want later. The estimate is a safety heuristic; actual render sizes depend on source bitrate, codec, and settings.

## Persistent batch jobs and recovery

Batch job state is stored in `outputs/batch_jobs.sqlite3`, including the selected source job, render settings, progress, and completed export metadata. After a server restart, jobs that were queued or running are restored as **interrupted** rather than disappearing. Use `POST /api/batch/resume/{batch_id}` to restart an interrupted or failed batch with its saved settings. The original uploaded source file must still exist in the `uploads/` directory. A restart reruns the batch from the beginning; it does not continue an FFmpeg render from the exact frame where it stopped. Keep the `uploads/` and `outputs/` directories on persistent storage, and run a single application process for this local MVP.

## Automated render quality diagnostics

Every rendered export is checked with FFprobe for a readable video stream, expected dimensions, expected duration, and an audio stream. FFmpeg then runs advisory diagnostics for long black segments, frozen frames, and the audio peak level. Potentially problematic segments and peaks near 0 dB are shown as warnings on each draft card; they do not automatically reject a clip because dark scenes, intentional pauses, and loud effects can be valid creative choices. A missing audio stream or invalid technical metadata does fail the technical gate. These checks do not assess subtitle placement, story quality, or actual audience retention, so review each exported video manually before publishing.

## Subtitle layout diagnostics

ASS-based karaoke captions and animated hook overlays receive an additional layout check. It compares the subtitle canvas with the output dimensions and checks style font size, horizontal margins, vertical margins, and approximate single-line text width. Findings appear as advisory warnings on the draft; they do not reject exports. This is a metadata/heuristic check, not OCR: it cannot identify the actual GTA minimap, mission text, or moving gameplay subjects. It additionally estimates whether top- or bottom-aligned text enters generic interface safe zones (such as HUD areas or Shorts controls), including explicit ASS positions. These warnings are advisory and can be false positives; review the video itself before publishing.

## End-to-end render verification

The GitHub Actions test suite installs FFmpeg and runs a real render integration test using a generated synthetic test pattern and tone (not third-party footage). It exercises the batch worker, three edit variants, vertical scaling/cropping, audio encoding, sentence subtitles, animated ASS hook overlays, FFprobe validation, and the ZIP/report export. The test patches analysis/transcription with deterministic test data so it does not download Whisper models or call external AI services. It does not prove quality on arbitrary user recordings; test your own footage locally before publishing.

## Requirements
- Python 3.10+
- FFmpeg and FFprobe installed and available on PATH

## Windows quick start

1. Install Python 3.10 or newer and make sure Python is available on PATH: https://www.python.org/downloads/windows/
2. Install FFmpeg with FFprobe and make sure both commands are available on PATH: https://ffmpeg.org/download.html
3. Download/clone this repository to your Windows PC (for example with GitHub Desktop).
4. Double-click `CHECK_SETUP.bat` to diagnose Python, FFmpeg/FFprobe, the OneDrive sync root, and whether port 8000 is already in use.
5. Double-click `INSTALL_CLIPPER.bat` once. It creates the local Python environment and installs the required packages.
6. Double-click `START_CLIPPER.bat` whenever you want to run the app. It opens the dashboard at http://127.0.0.1:8000. Keep the black terminal window open while using the app; press Ctrl+C there to stop it.

The app automatically detects the Windows OneDrive sync root from the `OneDrive`, `OneDriveCommercial`, or `OneDriveConsumer` environment variables and uses `OneDrive/AI Viral Video Clipper/Inbox`. Make sure the folder is available on this PC (in File Explorer, choose **Always keep on this device** if Files On-Demand has not downloaded it). On first launch, the app creates the Inbox and `processed` folders if needed. In the dashboard, approve each source file and start the source watcher; the watcher must be started again after an app restart. Only process recordings you own or have permission to use.

`CHECK_SETUP.bat` is a diagnostic helper; it does not install software or change account settings. The Windows scripts do not install Python or FFmpeg automatically. If FFmpeg is missing, install it and add the folder containing both `ffmpeg.exe` and `ffprobe.exe` to PATH, then reopen the terminal and run the check again. Speech recognition and visual cues remain optional; install `requirements-ai.txt` and/or `requirements-vision.txt` in the app's virtual environment if you want those features.

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
This is an early MVP, not a trained viral prediction model. It does not visually understand GTA gameplay or reliably detect specific events such as kills, crashes, or mission completions. It creates separate SRT subtitle files when speech transcription is available and can burn captions into the video when enabled and supported by FFmpeg. Streamer-humor and visual signals are heuristics, not true emotion recognition; sarcasm, facial expressions, webcam layout, visual jokes, and context can be missed. Scores should be reviewed before posting. Only upload videos you own or have permission to use.


## Automatic source discovery and authorized inbox

The dashboard can query public YouTube channel RSS feeds for newly published video metadata (title, publication time, and link). Enter channel IDs in the form `UC...`; the discovery endpoint does not download video files or bypass YouTube access controls.

For automatic clip generation without using the browser upload form, place source recordings in the project's local `source_inbox/` folder. Only recordings you own or have explicit permission to process should be placed there. The dashboard can scan that folder and queue up to three videos per action using the normal batch pipeline (8 Shorts and 1 longer video by default, three edit variants, manual review only). Successfully queued originals are moved to `source_inbox/processed/`. The files are copied into the normal uploads area before rendering, so keep persistent storage and monitor disk space.

This is a first source-ingestion step, not a fully autonomous platform downloader: YouTube RSS provides discovery metadata only, and Twitch live monitoring provides live status only. Neither integration records or downloads other creators' streams/VODs. To process platform footage, use creator-owned exports or a source explicitly provided for clipping. The local inbox currently requires the recording to be placed in the folder; continuous unattended recording or downloading is not implemented.

### Automatic local source watcher

The dashboard can start and stop a background watcher for the authorized source inbox. By default it watches `source_inbox/` in the project root; set the server environment variable `CLIPPER_SOURCE_INBOX` to point at a folder synchronized by a desktop cloud-drive client (for example, a creator-authorized OneDrive/Google Drive sync folder) if desired. The app does not authenticate to or download from those cloud services itself. The watcher While enabled, it checks every 15 seconds for supported video files and waits until a file is at least 30 seconds old before processing, reducing the chance of reading a file while it is still being copied or synced. Each file is fingerprinted with SHA-256 and recorded in `outputs/source_watch_seen.json` to avoid re-queuing the same content after a restart. Successfully queued originals are moved into `source_inbox/processed/`; each recording is copied to the normal uploads folder and sent through the existing batch renderer. The watcher processes one source at a time and uses the standard defaults (8 Shorts, 1 long video, three variants).

This makes folder-based intake automatic once a recording appears in the folder (for example through a creator-authorized desktop cloud-sync folder). It does **not** open YouTube/Twitch watch pages to extract video streams, download third-party VODs, or record live broadcasts. Public YouTube RSS and Twitch Helix integrations remain discovery/status-only. The watcher is process-local and must be started from the dashboard after each server restart; keep the server running and use a single application process. Only ingest content you own or have explicit permission to process.

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

## Diversity-aware batch selection

Batch selection now uses a greedy, score-first pass with a small soft penalty when a new candidate repeats a category already represented in the batch. Strongest candidates remain prioritized, while close-scoring alternatives can improve category variety. Existing near-duplicate and non-overlap checks still apply, and the selector fills remaining slots when only one category is available. Each selected highlight includes a short selection reason and the diversity adjustment for review. This is a ranking heuristic, not a guarantee of varied or engaging content.

## Automatic highlight selection and review report

When you upload a source recording and start a batch, the analysis selects the highest-scoring non-overlapping moments for Shorts and longer edits. The dashboard now lists each selected moment with source timestamps, score, reason, categories, and a transcript excerpt when available. The ZIP also includes `highlight-report.json` and `highlight-report.csv` so you can review or edit the timeline separately.

The score is a heuristic based on optional speech transcription, audio activity, and weak visual cues; it also gives a small positive bonus for observable hook signals in the first three seconds (early reaction phrases, laughter/humor, speech, and audio activity). A quiet opening is not automatically penalized. The hook score is not a retention prediction and is not a guarantee that a moment will perform well. Review every export before publishing. This workflow processes the uploaded source file only; it does not capture or download third-party live streams or VODs.


## Reaction & Rage Detector

The highlight ranker gives additional weight to explicit rage/frustration phrases in the transcript, alongside laughter, spontaneous reaction phrases, speech density, audio activity, and weak visual cues. The highlight report includes a separate rage score and matched phrases for review.

This is a heuristic signal, not reliable emotion recognition: transcription can be wrong, phrases can be sarcastic or playful, and loud audio alone is not treated as anger. Review clips before publishing and use source recordings you own or have permission to use.


## YouTube performance feedback tracker

The dashboard includes a manual YouTube Studio metrics tracker. Add a published video's format, content category, edit variant, views, engaged views, Shorts "stayed to watch", average view duration, average percentage viewed, long-form CTR, likes, comments, shares, and subscribers gained. The app stores entries in `outputs/performance.json` and compares category and edit-variant averages. It only shows a leading category or variant after at least three entries in that group.

The comparison score is an internal heuristic, not a viral prediction. Record the age of each video's metrics in hours (for example, 48) when entering results manually. CSV import also reads common publish-date columns and estimates the video's age at import time; an explicit measurement-age-hours column takes precedence. The dashboard separates results into 0–48 hours, 2–7 days, 7–30 days, and 30+ days, and compares categories and edit variants only within the same age window when enough data exists. It also reports engaged-view percentage and average likes, comments, shares, and subscribers gained per 1,000 views when those metrics are available; missing metrics are left blank rather than treated as zero. Entries without age data remain in the overall summaries but are excluded from age-window comparisons. Once a category has at least three results in the same format and age window, the ranker can apply a small confidence-adjusted bonus or penalty capped at ±3 points. You can import a CSV exported from YouTube Studio's Advanced mode. The importer supports common English and Swedish metric headers, asks for default category/format/edit variant when those fields are absent, skips unreadable rows, and detects repeated imports of the exact same file. It does not connect to a Google account or import analytics automatically; you export the CSV yourself.


### Cautious feedback-based ranking

Future candidate scores compare category results inside publication-age cohorts as well as within the same format. A category needs at least three examples in an age window; small samples are shrunk toward that cohort's baseline. Cohort-specific adjustments are combined by sample count and capped at ±3 ranking points. The report/dashboard shows the applied adjustment. This is lightweight calibration, not model training; it should not be treated as a causal conclusion from small or mismatched samples.


## Performance-based editing coach

The performance dashboard compares V1/V2/V3 on individual YouTube metrics within the same category, format, and publication-age cohort. It can surface evidence-led review prompts for Shorts hooks (stayed-to-watch), retention/pacing (average percentage viewed), average watch time, long-form packaging (click-through rate), and shareability (shares per 1,000 views). Each metric needs at least three valid measurements for every variant, and only meaningful gaps are shown. These are observational patterns, not proof that an edit caused the result; click-through rate mostly reflects packaging rather than the clip edit. The coach does not automatically alter or publish videos. When the next source video is analyzed, the clip selector also attaches a historical V1/V2/V3 hint to matching candidate categories when the same category and format have at least three examples for every variant. The dashboard marks the historically recommended export while still rendering all three versions. This hint is advisory and does not change candidate ranking, delete alternatives, or auto-publish.

## Optional AI clip reviewer (vision + transcript)

A second-pass reviewer can inspect up to three sampled still frames (opening, middle, ending) plus the available speech transcript for each selected highlight. It returns separate editorial scores for the hook, clarity, visual interest, framing/cropping, composition, overlay clutter, payoff, and story coherence, along with strengths, weaknesses, up to five concrete visual warnings, and one suggested edit. Framing checks look for visibly cut-off or poorly placed subjects; composition checks look for a clear subject and useful image space; overlay-clutter checks assess whether visible text/HUD elements compete with important content. These are visual estimates from three still frames, not full-motion analysis, OCR guarantees, or a prediction of views or actual audience retention.

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

The three suggestions are generated with local templates and transcript cues; they do not make an extra paid AI request or predict which hook will perform best. In batch exports, the three edit variants use one transcript-grounded hook each and burn it into the opening when a usable transcript is available. Check the wording against the footage before publishing. Nothing is uploaded or published automatically.

## Channel-adaptive ranking

The ranking can now make a small adjustment based on the channel's own saved YouTube results. It maps detected clip signals to the manually assigned performance categories, compares those results within the same format, and applies a bounded bonus or penalty only after at least three examples exist for a category. Small groups are statistically shrunk toward the format-wide average, and the dashboard displays the adjusted comparison and a confidence indicator. Variant/category recommendations also use this confidence-adjusted score.

The smart variant selector recommends V1, V2, or V3 only when each has at least three results in the same category, format, and publication-age cohort. It compares confidence-adjusted scores and shows the margin and sample counts; it does not silently remove the other variants or publish anything. This is lightweight adaptive calibration, not a trained machine-learning model or a viral-view prediction. The adjustment is deliberately capped at 3 ranking points, and results are more useful when videos are compared at similar ages and with enough samples.


### Klippgränser och reaktionsupptakt

Urvalet väger nu även in om ett klipp riskerar att börja eller sluta mitt i ett transkriberat ord/segment. Det ger en mindre poängjustering och visar en varning i dashboarden. Om en upptäckt reaktionsankare har ungefär 1–6 sekunders upptakt inne i klippet kan modellen ge en liten bonus; reaktioner som börjar nästan direkt vid klippets start kan få avdrag. Detta är en heuristik baserad på transkriptets tidsstämplar och upptäckta ankare, inte en garanti för perfekt klippning. Granska alltid klippgränserna manuellt.


### Payoff-tajming

Urvalet bedömer nu även när en upptäckt reaktion eller händelse inträffar i klippet. Tydliga talbaserade reaktionsankare väger tyngre än ljudtoppar och visuella signaler. En payoff i ungefär 68–90 procent av klippet kan få en liten bonus, medan en händelse efter 94 procent kan få avdrag eftersom det riskerar att saknas utrymme efter reaktionen. Dashboarden visar poäng, signaltyp och ungefärlig position. Detta är en heuristik, inte en förståelse av hela videons berättelse.


### Storyline Detector

Urvalet uppskattar nu om ett klipp innehåller en enkel händelsekedja: uppladdning före en upptäckt reaktion/händelse och efterspel efter den. Bedömningen använder tidsstämplar i transkriptet och befintliga tal-, ljud- och visuella reaktionsankare. Den kan ge en begränsad poängjustering och visar vilka delar som hittats i dashboarden. Detta är en tidsbaserad heuristik – systemet förstår inte säkert orsakssamband, ironi eller hela spelhändelsens sammanhang. Kontrollera därför klippen manuellt.


### Adaptiv klippgräns och klipplängd

Efter att ett kandidatögonblick har valts försöker systemet justera start och slut individuellt. Det kan ta bort kortare tysta partier i början/slutet och flytta en gräns för att undvika att kapa ett transkriptsegment eller ord. Den valda reaktionsankaren skyddas, och klippet behåller minst 75 % av den ursprungliga valda längden (med en femsekunders lägstanivå). Den här funktionen ändrar inte den manuella publiceringsprocessen. Justeringen bygger på transkriptets tidsstämplar och är inte en garanti för att visuellt sammanhang eller ljudlösa spelhändelser bevaras; granska därför varje klipp.


## Context-Aware Clip Selector – streamerreaktionen först

Klippens ranking ger nu en extra, begränsad prioritet till tydliga streamerreaktioner: skratt, spontana reaktionsuttryck, rage-uttryck och visuella reaktionssignaler. GTA-händelser används som sammanhang och deras separata poäng är avsiktligt begränsad. Ett gameplay-ögonblick utan tydlig streamerreaktion ska därför inte vinna enbart på många spelrelaterade nyckelord. Det här är fortfarande signalbaserad heuristik: den kan inte säkert avgöra ironi, känsloläge eller om en reaktion är genuin.


### Reaktionsstyrt urval – streamer före gameplay

- Tydliga streamerreaktioner (skratt, spontana utrop, frustration/rage och visuella reaktionssignaler) är den primära urvalssignalen.
- Klipp med tydlig reaktion får en extra reaktionsfokusbonus på 8 poäng.
- GTA-/gameplay-nyckelord ger endast en begränsad kontextpoäng (max 4,5). Gameplay-ögonblick utan tydlig streamerreaktion får ett avdrag på 12 poäng.
- Dashboarden och batchresultaten visar reaktionspoäng, gameplay-kontext och reaktionsfokusjustering separat.
- Detta är en heuristik baserad på transkript och tillgängliga visuella signaler. Den kan missa ironi, lågmälda reaktioner eller sammanhang och garanterar inte viralitet.


### Koppling mellan streamerreaktion och GTA-händelse

- Transkriberade segment med GTA-händelser jämförs tidsmässigt med efterföljande skratt, spontana utrop eller rage-uttryck.
- En händelse som inträffar högst 8 sekunder före en tydlig reaktion kan ge upp till 5 extra poäng.
- Kopplingen visas i dashboarden och följer med i batchens highlight-data.
- Detta är en tidsbaserad textheuristik, inte säker förståelse av bildinnehåll eller orsakssamband. Den kan missa händelser som inte nämns i talet.


### Audiovisuell kontextkoppling

- Reaktionskopplingen använder både talade GTA-händelser och tidsstämplade ljud-/bildsignaler.
- Om en tydlig streamerreaktion följer efter en talad GTA-händelse inom 8 sekunder kan den ge 5 poäng.
- Om händelsen inte nämns i talet kan en närliggande ljudtopp (högst 3 sekunder före reaktionen) ge 2 poäng, eller en visuell smile-signal ge 1 poäng.
- Ljud- och bildsignaler är endast svagt stöd för sammanhang; de bevisar inte vilken spelhändelse som orsakade reaktionen.
- Dashboard och exporter visar vilken evidenskälla som användes. Streamerreaktionen förblir den primära urvalssignalen.

## Source rights approval and provenance

Every video in the local source inbox must be explicitly approved before either the automatic watcher or manual inbox processing can queue it. In the dashboard, record the rights holder and choose one basis: your own material, written permission, or an applicable license; an optional source URL can also be saved. The user must actively confirm the rights statement. This is a workflow safeguard, not legal verification and not proof that the stated permission is valid.

Approval is bound to the file's SHA-256 fingerprint, not just its filename. If the file contents change, the old approval no longer applies and the new version must be approved. The app stores the provenance record in `outputs/source_authorizations.json` and copies the rights holder, permission basis, source URL, approval timestamp, and fingerprint into the batch-job metadata. Unapproved files remain in the inbox and are ignored by automatic ingestion. Review applicable platform terms, licenses, and permissions before using any recording; no third-party stream or video is downloaded by this feature.

## OneDrive source-folder integration

On Windows, the app automatically detects the OneDrive sync root from the `OneDrive`, `OneDriveCommercial`, or `OneDriveConsumer` environment variable. It then uses:

```text
OneDrive/AI Viral Video Clipper/Inbox
```

Create that folder inside your synced OneDrive and place recordings there. The existing source watcher scans it every 15 seconds, waits until a file is at least 30 seconds old, and processes only files with a matching explicit rights approval. After queueing, the original file is moved into the sibling `processed` folder, which is also synced by OneDrive. Only one automatic source batch is queued at a time.

To use another folder, set `CLIPPER_SOURCE_INBOX` to its full local path; this setting takes priority over automatic OneDrive detection. If OneDrive is not installed or synced on the machine running the app, the app falls back to the repository's `source_inbox/` folder.

This is a **OneDrive desktop-sync integration**, not a direct Microsoft Graph connection: OneDrive performs the cloud synchronization and the clipper reads the locally synced files. It does not request Microsoft account passwords or store Microsoft access tokens. The machine running the clipper must have OneDrive sync enabled and the selected folder available locally. On a hosted server without the OneDrive sync client, this method will not access the cloud. Rights approval is still required per exact file version, and nothing is published automatically.

## Direct OneDrive connection (Microsoft Graph)

The dashboard can connect to Microsoft OneDrive using Microsoft's device-code sign-in and Microsoft Graph. This is separate from the optional OneDrive desktop-sync folder. The app requests delegated read-only `Files.Read` and `User.Read` scopes; it does not request write access. The access token is held in application memory only and is cleared on disconnect or server restart. No Microsoft password, client secret, or refresh token is stored by the app.

### Microsoft app registration

An adult account administrator should create/configure the Microsoft Entra app registration and review the permissions/consent before connecting an account:

1. Register an application in Microsoft Entra ID.
2. Choose account types that support both organizational directories and personal Microsoft accounts, if both are needed.
3. Enable **Allow public client flows** (device-code flow).
4. Add Microsoft Graph **delegated** permissions `Files.Read` and `User.Read`.
5. Copy the Application (client) ID and configure it as the server environment variable `MICROSOFT_CLIENT_ID`. Do not paste IDs or secrets into chat; do not create a client secret for this public-client flow.

Restart the app, select **Anslut OneDrive**, open Microsoft's device login page, enter the displayed code, and then press **Kontrollera inloggning**. Create this folder in the connected OneDrive:

```text
AI Viral Video Clipper/Inbox
```

Select **Visa videor i OneDrive** and explicitly download only recordings you own or have permission/licensing to process. A downloaded file is staged in the normal source inbox but is **not** automatically approved or queued: confirm its rights in the regular source list first. The download endpoint also verifies that the selected item belongs to this exact OneDrive folder. The existing watcher can then process only the approved file.

The integration lists supported video files up to 2 GB, follows Microsoft Graph pagination for up to 10 pages (up to 1,000 entries) per refresh, downloads only after a manual click, and never publishes automatically. If more entries exist, the dashboard indicates that the list is capped. The Graph connection uses in-memory access tokens, so a server restart or token expiry requires signing in again. The API integration must run on a server with outbound access to Microsoft identity and Graph endpoints. Do not expose the local dashboard to untrusted networks; protect the host and its environment configuration.
