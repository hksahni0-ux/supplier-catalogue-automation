"""Render video.html frame by frame in Chrome and encode it with the soundtrack.

    python3 video/render.py --stills 5 20 40      # PNG previews in build/stills/
    python3 video/render.py                       # fci-demo.mp4 + fci-demo-thumbnail.png

Needs build/timing.json (voice.py) and assets/data.json (prepare.py). The soundtrack is
built by audio.py from the sound cues the page reports.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 30


def open_page(play, hash: str = ""):
    browser = play.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    data = (HERE / "assets" / "data.json").read_text()
    timing = (BUILD / "timing.json").read_text()
    page.add_init_script(f"window.DATA = {data}; window.TIMING = {timing};")
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type in ("warning", "error") else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto((HERE / "video.html").as_uri() + hash)
    page.evaluate("window.READY")
    if errors:
        print("page messages:\n  " + "\n  ".join(errors))
    return browser, page


def stills(times: list[float]) -> None:
    out = BUILD / "stills"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as play:
        browser, page = open_page(play)
        for t in times:
            page.evaluate(f"window.seek({t})")
            page.screenshot(path=str(out / f"t{t:06.2f}.png"))
            print(out / f"t{t:06.2f}.png")
        browser.close()


def thumbnail() -> Path:
    """The designed thumbnail (video.html#thumb), also embedded in the MP4 as its cover."""
    path = HERE / "fci-demo-thumbnail.png"
    with sync_playwright() as play:
        browser, page = open_page(play, "#thumb")
        page.screenshot(path=str(path))
        browser.close()
    return path


def full() -> None:
    timing = json.loads((BUILD / "timing.json").read_text())
    total = timing["total"]
    frames = int(round(total * FPS))
    silent = BUILD / "video.mp4"
    encoder = subprocess.Popen(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-f",
            "image2pipe",
            "-framerate",
            str(FPS),
            "-c:v",
            "mjpeg",
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "17",
            "-vf",
            "scale=in_range=pc:out_range=tv,format=yuv420p",
            "-color_range",
            "tv",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-r",
            str(FPS),
            str(silent),
        ],
        stdin=subprocess.PIPE,
    )
    assert encoder.stdin is not None
    with sync_playwright() as play:
        browser, page = open_page(play)
        (BUILD / "sfx.json").write_text(json.dumps(page.evaluate("window.SFX")))
        for n in range(frames):
            page.evaluate(f"window.seek({n / FPS})")
            encoder.stdin.write(page.screenshot(type="jpeg", quality=95))
            if n % 300 == 0:
                print(f"frame {n}/{frames}", flush=True)
        browser.close()
    encoder.stdin.close()
    if encoder.wait() != 0:
        sys.exit("video encode failed")
    subprocess.run([sys.executable, str(HERE / "audio.py")], check=True)
    cover = BUILD / "cover.jpg"  # MP4 cover art: JPEG, embedded as an attached picture
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(thumbnail()), "-q:v", "2", str(cover)], check=True)
    # No -shortest: with a one-frame cover stream it cuts the video short. All streams are the same length.
    subprocess.run(
        [
            FFMPEG, "-y", "-v", "error",
            "-i", str(silent), "-i", str(BUILD / "mix.wav"), "-i", str(cover),
            "-map", "0:v", "-map", "1:a", "-map", "2:v",
            "-c:v:0", "copy", "-c:v:1", "mjpeg", "-disposition:v:1", "attached_pic",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(HERE / "fci-demo.mp4"),
        ],
        check=True,
    )  # fmt: skip
    print(HERE / "fci-demo.mp4")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stills", nargs="*", type=float)
    parser.add_argument("--sfx", action="store_true", help="only write build/sfx.json")
    parser.add_argument("--thumbnail", action="store_true", help="only write fci-demo-thumbnail.png")
    args = parser.parse_args()
    if args.thumbnail:
        print(thumbnail())
    elif args.sfx:
        with sync_playwright() as play:
            browser, page = open_page(play)
            (BUILD / "sfx.json").write_text(json.dumps(page.evaluate("window.SFX")))
            browser.close()
    elif args.stills is not None:
        stills(args.stills)
    else:
        full()


if __name__ == "__main__":
    main()
