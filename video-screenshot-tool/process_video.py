#!/usr/bin/env python3
"""
process_video.py — Turn an MP4 screen demo into a timestamped Whisper transcript
that Claude reads to grab the exact screenshots it needs, on demand.

By default this does NOT pre-extract a wall of screenshots. The transcript is the
map; Claude reads it, decides which moments matter, and pulls those exact frames
with grab.py (one ffmpeg seek each). Frames exist only because they were needed.

For each input video it produces an output folder:

    output/<video-name>/
        source.mp4            copy of the original (so grabs work later)
        transcript.json       Whisper segments: [{start, end, text}, ...]
        transcript.txt        plain readable transcript with [MM:SS] prefixes
        manifest.json         segments + timestamps (frames filled in on demand)
        frames/HH-MM-SS.jpg   created on demand by grab.py (or by --frames mode)

Frame modes (RAVT_FRAMES, default "none"):
    none      transcribe only — grab frames later with grab.py  (recommended)
    scene     pre-extract a frame on every visual scene change   (silent stretches)
    interval  pre-extract a frame every FLOOR_SECONDS            (blanket grid)
    both      scene + interval floor

Transcription is local faster-whisper (no API key, no per-video cost).

Usage:
    process_video.py VIDEO.mp4 [VIDEO2.mp4 ...]

Env overrides:
    RAVT_FRAMES       none | scene | interval | both   (default: none)
    RAVT_MODEL        whisper model (default: small.en)   e.g. base.en, medium.en
    RAVT_SCENE        scene threshold 0-1 (default: 0.30)  lower = more frames
    RAVT_FLOOR        max seconds between forced frames (default: 4)
    RAVT_OUTPUT       output root (default: ./output next to this script)
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = Path(os.environ.get("RAVT_OUTPUT", SCRIPT_DIR / "output"))
WHISPER_MODEL = os.environ.get("RAVT_MODEL", "small.en")
SCENE_THRESHOLD = float(os.environ.get("RAVT_SCENE", "0.30"))
FLOOR_SECONDS = float(os.environ.get("RAVT_FLOOR", "4"))
FRAMES_MODE = os.environ.get("RAVT_FRAMES", "none").lower()  # none|scene|interval|both

# Resolve ffmpeg/ffprobe whether or not they're on PATH (the droplet runs with a
# minimal environment, so check the common Homebrew locations too).
def _find(binary):
    found = shutil.which(binary)
    if found:
        return found
    for cand in (f"/opt/homebrew/bin/{binary}", f"/usr/local/bin/{binary}"):
        if Path(cand).exists():
            return cand
    return None

FFMPEG = _find("ffmpeg")
FFPROBE = _find("ffprobe")


def log(msg):
    print(msg, flush=True)


def hhmmss(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}-{m:02d}-{s:02d}"


def mmss(seconds):
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def probe_duration(video):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def extract_frames(video, frames_dir, duration):
    """Extract a frame on every meaningful scene change PLUS a guaranteed frame
    every FLOOR_SECONDS, then merge and de-dupe.

    Two passes, each producing frames whose real timestamp is known *without*
    fragile stderr scraping:
      1. interval floor -> `fps=1/FLOOR`. The k-th emitted frame is at
         (k-1)*FLOOR seconds by construction, so we name it from its index.
         This is the backbone: a static screen is still sampled regularly and
         nothing is ever missed for more than FLOOR seconds.
      2. scene changes  -> `select='gt(scene,THRESH)'` with
         `metadata=print:file=...`, which writes one deterministic block per
         emitted frame (frame:N pts_time:T). We read T straight from that file.
         This catches the moments *between* floor samples where the UI changes.

    ffmpeg's scene score is luma-based, so it won't fire on every visual change
    (e.g. red->green); the floor pass is what guarantees coverage regardless.
    """
    frames_dir.mkdir(parents=True, exist_ok=True)
    tmp = frames_dir / "_tmp"
    tmp.mkdir(exist_ok=True)

    candidates = []  # list of (time_seconds, source_jpg_path)

    # Pass 1: interval floor — deterministic index-based timestamps.
    if FRAMES_MODE in ("interval", "both"):
        subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video),
             "-vf", f"fps=1/{FLOOR_SECONDS}", "-q:v", "3",
             str(tmp / "interval_%05d.jpg")],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        for f in sorted(tmp.glob("interval_*.jpg")):
            idx = int(f.stem.split("_")[1])          # 1-based
            t = (idx - 1) * FLOOR_SECONDS
            candidates.append((t, f))

    # Pass 2: scene changes — exact timestamps from a metadata sidecar file.
    if FRAMES_MODE in ("scene", "both"):
        meta_file = tmp / "scene_meta.txt"
        subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video),
             "-vf", f"select='gt(scene,{SCENE_THRESHOLD})',metadata=print:file={meta_file}",
             "-vsync", "vfr", "-q:v", "3", str(tmp / "scene_%05d.jpg")],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        scene_times = _parse_metadata_times(meta_file)
        scene_jpgs = sorted(tmp.glob("scene_*.jpg"))
        for f, t in zip(scene_jpgs, scene_times):     # counts match by construction
            candidates.append((t, f))

    # Merge: sort by time, drop near-duplicates (<1s apart), name by timestamp.
    candidates.sort(key=lambda x: x[0])
    kept = []
    last_t = -999.0
    for t, f in candidates:
        if t - last_t < 1.0:
            continue
        dest = frames_dir / f"{hhmmss(t)}.jpg"
        if dest.exists():                          # same HH-MM-SS already kept
            continue
        shutil.copy2(str(f), str(dest))
        kept.append({"time": round(t, 2), "file": dest.name})
        last_t = t

    shutil.rmtree(tmp, ignore_errors=True)
    log(f"  frames: {len(kept)} extracted")
    return kept


def _parse_metadata_times(meta_file):
    """Read pts_time:<float> from an ffmpeg metadata=print sidecar file, in the
    order frames were emitted (one 'frame:.. pts_time:..' line per frame)."""
    times = []
    if not meta_file.exists():
        return times
    for line in meta_file.read_text(errors="ignore").splitlines():
        if "pts_time:" in line:
            try:
                times.append(float(line.split("pts_time:")[1].split()[0]))
            except (IndexError, ValueError):
                pass
    return times


def transcribe(video):
    """Local faster-whisper transcription -> list of {start, end, text}."""
    from faster_whisper import WhisperModel

    log(f"  transcribing with faster-whisper '{WHISPER_MODEL}' (first run downloads the model)...")
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(video), vad_filter=True)
    out = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            out.append({"start": round(seg.start, 2),
                        "end": round(seg.end, 2),
                        "text": text})
    log(f"  transcript: {len(out)} segments")
    return out


def build_manifest(video_name, duration, frames, segments):
    """Link each transcript segment to the frame nearest its midpoint."""
    frame_times = [f["time"] for f in frames]

    def nearest_frame(t):
        if not frames:
            return None
        best_i = min(range(len(frame_times)), key=lambda i: abs(frame_times[i] - t))
        return frames[best_i]

    linked = []
    for seg in segments:
        mid = (seg["start"] + seg["end"]) / 2
        nf = nearest_frame(mid)
        linked.append({
            "start": seg["start"],
            "end": seg["end"],
            "timecode": mmss(seg["start"]),
            "text": seg["text"],
            "frame": nf["file"] if nf else None,
            "frame_time": nf["time"] if nf else None,
        })

    return {
        "video": video_name,
        "duration_seconds": round(duration, 2),
        "frame_count": len(frames),
        "segment_count": len(segments),
        "settings": {
            "whisper_model": WHISPER_MODEL,
            "scene_threshold": SCENE_THRESHOLD,
            "floor_seconds": FLOOR_SECONDS,
        },
        "frames": frames,
        "segments": linked,
    }


def write_transcript_txt(path, segments):
    lines = [f"[{mmss(s['start'])}] {s['text']}" for s in segments]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def process(video_path):
    video = Path(video_path).expanduser().resolve()
    if not video.exists():
        log(f"!! not found: {video}")
        return
    if FFMPEG is None or FFPROBE is None:
        log("!! ffmpeg/ffprobe not found. Install with: brew install ffmpeg")
        return

    name = video.stem
    out_dir = OUTPUT_ROOT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"\n=== {video.name} -> {out_dir}")

    duration = probe_duration(video)
    log(f"  duration: {mmss(duration)}")

    # Keep a self-contained copy of the source alongside its derivatives.
    try:
        shutil.copy2(video, out_dir / f"source{video.suffix}")
    except shutil.SameFileError:
        pass

    # Transcribe first — it's the map. Frames are pre-extracted only if asked;
    # otherwise grab.py pulls exact frames on demand later.
    segments = transcribe(video)
    if FRAMES_MODE in ("scene", "interval", "both"):
        frames = extract_frames(video, out_dir / "frames", duration)
    else:
        frames = []
        log("  frames: none (on-demand — use grab.py to pull exact timestamps)")

    manifest = build_manifest(video.name, duration, frames, segments)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out_dir / "transcript.json").write_text(json.dumps(segments, indent=2), encoding="utf-8")
    write_transcript_txt(out_dir / "transcript.txt", segments)

    log(f"  done: {out_dir}")
    return out_dir


def main(argv):
    if len(argv) < 2:
        log("usage: process_video.py VIDEO.mp4 [VIDEO2.mp4 ...]")
        return 1
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for v in argv[1:]:
        try:
            process(v)
        except Exception as e:
            log(f"!! error processing {v}: {e}")
    log("\nAll done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
