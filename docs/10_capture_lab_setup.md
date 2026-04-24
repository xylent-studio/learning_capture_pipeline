# Capture lab setup

## Capture workstation

Recommended:

- dedicated machine or VM
- Chrome or Edge
- 1920x1080+ display
- stable network
- approved SeedTalent account
- password manager for credentials
- OBS or FFmpeg installed
- local artifact folder excluded by `.gitignore`

## Browser settings

- fixed viewport
- zoom 100%
- no unrelated browser extensions
- no notifications/popups
- one SeedTalent tab unless testing requires otherwise

## Audio setup

macOS:

- OBS desktop audio where possible
- virtual audio device if needed

Windows:

- OBS desktop audio or VB-Cable if needed

Linux:

- PulseAudio/PipeWire monitor capture

## Local artifacts

Never commit capture artifacts. Store locally in:

```text
captures/<capture_batch_id>/<capture_session_id>/
```

Expected contents:

```text
recording.mp4
screenshots/
events.jsonl
operator_notes.md
qa_report.json
```

## Test fixtures

Use fake local HTML training pages and synthetic media only. Do not put real SeedTalent content in fixtures.
