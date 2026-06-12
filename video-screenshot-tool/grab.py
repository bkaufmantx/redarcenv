#!/usr/bin/env python3
"""
grab.py — Pull exact screenshots from a video at specific timestamps, on demand.

This is the on-demand half of the tool. Workflow: process_video.py transcribes
the video (the map); Claude reads transcript.json, decides which moments matter,
then calls this to seek those exact timestamps. No blanket grid — frames exist
only because they were needed, at the precise moment, not the nearest sample.

Each grab is a single fast ffmpeg seek (`-ss <t> -i video -frames:v 1`) and is
saved as frames/HH-MM-SS.jpg inside the video's output folder.

Usage:
    grab.py <video-or-output-folder> <timestamp> [<timestamp> ...]

Targets:
    a folder under output/   -> uses its source.* video, writes to its frames/
    a video file directly    -> writes a frames/ folder next to the video

Timestamps accept:
    262        seconds
    262.5      seconds (sub-second precision is honored)
    4:22       MM:SS
    1:04:22    HH:MM:SS

Examples:
    grab.py output/demo 4:22 5:10 6:03
    grab.py output/demo 262.5
    grab.py ~/Movies/demo.mp4 90
"""

import shutil
import subprocess
import sys
from pathlib import Path


def _find(binary):
    found = shutil.which(binary)
    if found:
        return found
    for cand in (f"/opt/homebrew/bin/{binary}", f"/usr/local/bin/{binary}"):
        if Path(cand).exists():
            return cand
    return None


FFMPEG = _find("ffmpeg")


def parse_ts(s):
    """Parse seconds | MM:SS | HH:MM:SS -> float seconds."""
    s = s.strip()
    if ":" in s:
        parts = [float(p) for p in s.split(":")]
        total = 0.0
        for p in parts:
            total = total * 60 + p
        return total
    return float(s)


def hhmmss(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}-{m:02d}-{s:02d}"


def resolve_target(target):
    """Return (video_path, frames_dir) for a folder or a video file."""
    p = Path(target).expanduser().resolve()
    if p.is_dir():
        sources = sorted(p.glob("source.*"))
        if not sources:
            # fall back to any video in the folder
            sources = sorted(
                f for f in p.iterdir()
                if f.suffix.lower() in (".mp4", ".mov", ".m4v", ".mkv", ".avi")
            )
        if not sources:
            raise SystemExit(f"!! no source video found in folder: {p}")
        return sources[0], p / "frames"
    if p.is_file():
        return p, p.parent / "frames"
    raise SystemExit(f"!! not found: {p}")


def grab(video, frames_dir, t):
    frames_dir.mkdir(parents=True, exist_ok=True)
    dest = frames_dir / f"{hhmmss(t)}.jpg"
    # Input seek (-ss before -i) is fast and frame-accurate enough for stills.
    proc = subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
         "-ss", f"{t:.3f}", "-i", str(video),
         "-frames:v", "1", "-q:v", "2", str(dest)],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0 or not dest.exists():
        print(f"!! failed @ {t:.2f}s: {proc.stderr.strip()[:200]}")
        return None
    print(f"  {hhmmss(t)}  ->  {dest}")
    return dest


def main(argv):
    if FFMPEG is None:
        raise SystemExit("!! ffmpeg not found. Install with: brew install ffmpeg")
    if len(argv) < 3:
        print(__doc__)
        return 1
    video, frames_dir = resolve_target(argv[1])
    print(f"grabbing from {video.name} -> {frames_dir}")
    for raw in argv[2:]:
        try:
            grab(video, frames_dir, parse_ts(raw))
        except ValueError:
            print(f"!! bad timestamp: {raw!r} (use seconds, MM:SS, or HH:MM:SS)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
