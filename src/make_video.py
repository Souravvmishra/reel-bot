#!/usr/bin/env python3
"""
Turn a still image into an MP4 reel (default: 8 seconds, 30 fps, 1080x1920).

Includes motion so it feels like a real reel:
  - Ken Burns slow zoom-in (--zoom 0.12, set 0 to disable)
  - fade in / fade out (--no-fade to disable)

Uses the ffmpeg binary bundled with imageio-ffmpeg (installed in .venv).
Run with:  .venv/bin/python make_video.py
"""

import argparse
import struct
import subprocess

import imageio_ffmpeg


def audio_duration(path):
    """Duration of an audio file in seconds (parsed from ffmpeg -i)."""
    import re
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out = subprocess.run([ff, "-hide_banner", "-i", path],
                         capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out.stderr)
    if not m:
        return None
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def png_size(path):
    """Read a PNG's (width, height) from its header without decoding."""
    with open(path, "rb") as f:
        head = f.read(24)
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def main():
    p = argparse.ArgumentParser(description="Make an MP4 reel from a still image")
    p.add_argument("--image", default="post-reel.png")
    p.add_argument("--output", default="post-reel.mp4")
    p.add_argument("--seconds", type=float, default=8.0)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--zoom", type=float, default=0.12,
                   help="Ken Burns zoom-in amount (0.12 = a 12-percent zoom "
                        "over the clip; 0 disables)")
    p.add_argument("--no-fade", action="store_true",
                   help="disable fade in/out")
    p.add_argument("--audio", default=None,
                   help="audio file (mp3/m4a/wav) to mux in; looped to fit "
                        "the clip")
    p.add_argument("--audio-start", type=float, default=0.0,
                   help="start offset in seconds into the audio file "
                        "(e.g. 3.89 = last 8s of an ~11.9s track)")
    args = p.parse_args()

    w, h = png_size(args.image)
    frames = max(1, round(args.fps * args.seconds))
    ff = imageio_ffmpeg.get_ffmpeg_exe()

    if args.zoom > 0:
        # zoompan is smoother when the input is upscaled first
        step = args.zoom / frames
        vf = (
            f"scale={w * 2}:{h * 2},"
            f"zoompan=z='min(zoom+{step:.6f},{1 + args.zoom:.4f})'"
            f":d={frames}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s={w}x{h}:fps={args.fps}"
        )
        inputs = [["-i", args.image]]
    else:
        vf = f"scale={w}:{h},fps={args.fps}"
        inputs = [["-loop", "1", "-framerate", str(args.fps), "-i", args.image]]

    if not args.no_fade:
        vf += f",fade=t=in:st=0:d=0.5,fade=t=out:st={args.seconds - 0.5:.2f}:d=0.5"
    vf += ",format=yuv420p"

    cmd = [ff, "-y"]
    if args.audio:
        dur = audio_duration(args.audio)
        # only loop when the track is shorter than the clip (avoids
        # non-monotonic-DTS warnings when it already fills the clip)
        if dur is not None and dur < args.seconds:
            cmd += ["-stream_loop", "-1"]
        cmd += ["-ss", str(args.audio_start), "-i", args.audio]
    for inp in inputs:
        cmd += inp
    cmd += ["-vf", vf, "-t", str(args.seconds), "-r", str(args.fps),
            "-c:v", "libx264", "-movflags", "+faststart"]
    if args.audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += [args.output]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Wrote {args.output} ({args.seconds}s @ {args.fps}fps, "
          f"zoom={args.zoom}, fade={'on' if not args.no_fade else 'off'}, "
          f"audio={args.audio or 'none'})")


if __name__ == "__main__":
    main()
