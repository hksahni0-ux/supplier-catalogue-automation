"""Original soundtrack for the FCI demo: music bed, sound effects, and the final mix.

    python3 video/audio.py      # build/music.wav, build/sfx.wav, build/mix.wav (-16 LUFS)

The music is synthesised here (no samples, nothing reused): a felt-piano arpeggio over a
soft pad in D major at 76 BPM, with bass and a light shaker joining once the demo starts.
It ducks under the voice. Sound effects are placed at the cues the page reports
(build/sfx.json): chapter wipes, numbers landing, ticks, stamps.
"""

from __future__ import annotations

import json
import re
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SR = 44100
BPM = 76
BEAT = 60 / BPM
rng = np.random.default_rng(7)  # fixed seed: the same soundtrack on every render


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as handle:
        data = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)
    return data.astype(np.float32) / 32768


def write_wav(path: Path, signal: np.ndarray) -> None:
    clipped = np.clip(signal, -1, 1)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2 if signal.ndim == 2 else 1)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes((clipped * 32767).astype(np.int16).tobytes())


def add(track: np.ndarray, sound: np.ndarray, at: float, gain: float = 1.0) -> None:
    start = int(at * SR)
    if start >= len(track) or start + len(sound) <= 0:
        return
    end = min(len(track), start + len(sound))
    track[start:end] += sound[: end - start] * gain


# ---------------------------------------------------------------- instruments
def piano(midi: float, length: float, velocity: float) -> np.ndarray:
    """A soft felt-piano note: a few slightly stretched partials, each decaying faster than the last."""
    t = np.arange(int(length * SR)) / SR
    f = hz(midi)
    note = np.zeros_like(t)
    for n in range(1, 7):
        partial = f * n * (1 + 0.0004 * n * n)
        note += np.sin(2 * np.pi * partial * t) * (1 / n**1.6) * np.exp(-t * (1.2 + 0.9 * n))
    attack = np.minimum(1, t / 0.012)
    hammer = np.exp(-t * 120) * rng.normal(0, 0.02, len(t))  # the felt touch
    return (note * attack + hammer) * velocity


def pad(midis: list[int], length: float) -> np.ndarray:
    t = np.arange(int(length * SR)) / SR
    out = np.zeros_like(t)
    for m in midis:
        for cents in (-6, 5):
            f = hz(m + cents / 100)
            out += np.sin(2 * np.pi * f * t) + 0.18 * np.sin(2 * np.pi * 2 * f * t)
    envelope = np.minimum(1, t / 1.6) * np.minimum(1, (length - t) / 1.4)
    shimmer = 1 + 0.06 * np.sin(2 * np.pi * 0.23 * t)
    return out * envelope * shimmer / (2 * len(midis))


def bass(midi: int, length: float) -> np.ndarray:
    t = np.arange(int(length * SR)) / SR
    f = hz(midi)
    tone = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    return tone * np.minimum(1, t / 0.03) * np.exp(-t * 1.6)


def noise_burst(length: float, colour: int) -> np.ndarray:
    """White noise smoothed by a short moving average: larger `colour` means darker."""
    n = rng.normal(0, 1, int(length * SR) + colour)
    return np.convolve(n, np.ones(colour) / colour, mode="valid")[: int(length * SR)]


def shaker(length: float = 0.09) -> np.ndarray:
    n = rng.normal(0, 1, int(length * SR))
    n = np.diff(n, prepend=0)  # brighter: keep the top end only
    t = np.arange(len(n)) / SR
    return n * np.exp(-t * 55) * np.minimum(1, t / 0.004)


# ---------------------------------------------------------------- the piece
# D major. Each chord lasts two bars; the arpeggio walks up and back in eighth notes.
CHORDS = [
    (50, [62, 66, 69, 73, 76]),  # Dmaj9
    (47, [59, 62, 66, 69, 73]),  # Bm9
    (43, [59, 62, 66, 69, 71]),  # Gmaj9 (B D F# A)
    (45, [57, 61, 64, 69, 71]),  # A add9
]
PATTERN = [0, 2, 3, 4, 3, 2, 1, 2, 0, 2, 3, 4, 3, 4, 2, 3]  # 16 eighths = two bars


def music(total: float, scenes: dict[str, dict]) -> np.ndarray:
    n = int(total * SR) + SR
    keys, low = np.zeros(n), np.zeros(n)
    start_band = scenes["run"]["start"] - 2 * BEAT
    end_band = scenes["creator"]["start"]
    eighth = BEAT / 2
    bars2 = 8 * BEAT
    k = 0
    t = 0.0
    while t < total + 2:
        root, tones = CHORDS[k % len(CHORDS)]
        final = t >= end_band - 0.01
        add(low, pad(tones[:4], bars2 + 1.2), t, 0.32 if not final else 0.42)
        for i, step in enumerate(PATTERN):
            at = t + i * eighth
            if at > total:
                break
            swing = 0.012 * (i % 2)  # a hint of human timing
            velocity = (0.55 if i % 4 == 0 else 0.38) * (0.9 + 0.2 * rng.random())
            if final and i > 0:
                break
            add(keys, piano(tones[step], 2.4 if not final else 5.0, velocity), at + swing)
        if start_band <= t < end_band:
            add(low, bass(root - 12, 2 * BEAT), t, 0.5)
            add(low, bass(root - 12, 2 * BEAT), t + 4 * BEAT, 0.42)
            add(low, bass(root - 12 + 7, 1.5 * BEAT), t + 6 * BEAT, 0.3)
            for b in range(16):
                if b % 2 == 1:
                    add(low, shaker(), t + b * eighth, 0.05 if b % 4 == 3 else 0.03)
        t += bars2
        k += 1
        if final:
            break
    # a room around the keys and pad: exponentially decaying noise as the impulse response
    ir_t = np.arange(int(1.9 * SR)) / SR
    ir = rng.normal(0, 1, len(ir_t)) * np.exp(-ir_t * 3.2)
    ir = np.convolve(ir, np.ones(12) / 12, mode="same")
    ir /= np.sqrt(np.sum(ir**2))
    dry = keys + low
    size = 1 << int(np.ceil(np.log2(len(dry) + len(ir))))
    wet = np.fft.irfft(np.fft.rfft(dry, size) * np.fft.rfft(ir, size), size)[: len(dry)]
    mix = 0.78 * dry + 0.32 * wet
    fade = np.ones(len(mix))
    fin = int(1.2 * SR)
    fade[:fin] = np.linspace(0, 1, fin)
    out_len = int(total * SR)
    tail = int(3.5 * SR)
    fade[out_len - tail : out_len] = np.linspace(1, 0, tail) ** 1.5
    fade[out_len:] = 0
    return (mix * fade)[:out_len]


# ---------------------------------------------------------------- sound effects
def sfx_sound(kind: str) -> np.ndarray:
    if kind == "wipe":  # a soft sheet sliding past: noise that brightens then fades
        length = 0.55
        t = np.arange(int(length * SR)) / SR
        dark, bright = noise_burst(length, 18), noise_burst(length, 3)
        mixk = np.clip(t / length * 1.6, 0, 1)
        env = np.sin(np.pi * np.clip(t / length, 0, 1)) ** 1.6
        return (dark * (1 - mixk) + bright * mixk * 0.6) * env * 0.5
    if kind == "tick":  # a light wooden tick
        t = np.arange(int(0.08 * SR)) / SR
        return (np.sin(2 * np.pi * 2350 * t) * 0.5 + np.sin(2 * np.pi * 1170 * t)) * np.exp(-t * 85) * 0.35
    if kind == "land":  # a number settling: a soft low knock and a tuned bell (D6)
        t = np.arange(int(0.9 * SR)) / SR
        drop = 2 * np.pi * np.cumsum(150 - 60 * np.minimum(1, t / 0.08)) / SR
        knock = np.sin(drop) * np.exp(-t * 22)
        bell = (np.sin(2 * np.pi * hz(86) * t) + 0.3 * np.sin(2 * np.pi * hz(86) * 2.76 * t)) * np.exp(-t * 5)
        return knock * 0.55 + bell * 0.12
    if kind == "stamp":
        t = np.arange(int(0.35 * SR)) / SR
        thud = np.sin(2 * np.pi * 85 * t) * np.exp(-t * 18)
        slap = noise_burst(0.35, 6) * np.exp(-t * 60)
        return thud * 0.7 + slap * 0.5
    if kind == "sweep":  # many cells lighting up: a rising, airy shimmer
        length = 1.4
        t = np.arange(int(length * SR)) / SR
        f = 900 + 1500 * (t / length) ** 1.5
        tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
        env = np.sin(np.pi * t / length) ** 2
        return (tone * 0.12 + noise_burst(length, 2) * 0.05) * env
    raise ValueError(kind)


def effects(total: float, cues: list[dict]) -> np.ndarray:
    track = np.zeros(int(total * SR))
    for cue in cues:
        add(track, sfx_sound(cue["kind"]), cue["t"], cue.get("v", 1.0))
    return track


# ---------------------------------------------------------------- mix
def envelope(voice: np.ndarray) -> np.ndarray:
    """How much speech is present at each moment, 0..1, with a fast attack and a slow release."""
    hop = 441
    frames = np.sqrt(np.convolve(voice**2, np.ones(hop) / hop, mode="same")[::hop])
    level = np.clip(frames / (np.percentile(frames, 90) + 1e-9), 0, 1)
    smooth = np.zeros_like(level)
    for i in range(1, len(level)):
        coef = 0.5 if level[i] > smooth[i - 1] else 0.06
        smooth[i] = smooth[i - 1] + coef * (level[i] - smooth[i - 1])
    return np.interp(np.arange(len(voice)), np.arange(len(smooth)) * hop, smooth)


def loudnorm(src: Path, dest: Path) -> str:
    first = subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-i",
            str(src),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", first, re.S).group(0))  # type: ignore[union-attr]
    second = (
        f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
        f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}"
        ":linear=true:print_format=summary"
    )
    out = subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-i", str(src), "-af", second, "-ar", str(SR), str(dest)],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    return out[out.find("Output Integrated") :].split("\n")[0]


def main() -> None:
    timing = json.loads((BUILD / "timing.json").read_text())
    total = timing["total"]
    scenes = {s["id"]: s for s in timing["scenes"]}
    voice = read_wav(BUILD / "voice.wav")
    voice = np.pad(voice, (0, max(0, int(total * SR) - len(voice))))[: int(total * SR)]
    bed = music(total, scenes)
    fx = effects(total, json.loads((BUILD / "sfx.json").read_text()))
    write_wav(BUILD / "music.wav", bed)
    write_wav(BUILD / "sfx.wav", fx)

    speech = envelope(voice)
    rms = lambda x: float(np.sqrt(np.mean(x[np.abs(x) > 1e-4] ** 2)))  # noqa: E731
    music_gain = rms(voice) / rms(bed) * 10 ** (-12 / 20)  # bed 12 dB under the voice...
    duck = 1 - 0.6 * speech  # ...and about 8 dB lower again while he speaks
    fx_gain = rms(voice) / max(rms(fx), 1e-9) * 10 ** (-12 / 20)
    mono_music = bed * music_gain * duck
    # a little width: the bed is spread slightly, the voice and effects stay centred
    delay = int(0.011 * SR)
    left = voice + fx * fx_gain + mono_music
    right = voice + fx * fx_gain + np.concatenate([np.zeros(delay), mono_music[:-delay]])
    stereo = np.stack([left, right], axis=1)
    stereo /= max(1.0, float(np.max(np.abs(stereo))) / 0.95)
    write_wav(BUILD / "premix.wav", stereo)
    print(loudnorm(BUILD / "premix.wav", BUILD / "mix.wav"))


if __name__ == "__main__":
    main()
