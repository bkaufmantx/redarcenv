# RedArc Video Screenshot Tool

Turn a screen-demo MP4 into a **timestamped Whisper transcript** that Claude
reads to grab the **exact screenshots it needs, on demand** — instead of
pre-dumping a frame every few seconds. The point: when you say *"show me where
Zak opens the rate sheet,"* Claude searches the transcript, finds the timecode,
and pulls that precise frame — no scrubbing, no wall of redundant images.

## The model: transcribe up front, grab frames on demand

| Step | When | What |
|---|---|---|
| **Transcribe** → `manifest.json` | Always, up front | The map: every spoken line with exact timestamps |
| **Grab exact frame(s)** | On demand, Claude's judgment | One ffmpeg seek at the precise moment |
| **Blanket / scene frames** | Opt-in (`RAVT_FRAMES`) | Only for silent stretches you need to eyeball |

Frames exist only because they were needed — and at the exact timestamp, not the
nearest 4-second sample.

## How to use it (drag-drop)

1. Drag one or more `.mp4` / `.mov` files onto **`RedArc Video Tool.app`**.
2. A Terminal window opens and transcribes (first run downloads the model once).
3. The `output/` folder opens. You now have the transcript + manifest.
4. Ask Claude for the moment you want — it grabs that frame for you.

Or from the command line:

```sh
./venv/bin/python ./process_video.py /path/to/demo.mp4     # transcribe
./venv/bin/python ./grab.py output/demo 4:22 5:10          # grab on demand
```

## What you get

```
output/demo/
  source.mp4          copy of the original (so grabs work anytime later)
  transcript.txt      readable, [MM:SS]-prefixed
  transcript.json     [{start, end, text}, ...]
  manifest.json       segments + timestamps (frame links fill in as you grab)
  frames/             created on demand
    00-04-22.jpg      ← only the moments that were actually needed
```

### Transcript
Local **faster-whisper** (`small.en`) transcribes the audio with real timestamps
— no API key, no per-video cost, runs offline. Your hand transcript isn't needed;
the audio is the source of truth.

## Grabbing frames on demand — `grab.py`

```sh
./venv/bin/python ./grab.py <video-or-output-folder> <timestamp> [<timestamp> ...]
```

Timestamps accept seconds (`262`, `262.5`), `MM:SS` (`4:22`), or `HH:MM:SS`.
Each grab seeks that exact point and saves `frames/HH-MM-SS.jpg`. Examples:

```sh
./venv/bin/python ./grab.py output/demo 4:22 5:10 6:03
./venv/bin/python ./grab.py ~/Movies/demo.mp4 90
```

## How Claude uses this

Point Claude at `output/<video-name>/manifest.json`. It reads the segment `text`,
finds the line you mean, then runs `grab.py` at that timecode and reads the image
— all in one step. You just ask: *"grab the screen where Kristin filters item
codes."*

## When narration is silent

On-demand relies on the transcript describing the moment. If something important
happens with no narration, pre-extract frames for that case:

```sh
RAVT_FRAMES=scene ./venv/bin/python ./process_video.py demo.mp4   # frame per visual change
RAVT_FRAMES=both  ./venv/bin/python ./process_video.py demo.mp4   # scene + every-4s floor
```

## Tuning (optional env vars)

| Var | Default | Effect |
|---|---|---|
| `RAVT_FRAMES`| `none` | `none` (on-demand) · `scene` · `interval` · `both` |
| `RAVT_MODEL` | `small.en` | Whisper model: `base.en` (faster), `medium.en` (more accurate) |
| `RAVT_FLOOR` | `4` | Interval-mode seconds between forced frames |
| `RAVT_SCENE` | `0.30` | Scene sensitivity (0–1); lower = more scene frames |
| `RAVT_OUTPUT`| `./output` | Where result folders are written |

## Requirements (already installed on this machine)
- `ffmpeg` (Homebrew) — seeking + frame extraction
- Python venv at `./venv` with `faster-whisper`

If moved to another Mac: `brew install ffmpeg`, then
`python3 -m venv venv && ./venv/bin/pip install faster-whisper`.
