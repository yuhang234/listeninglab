#!/usr/bin/env python3
"""Validate ListeningLab paper JSONs and generate SOURCES.md."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PAPERS_DIR = "content/papers"
SOURCES_MD = "content/SOURCES.md"
MAX_AUDIO_MB = 12.0
MAX_DURATION_ERR = 0.3


def get_media_duration(path: str) -> float:
    if not os.path.isfile(path):
        return None
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def validate_paper(json_path: str) -> list:
    errors = []
    paper_id = Path(json_path).stem

    with open(json_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            return [f"Invalid JSON: {e}"]

    # Required top-level fields
    for field in ["id", "title", "year", "month", "sections", "sentences", "questions"]:
        if field not in data:
            errors.append(f"Missing top-level field: {field}")

    if data.get("id") != paper_id:
        errors.append(f"id mismatch: {data.get('id')} != {paper_id}")

    # Sections
    sections = data.get("sections", [])
    sec_ids = set()
    for sec in sections:
        sid = sec.get("id")
        if not sid:
            errors.append("Section missing id")
            continue
        if sid in sec_ids:
            errors.append(f"Duplicate section id: {sid}")
        sec_ids.add(sid)
        for f in ["paper_id", "title", "section_type", "sort_order"]:
            if f not in sec:
                errors.append(f"Section {sid} missing field {f}")
        if sec.get("paper_id") != paper_id:
            errors.append(f"Section {sid} paper_id mismatch")

    # Sentences
    sentences = data.get("sentences", [])
    sent_ids = set()
    sent_id_map = {}
    prev_end = -1
    for sent in sentences:
        sid = sent.get("id")
        if not sid:
            errors.append("Sentence missing id")
            continue
        if sid in sent_ids:
            errors.append(f"Duplicate sentence id: {sid}")
        sent_ids.add(sid)
        sent_id_map[sid] = sent
        for f in ["paper_id", "section_id", "idx", "english", "chinese", "start_time", "end_time", "key_vocab"]:
            if f not in sent:
                errors.append(f"Sentence {sid} missing field {f}")
        if sent.get("paper_id") != paper_id:
            errors.append(f"Sentence {sid} paper_id mismatch")
        if sent.get("section_id") not in sec_ids:
            errors.append(f"Sentence {sid} section_id {sent.get('section_id')} not found")

        st = sent.get("start_time", 0)
        et = sent.get("end_time", 0)
        if st < prev_end:
            errors.append(f"Sentence {sid} start_time {st} overlaps previous end {prev_end}")
        if et <= st:
            errors.append(f"Sentence {sid} end_time {et} <= start_time {st}")
        prev_end = et

        # Audio file check
        audio_path = sent.get("audio_path")
        if not audio_path:
            errors.append(f"Sentence {sid} missing audio_path")
        else:
            dur = get_media_duration(audio_path)
            if dur is None:
                errors.append(f"Sentence {sid} audio missing or unreadable: {audio_path}")
            else:
                expected_dur = et - st
                if abs(dur - expected_dur) > MAX_DURATION_ERR:
                    errors.append(f"Sentence {sid} duration mismatch: ffprobe={dur:.3f}s, json={expected_dur:.3f}s")

        # key_vocab
        kv = sent.get("key_vocab", [])
        if not isinstance(kv, list) or len(kv) == 0:
            errors.append(f"Sentence {sid} key_vocab empty or not a list")
        else:
            for item in kv:
                if not isinstance(item, dict) or "word" not in item or "definition" not in item:
                    errors.append(f"Sentence {sid} key_vocab item malformed: {item}")

        # Chinese
        if not sent.get("chinese", "").strip():
            errors.append(f"Sentence {sid} chinese empty")

    # Questions
    questions = data.get("questions", [])
    q_ids = set()
    for q in questions:
        qid = q.get("id")
        if not qid:
            errors.append("Question missing id")
            continue
        if qid in q_ids:
            errors.append(f"Duplicate question id: {qid}")
        q_ids.add(qid)
        for f in ["paper_id", "section_id", "idx", "question_text", "options", "answer", "explanation"]:
            if f not in q:
                errors.append(f"Question {qid} missing field {f}")
        if q.get("paper_id") != paper_id:
            errors.append(f"Question {qid} paper_id mismatch")
        if q.get("section_id") not in sec_ids:
            errors.append(f"Question {qid} section_id {q.get('section_id')} not found")
        ans = q.get("answer", "")
        if ans not in {"A", "B", "C", "D"}:
            errors.append(f"Question {qid} answer '{ans}' not in A-D")
        sid = q.get("sentence_id")
        if not sid:
            errors.append(f"Question {qid} missing sentence_id")
        elif sid not in sent_id_map:
            errors.append(f"Question {qid} sentence_id {sid} not found")
        # options parse check
        opts = q.get("options", [])
        if isinstance(opts, str):
            try:
                opts = json.loads(opts)
            except json.JSONDecodeError:
                errors.append(f"Question {qid} options not valid JSON string")
                opts = []
        if not isinstance(opts, list) or len(opts) != 4:
            errors.append(f"Question {qid} options must be array of 4 strings")

    # Section audio check
    for sec in sections:
        sec_audio = os.path.join(PAPERS_DIR, paper_id, f"sec_{sec.get('sort_order', 0)}.mp3")
        if not os.path.isfile(sec_audio):
            errors.append(f"Section {sec.get('id')} audio missing: sec_{sec.get('sort_order', 0)}.mp3")

    # Full audio check
    full_audio = data.get("audio_path")
    if not full_audio:
        errors.append(f"Full audio missing audio_path")
    else:
        dur = get_media_duration(full_audio)
        if dur is None:
            errors.append(f"Full audio missing or unreadable: {full_audio}")
        else:
            total_dur = data.get("total_duration_sec", 0)
            if abs(dur - total_dur) > MAX_DURATION_ERR * 2:
                errors.append(f"Full audio duration mismatch: ffprobe={dur:.3f}s, json={total_dur:.3f}s")

    # Size check
    audio_dir = os.path.join(PAPERS_DIR, paper_id)
    if os.path.isdir(audio_dir):
        total_size = sum(
            os.path.getsize(os.path.join(audio_dir, f))
            for f in os.listdir(audio_dir)
            if f.endswith(".mp3")
        )
        if total_size > MAX_AUDIO_MB * 1024 * 1024:
            errors.append(f"Total audio size {total_size/1024/1024:.2f}MB exceeds {MAX_AUDIO_MB}MB")

    return errors


def generate_sources_md(papers_dir: str) -> str:
    lines = [
        "# Content Sources",
        "",
        "六级听力真题内容来源与验证记录：",
        "",
        "| Paper ID | Title | Verified | Provenance |",
        "|---|---|---|---|",
    ]
    for filename in sorted(os.listdir(papers_dir)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(papers_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        pid = data.get("id", "")
        title = data.get("title", "")
        verified = "Yes" if data.get("verified", False) else "No"
        prov = data.get("provenance", "")
        lines.append(f"| {pid} | {title} | {verified} | {prov} |")
    lines.append("")
    lines.append("> 说明：标有 `model-reconstructed` 的套题内容凭模型记忆重建，可能有误差；标有 `verified: Yes` 的套题已按真实试卷核对。所有音频均为本地离线 TTS 按句合成，非考场原声。")
    return "\n".join(lines)


def main():
    all_ok = True
    paper_errors = {}
    for filename in sorted(os.listdir(PAPERS_DIR)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(PAPERS_DIR, filename)
        print(f"Validating {filename}...")
        errs = validate_paper(path)
        if errs:
            all_ok = False
            paper_errors[filename] = errs
            for e in errs:
                print(f"  ERROR: {e}")
        else:
            print(f"  OK")

    # Write SOURCES.md
    sources_md = generate_sources_md(PAPERS_DIR)
    with open(SOURCES_MD, "w", encoding="utf-8") as f:
        f.write(sources_md + "\n")
    print(f"\nGenerated {SOURCES_MD}")

    if not all_ok:
        print("\nValidation FAILED")
        sys.exit(1)
    else:
        print("\nValidation PASSED")


if __name__ == "__main__":
    main()
