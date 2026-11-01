"""Voiceover, word timings and captions for the FCI demo.

    python3 video/voice.py      # build/voice.wav, build/timing.json, fci-demo.srt

Each scene is spoken separately so a scene starts exactly when its line does. Word
boundaries drive the on-screen cues (a number lands when it is said) and the captions.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from pathlib import Path

import edge_tts
import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
RATE = 44100
LEAD_IN = 1.6  # the opening frames show the thumbnail, so every preview of the video shows it


async def speak(text: str, voice: str, rate: str, mp3: Path) -> list[dict]:
    words = []
    stream = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary").stream()
    with mp3.open("wb") as handle:
        async for chunk in stream:
            if chunk["type"] == "audio":
                handle.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append(
                    {"t": chunk["offset"] / 1e7, "d": chunk["duration"] / 1e7, "text": chunk["text"]}
                )
    return words


def to_wav(src: Path, dest: Path) -> float:
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(RATE), str(dest)], check=True
    )
    return (dest.stat().st_size - 44) / (2 * RATE)


def stamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def captions(words: list[dict], limit: int = 7) -> str:
    """Short caption lines that break at punctuation or after `limit` words."""
    lines, current = [], []
    for word in words:
        current.append(word)
        if len(current) >= limit or re.search(r"[.,:;?!]$", word["raw"]):
            lines.append(current)
            current = []
    if current:
        lines.append(current)
    out = []
    for n, line in enumerate(lines, 1):
        end = line[-1]["t"] + line[-1]["d"] + 0.25
        out.append(f"{n}\n{stamp(line[0]['t'])} --> {stamp(end)}\n{' '.join(w['raw'] for w in line)}\n")
    return "\n".join(out)


def attach_punctuation(text: str, words: list[dict]) -> None:
    """Edge TTS reports bare words; take each word's spelling and punctuation from the script."""
    tokens = text.split()
    cursor = 0
    for word in words:
        bare = re.sub(r"\W", "", word["text"].lower())
        for k in range(cursor, len(tokens)):
            if bare and bare in re.sub(r"\W", "", tokens[k].lower()):
                word["raw"] = tokens[k]
                cursor = k + 1
                break
        else:
            word["raw"] = word["text"]


async def main() -> None:
    script = json.loads((HERE / "script.json").read_text())
    BUILD.mkdir(exist_ok=True)
    t, scenes, words, pieces = LEAD_IN, [], [], []
    for i, scene in enumerate(script["scenes"]):
        mp3, wav = BUILD / f"{i:02d}-{scene['id']}.mp3", BUILD / f"{i:02d}-{scene['id']}.wav"
        spoken = await speak(scene["text"], script["voice"], script["rate"], mp3)
        attach_punctuation(scene["text"], spoken)
        length = to_wav(mp3, wav)
        last = i == len(script["scenes"]) - 1
        span = length + (script["tail"] if last else script["gap"])
        scenes.append(
            {"id": scene["id"], "start": round(t, 3), "end": round(t + span, 3), "speech": round(length, 3)}
        )
        words += [{**w, "t": round(t + w["t"], 3), "scene": scene["id"]} for w in spoken]
        pieces.append((wav, t))
        t += span
        print(f"{scene['id']:9} {length:6.2f}s")
    total = round(t, 3)
    track = [str(p) for p, _ in pieces]
    delays = ";".join(f"[{k}:a]adelay={round(s * 1000)}:all=1[v{k}]" for k, (_, s) in enumerate(pieces))
    mix = "".join(f"[v{k}]" for k in range(len(pieces)))
    args = [FFMPEG, "-y", "-v", "error"]
    for path in track:
        args += ["-i", path]
    args += [
        "-filter_complex",
        f"{delays};{mix}amix=inputs={len(pieces)}:normalize=0,apad=whole_dur={total}",
        "-t",
        str(total),
        "-ar",
        str(RATE),
        "-ac",
        "1",
        str(BUILD / "voice.wav"),
    ]
    subprocess.run(args, check=True)
    (BUILD / "timing.json").write_text(
        json.dumps({"total": total, "scenes": scenes, "words": words}, indent=1)
    )
    (HERE / "fci-demo.srt").write_text(captions(words))
    print(f"total {total:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
