#!/usr/bin/env python3
"""TTS synthesis pipeline for ListeningLab.

Input: content/papers/<paper-id>.json
Output:
  content/papers/<paper-id>/<sentence_id>.mp3
  content/papers/<paper-id>/sec_<section_sort_order>.mp3
  content/papers/<paper-id>/full.mp3

Updates JSON in-place with start_time/end_time/audio_path/total_duration_sec.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Configuration
VENV_DIR = os.environ.get("LISTENINGLAB_TTS_VENV", "/home/Yuhang/.local/share/listeninglab-tts/venv")
MODEL_DIR = os.environ.get("LISTENINGLAB_TTS_MODELS", "/home/Yuhang/.local/share/listeninglab-tts/models")
DEFAULT_MODEL = os.path.join(MODEL_DIR, "en_US-libritts_r-medium.onnx")
SILENCE_BETWEEN_SENTENCES = 0.35  # seconds
TARGET_SAMPLE_RATE = 22050
TARGET_CHANNELS = 1
TARGET_BITRATE = "32k"
TARGET_WPM = 150

PIPER_BIN = os.path.join(VENV_DIR, "bin", "piper")


def ensure_model():
    if not os.path.isfile(DEFAULT_MODEL):
        raise RuntimeError(f"Model not found: {DEFAULT_MODEL}")


def estimate_duration(text: str) -> float:
    """Estimate sentence duration based on word count and target WPM."""
    words = len(text.split())
    return (words / TARGET_WPM) * 60.0


def synthesize_sentence(text: str, output_wav: str, length_scale: float = 1.0) -> float:
    """Synthesize a single sentence to WAV. Returns estimated duration."""
    ensure_model()
    cmd = [
        PIPER_BIN,
        "-m", DEFAULT_MODEL,
        "-f", output_wav,
        "--length-scale", str(length_scale),
        "--sentence-silence", "0.0",
    ]
    proc = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"piper failed: {proc.stderr.decode()}")
    # Get actual duration via ffprobe
    dur = get_media_duration(output_wav)
    return dur


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
    """Convert WAV to target MP3 format."""
    cmd = [
        "ffmpeg", "-y", "-i", input_wav,
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", str(TARGET_CHANNELS),
        "-b:a", TARGET_BITRATE,
        output_mp3,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def create_silence(duration: float, output_wav: str):
    """Generate silence WAV."""
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


def process_paper(json_path: str):
    paper_dir = os.path.dirname(json_path)
    paper_id = Path(json_path).stem
    audio_dir = os.path.join(paper_dir, paper_id)
    os.makedirs(audio_dir, exist_ok=True)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sentences = data.get("sentences", [])
    if not sentences:
        print(f"[warn] No sentences in {json_path}")
        return

    # Determine length scale to hit target WPM on average
    total_words = sum(len(s["english"].split()) for s in sentences)
    # First pass: rough estimate with scale 1.0
    # We'll do a single pass with fixed scale based on heuristics.
    # Piper libritts_r at 1.0 is roughly 170 wpm; 1.15 gives ~150 wpm.
    length_scale = 1.15

    # Sort sentences by idx to preserve order
    sentences.sort(key=lambda s: s.get("idx", 0))

    current_time = 0.0
    sentence_files = []

    for sent in sentences:
        sent_id = sent["id"]
        text = sent["english"].strip()
        if not text:
            continue

        wav_path = os.path.join(audio_dir, f"{sent_id}.wav")
        mp3_path = os.path.join(audio_dir, f"{sent_id}.mp3")

        if not os.path.exists(mp3_path):
            dur = synthesize_sentence(text, wav_path, length_scale)
            wav_to_mp3(wav_path, mp3_path)
            os.remove(wav_path)
        else:
            dur = get_media_duration(mp3_path)

        sent["start_time"] = round(current_time, 3)
        sent["end_time"] = round(current_time + dur, 3)
        sent["audio_path"] = mp3_path.replace("content/papers/", "content/papers/")

        sentence_files.append(mp3_path)
        current_time += dur + SILENCE_BETWEEN_SENTENCES

    data["total_duration_sec"] = round(current_time, 3)
    data["sentence_count"] = len(sentences)

    # Generate per-section audio
    sections = data.get("sections", [])
    sections.sort(key=lambda s: s.get("sort_order", 0))
    sec_audio_paths = []
    for sec in sections:
        sec_id = sec["id"]
        sec_sentences = [s for s in sentences if s.get("section_id") == sec_id]
        sec_sentences.sort(key=lambda s: s.get("idx", 0))
        if not sec_sentences:
            continue
        sec_files = [os.path.join(audio_dir, f"{s['id']}.mp3") for s in sec_sentences]
        sec_mp3 = os.path.join(audio_dir, f"sec_{sec['sort_order']}.mp3")
        if not os.path.exists(sec_mp3):
            concat_audio_files(sec_files, sec_mp3)
        sec_audio_paths.append(sec_mp3)

    # Generate full paper audio
    full_mp3 = os.path.join(audio_dir, "full.mp3")
    if not os.path.exists(full_mp3):
        concat_audio_files(sentence_files, full_mp3)

    data["audio_path"] = full_mp3

    # Write updated JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total_size = sum(
        os.path.getsize(os.path.join(audio_dir, f))
        for f in os.listdir(audio_dir)
        if f.endswith(".mp3")
    )
    print(f"[done] {paper_id}: {len(sentences)} sentences, {data['total_duration_sec']:.1f}s, audio_size={total_size/1024/1024:.2f}MB")


def main():
    if len(sys.argv) > 1:
        paths = sys.argv[1:]
    else:
        paths = sorted(glob.glob("content/papers/*.json"))
    for p in paths:
        if not p.endswith(".json"):
            continue
        print(f"[processing] {p}")
        try:
            process_paper(p)
        except Exception as e:
            print(f"[error] {p}: {e}")
            raise


if __name__ == "__main__":
    import glob
    main()
