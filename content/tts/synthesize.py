#!/usr/bin/env python3
"""TTS synthesis pipeline for ListeningLab.

Input: content/papers/<paper-id>.json
Output:
  content/papers/<paper-id>/<sentence_id>.mp3
  content/papers/<paper-id>/sec_<section_sort_order>.mp3
  content/papers/<paper-id>/full.mp3

Updates JSON in-place with start_time/end_time/audio_path/total_duration_sec.

Usage:
  # Synthesize all papers:
  python3 content/tts/synthesize.py

  # Synthesize a specific paper:
  python3 content/tts/synthesize.py content/papers/cet6-2024-06-1.json

  # Force regeneration even if MP3s exist:
  python3 content/tts/synthesize.py --force [<paper.json> ...]

Run from repository root.
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VENV_DIR = os.environ.get("LISTENINGLAB_TTS_VENV", "/home/Yuhang/.local/share/listeninglab-tts/venv")
MODEL_DIR = os.environ.get("LISTENINGLAB_TTS_MODELS", "/home/Yuhang/.local/share/listeninglab-tts/models")
DEFAULT_MODEL = os.path.join(MODEL_DIR, "en_US-libritts_r-medium.onnx")
SILENCE_BETWEEN_SENTENCES = 0.35   # seconds gap between sentences
TARGET_SAMPLE_RATE = 22050
TARGET_CHANNELS = 1
TARGET_BITRATE = "32k"
# Piper libritts_r at length_scale 1.15 ≈ 148–155 wpm (target 140–160)
LENGTH_SCALE = 1.15

PIPER_BIN = os.path.join(VENV_DIR, "bin", "piper")

# Repo root: directory containing this file's grandparent (content/tts/ → content/ → root)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAPERS_DIR = os.path.join(REPO_ROOT, "content", "papers")


# ---------------------------------------------------------------------------
# TTS back-ends: piper → espeak-ng (if installed) → blocked
# ---------------------------------------------------------------------------

def _check_piper() -> bool:
    return os.path.isfile(PIPER_BIN) and os.path.isfile(DEFAULT_MODEL)


def _check_espeak() -> bool:
    import shutil
    return shutil.which("espeak-ng") is not None


def synthesize_sentence(text: str, output_wav: str) -> float:
    """Synthesize a single sentence to WAV using best available TTS.

    Returns actual duration (seconds) measured by ffprobe.
    Raises RuntimeError if no TTS backend is available.
    """
    if _check_piper():
        return _synth_piper(text, output_wav)
    elif _check_espeak():
        print("[warn] piper not available, falling back to espeak-ng")
        return _synth_espeak(text, output_wav)
    else:
        raise RuntimeError(
            "blocked: no offline TTS backend available. "
            "Install piper via ~/.local/share/listeninglab-tts/venv or install espeak-ng."
        )


def _synth_piper(text: str, output_wav: str) -> float:
    cmd = [
        PIPER_BIN,
        "-m", DEFAULT_MODEL,
        "-f", output_wav,
        "--length-scale", str(LENGTH_SCALE),
        "--sentence-silence", "0.0",
    ]
    proc = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"piper failed: {proc.stderr.decode()}")
    return get_media_duration(output_wav)


def _synth_espeak(text: str, output_wav: str) -> float:
    cmd = [
        "espeak-ng",
        "-s", "150",        # ~150 wpm
        "-a", "100",
        "--ipa=0",
        "-w", output_wav,
        text,
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"espeak-ng failed: {proc.stderr.decode()}")
    return get_media_duration(output_wav)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def get_media_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def wav_to_mp3(input_wav: str, output_mp3: str):
    """Convert WAV to target MP3 format (22050 Hz, mono, 32kbps)."""
    cmd = [
        "ffmpeg", "-y", "-i", input_wav,
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", str(TARGET_CHANNELS),
        "-b:a", TARGET_BITRATE,
        output_mp3,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def create_silence_wav(duration: float, output_wav: str):
    """Generate a silence WAV of given duration."""
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"anullsrc=r={TARGET_SAMPLE_RATE}:cl=mono",
        "-t", str(duration),
        "-acodec", "pcm_s16le",
        output_wav,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def concat_audio_files(files: list, output_mp3: str):
    """Concatenate multiple audio files into one MP3."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for filepath in files:
            f.write(f"file '{os.path.abspath(filepath)}'\n")
        list_path = f.name
    try:
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-ar", str(TARGET_SAMPLE_RATE),
            "-ac", str(TARGET_CHANNELS),
            "-b:a", TARGET_BITRATE,
            output_mp3,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
    finally:
        os.unlink(list_path)


def _rel(abs_path: str) -> str:
    """Return a path relative to REPO_ROOT (for storage in JSON)."""
    try:
        return os.path.relpath(abs_path, REPO_ROOT)
    except ValueError:
        return abs_path


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process_paper(json_path: str, force: bool = False):
    """Synthesize audio for one paper JSON and update it in place."""
    json_path = os.path.abspath(json_path)
    paper_id = Path(json_path).stem
    # Audio output dir lives alongside the JSON: content/papers/<paper_id>/
    audio_dir = os.path.join(os.path.dirname(json_path), paper_id)
    os.makedirs(audio_dir, exist_ok=True)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sentences = data.get("sentences", [])
    if not sentences:
        print(f"[warn] No sentences in {json_path}")
        return

    # Sort sentences by idx to preserve order
    sentences.sort(key=lambda s: s.get("idx", 0))

    current_time = 0.0
    sentence_mp3s = []       # individual sentence MP3s in order

    with tempfile.TemporaryDirectory() as tmpdir:
        for sent in sentences:
            sent_id = sent["id"]
            text = sent.get("english", "").strip()
            if not text:
                continue

            mp3_path = os.path.join(audio_dir, f"{sent_id}.mp3")

            if force or not os.path.exists(mp3_path):
                wav_path = os.path.join(tmpdir, f"{sent_id}.wav")
                synthesize_sentence(text, wav_path)
                wav_to_mp3(wav_path, mp3_path)
                # wav cleaned up when tmpdir exits

            dur = get_media_duration(mp3_path)

            sent["start_time"] = round(current_time, 3)
            sent["end_time"] = round(current_time + dur, 3)
            sent["audio_path"] = _rel(mp3_path)

            sentence_mp3s.append(mp3_path)
            current_time += dur + SILENCE_BETWEEN_SENTENCES

    data["total_duration_sec"] = round(current_time - SILENCE_BETWEEN_SENTENCES, 3)
    data["sentence_count"] = len(sentence_mp3s)

    # Per-section audio
    sections = data.get("sections", [])
    sections.sort(key=lambda s: s.get("sort_order", 0))
    for sec in sections:
        sec_id = sec["id"]
        sec_sents = [s for s in sentences if s.get("section_id") == sec_id]
        sec_sents.sort(key=lambda s: s.get("idx", 0))
        if not sec_sents:
            continue
        sec_files = [os.path.join(audio_dir, f"{s['id']}.mp3") for s in sec_sents]
        sec_mp3 = os.path.join(audio_dir, f"sec_{sec['sort_order']}.mp3")
        if force or not os.path.exists(sec_mp3):
            concat_audio_files(sec_files, sec_mp3)

    # Full paper audio
    full_mp3 = os.path.join(audio_dir, "full.mp3")
    if force or not os.path.exists(full_mp3):
        concat_audio_files(sentence_mp3s, full_mp3)

    data["audio_path"] = _rel(full_mp3)

    # Write updated JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total_size = sum(
        os.path.getsize(os.path.join(audio_dir, fn))
        for fn in os.listdir(audio_dir)
        if fn.endswith(".mp3")
    )
    print(
        f"[done] {paper_id}: {len(sentence_mp3s)} sentences, "
        f"{data['total_duration_sec']:.1f}s, "
        f"audio_size={total_size / 1024 / 1024:.2f}MB"
    )


def main():
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args:
        paths = args
    else:
        paths = sorted(glob.glob(os.path.join(PAPERS_DIR, "*.json")))

    if not paths:
        print(f"No paper JSONs found in {PAPERS_DIR}")
        sys.exit(1)

    errors = []
    for p in paths:
        if not p.endswith(".json"):
            continue
        print(f"[processing] {p}")
        try:
            process_paper(p, force=force)
        except Exception as e:
            print(f"[error] {p}: {e}")
            errors.append((p, e))

    if errors:
        print(f"\n{len(errors)} paper(s) failed synthesis.")
        sys.exit(1)


if __name__ == "__main__":
    main()
