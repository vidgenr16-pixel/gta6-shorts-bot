"""Turns a gameplay recording into finished 9:16 shorts.

1. find the most action-packed moments (loudness spikes: gunfire, crashes, shouting)
2. transcribe speech with Whisper to get word timings
3. write a hook + caption (copywriter.py)
4. render: blurred background, zoomed gameplay, hook text on top,
   word-by-word captions, optional music, loudness normalised
"""
import json
import logging
import os
import random
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import config
import copywriter

log = logging.getLogger(__name__)
FFMPEG = os.getenv("FFMPEG", "ffmpeg")
FFPROBE = os.getenv("FFPROBE", "ffprobe")
W, H = 1080, 1920


@dataclass
class Info:
    duration: float
    width: int
    height: int
    has_audio: bool


def probe(path: Path) -> Info:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise ValueError("no video stream in file")
    return Info(
        duration=float(data["format"]["duration"]),
        width=int(video["width"]),
        height=int(video["height"]),
        has_audio=any(s["codec_type"] == "audio" for s in data["streams"]),
    )


# ---------- 1. pick the best moments ----------

def _loudness(path: Path, hop: float = 0.5) -> np.ndarray:
    raw = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    n = int(8000 * hop)
    k = len(a) // n
    if k == 0:
        return np.zeros(1)
    rms = np.sqrt((a[: k * n].reshape(k, n) ** 2).mean(axis=1) + 1e-10)
    return 20 * np.log10(rms)


def pick_segments(path: Path, info: Info, clip_len: float, count: int) -> list[float]:
    """Return start times of the `count` most intense, non-overlapping windows."""
    if info.duration <= clip_len + 1:
        return [0.0]
    last_start = info.duration - clip_len
    if not info.has_audio:
        return [last_start * (i + 1) / (count + 1) for i in range(count)]

    hop = 0.5
    db = _loudness(path, hop)
    norm = (db - db.mean()) / (db.std() + 1e-6)
    jumps = np.abs(np.diff(norm, prepend=norm[0]))  # sudden changes = explosions, crashes, gunfire
    per_frame = norm + 0.8 * jumps
    win = int(clip_len / hop)
    csum = np.concatenate([[0], np.cumsum(per_frame)])
    scores = (csum[win:] - csum[:-win]) / win  # score of window starting at each frame

    max_i = min(len(scores) - 1, int(last_start / hop))
    order = np.argsort(scores[: max_i + 1])[::-1]
    picked: list[int] = []
    for i in order:
        if all(abs(i - p) >= win for p in picked):
            picked.append(int(i))
        if len(picked) == count:
            break
    return sorted(p * hop for p in picked)


# ---------- 2. transcribe ----------

_whisper = None


def transcribe(path: Path, start: float, length: float, work: Path) -> list[dict]:
    """Word-level timestamps (relative to the clip start). Empty list if no speech."""
    global _whisper
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # e.g. Windows path too long for ctranslate2's DLL
        log.warning("Whisper unavailable, making the short without spoken captions: %s", e)
        return []
    # decode with ffmpeg ourselves (16 kHz mono float) instead of faster-whisper's PyAV loader
    raw = subprocess.run(
        [FFMPEG, "-v", "error", "-ss", f"{start:.2f}", "-t", f"{length:.2f}", "-i", str(path),
         "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    if _whisper is None:
        log.info("loading Whisper model %s (first run downloads it)", config.WHISPER_MODEL)
        _whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _ = _whisper.transcribe(audio, word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        if seg.no_speech_prob > 0.6:
            continue
        for w in seg.words or []:
            text = w.word.strip()
            if text and w.probability >= 0.35:
                words.append({"start": round(w.start, 2), "end": round(w.end, 2), "text": text})
    return words


# ---------- 3. subtitles (ASS) ----------

def _t(sec: float) -> str:
    sec = max(sec, 0)
    return f"{int(sec // 3600)}:{int(sec % 3600 // 60):02d}:{sec % 60:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(hook: str, words: list[dict], length: float) -> str:
    f = config.CAPTION_FONT
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Hook,{f},86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,4,8,70,70,250,1",
        f"Style: Cap,{f},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,500,1",
        f"Style: Tag,{f},40,&H50FFFFFF,&H00FFFFFF,&H64000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,2,40,40,140,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if hook:
        pop = r"{\fad(120,0)\fscx70\fscy70\t(0,160,\fscx108\fscy108)\t(160,280,\fscx100\fscy100)}"
        lines.append(f"Dialogue: 1,{_t(0)},{_t(length)},Hook,,0,0,0,,{pop}{_esc(hook.upper())}")
    if config.CHANNEL_HANDLE:
        lines.append(f"Dialogue: 0,{_t(0)},{_t(length)},Tag,,0,0,0,,{_esc(config.CHANNEL_HANDLE)}")

    # group words into 1-3 word chunks; highlight the word being spoken
    chunks: list[list[dict]] = []
    for w in words:
        if chunks and len(chunks[-1]) < 3 and w["start"] - chunks[-1][-1]["end"] < 0.5:
            chunks[-1].append(w)
        else:
            chunks.append([w])
    for chunk in chunks:
        for i, w in enumerate(chunk):
            start = w["start"]
            end = chunk[i + 1]["start"] if i + 1 < len(chunk) else min(w["end"] + 0.3, length)
            if end <= start:
                continue
            parts = []
            for j, other in enumerate(chunk):
                word = _esc(other["text"].upper())
                if j == i:
                    parts.append(r"{\c&H00E6FF&\fscx112\fscy112}" + word + r"{\r}")
                else:
                    parts.append(word)
            lines.append(f"Dialogue: 2,{_t(start)},{_t(end)},Cap,,0,0,0,,{' '.join(parts)}")
    return "\n".join(lines) + "\n"


# ---------- 4. render ----------

def _even(x: float) -> int:
    return int(x) // 2 * 2


def render(src: Path, info: Info, start: float, length: float, hook: str, words: list[dict], out: Path, work: Path):
    (work / "captions.ass").write_text(build_ass(hook, words, length), encoding="utf-8")
    # relative paths keep Windows drive letters ("C:") out of the filter string
    subs = "subtitles=captions.ass"
    if any(config.FONTS.glob("*.[ot]tf")):
        subs += ":fontsdir=" + os.path.relpath(config.FONTS, work).replace("\\", "/")

    if info.width / info.height > 0.8:  # landscape gameplay: blurred fill + zoomed centre
        video = (
            "[0:v]fps=30,split[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:3,"
            "eq=brightness=-0.08:saturation=1.2[bg];"
            f"[b]scale={_even(W * config.FG_ZOOM)}:-2,crop={W}:ih[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2-60,{subs}[v]"
        )
    else:  # already vertical
        video = f"[0:v]fps=30,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{subs}[v]"

    music = random.choice(list(config.MUSIC.glob("*.mp3")) + list(config.MUSIC.glob("*.m4a")) or [None])
    cmd = [FFMPEG, "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", f"{length:.2f}", "-i", str(src.resolve())]
    fade = f"afade=t=out:st={max(length - 0.6, 0):.2f}:d=0.6"
    audio = ""
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music.resolve())]
        m = f"[1:a]volume={config.MUSIC_VOLUME},afade=t=in:d=1[m]"
        if info.has_audio:
            audio = f";[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[g];{m};[g][m]amix=inputs=2:duration=first:normalize=0,{fade}[aout]"
        else:
            audio = f";{m};[m]{fade}[aout]"
    elif info.has_audio:
        audio = f";[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,{fade}[aout]"

    cmd += ["-filter_complex", video + audio, "-map", "[v]"]
    cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"] if audio else ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-maxrate", "8M", "-bufsize", "16M",
            "-pix_fmt", "yuv420p", "-t", f"{length:.2f}", "-movflags", "+faststart", str(out.resolve())]
    subprocess.run(cmd, check=True, cwd=work)


# ---------- glue ----------

def recent_hooks(n: int = 15) -> list[str]:
    metas = [json.loads(p.read_text(encoding="utf-8")) for d in (config.READY, config.POSTED)
             for p in d.glob("*/meta.json")]
    metas.sort(key=lambda m: m["created"], reverse=True)
    return [m["hook"] for m in metas[:n]]


def make_shorts(src: Path, note: str = "") -> list[dict]:
    """Cut `src` into one or more finished shorts in data/ready/<id>/. Returns their metadata."""
    info = probe(src)
    length = min(config.CLIP_SECONDS, info.duration)
    count = max(1, min(config.MAX_SHORTS_PER_VIDEO, int(info.duration // (config.CLIP_SECONDS * 3))))
    results = []
    for start in pick_segments(src, info, length, count):
        sid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        work = config.WORK / sid
        work.mkdir(parents=True)
        try:
            words = transcribe(src, start, length, work) if info.has_audio else []
            copy = copywriter.write_copy(" ".join(w["text"] for w in words), note, recent_hooks())
            out_dir = config.READY / sid
            out_dir.mkdir(parents=True)
            render(src, info, start, length, copy["hook"], words, out_dir / "short.mp4", work)
            meta = {
                "id": sid, "created": time.time(), "source": src.name, "start": start, "length": length,
                "hook": copy["hook"], "caption": copy["caption"], "hashtags": copy["hashtags"],
                "words": words, "note": note,
            }
            (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            results.append(meta)
            log.info("made short %s from %s @ %.1fs: %s", sid, src.name, start, copy["hook"])
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return results


def rerender(sid: str, hook: str) -> dict:
    """Re-render a queued short with a new hook text."""
    out_dir = config.READY / sid
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    src = config.SOURCES / meta["source"]
    work = config.WORK / (sid + "-re")
    work.mkdir(parents=True, exist_ok=True)
    try:
        render(src, probe(src), meta["start"], meta["length"], hook, meta["words"], out_dir / "short.mp4", work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    meta["hook"] = hook
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


if __name__ == "__main__":  # quick local test: python editor.py clip.mp4 "optional note"
    import sys

    logging.basicConfig(level=logging.INFO)
    p = Path(sys.argv[1])
    dest = config.SOURCES / p.name
    if p.resolve() != dest.resolve():
        shutil.copy2(p, dest)
    for m in make_shorts(dest, sys.argv[2] if len(sys.argv) > 2 else ""):
        print(json.dumps({k: v for k, v in m.items() if k != "words"}, indent=2))
