"""Import seed data and user uploads."""
import json
import os
import re
import shutil
from typing import Dict, Any, List

from app import db

PAPERS_DIR = "content/papers"
IMPORTED_DIR = "content/imported"


def import_seed_papers():
    if not os.path.isdir(PAPERS_DIR):
        return
    for filename in sorted(os.listdir(PAPERS_DIR)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(PAPERS_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[import] skip {filename}: invalid JSON: {e}")
            continue
        import_paper_data(data)


def import_paper_data(data: Dict[str, Any]) -> bool:
    paper = {
        "id": data.get("id"),
        "title": data.get("title", ""),
        "year": data.get("year"),
        "month": data.get("month"),
        "set_number": data.get("set_number"),
        "category": data.get("category", "cet6-real"),
        "total_duration_sec": data.get("total_duration_sec", 0),
        "sentence_count": data.get("sentence_count", 0),
        "version": data.get("version", 1),
        "audio_path": data.get("audio_path"),
    }
    if not paper["id"]:
        return False
    updated = db.upsert_paper(paper)
    if not updated:
        return False

    # Delete old child records to allow re-import
    conn = db.get_conn()
    try:
        conn.execute("DELETE FROM sections WHERE paper_id = ?", (paper["id"],))
        conn.execute("DELETE FROM sentences WHERE paper_id = ?", (paper["id"],))
        conn.execute("DELETE FROM questions WHERE paper_id = ?", (paper["id"],))
        conn.commit()
    finally:
        conn.close()

    for sec in data.get("sections", []):
        db.insert_section({
            "id": sec.get("id", f"{paper['id']}_sec_{sec.get('sort_order', 0)}"),
            "paper_id": paper["id"],
            "title": sec.get("title", ""),
            "section_type": sec.get("section_type", ""),
            "sort_order": sec.get("sort_order", 0),
        })

    for sent in data.get("sentences", []):
        db.insert_sentence({
            "id": sent.get("id", f"{paper['id']}_s_{sent.get('idx', 0)}"),
            "paper_id": paper["id"],
            "section_id": sent.get("section_id"),
            "idx": sent.get("idx", 0),
            "english": sent.get("english", ""),
            "chinese": sent.get("chinese", ""),
            "start_time": sent.get("start_time", 0),
            "end_time": sent.get("end_time", 0),
            "audio_path": sent.get("audio_path"),
            "key_vocab": json.dumps(sent.get("key_vocab", []), ensure_ascii=False) if isinstance(sent.get("key_vocab"), list) else sent.get("key_vocab"),
            "status": sent.get("status", "unread"),
            "is_bookmarked": 1 if sent.get("is_bookmarked") else 0,
            "dictation_accuracy": sent.get("dictation_accuracy"),
        })

    for q in data.get("questions", []):
        db.insert_question({
            "id": q.get("id", f"{paper['id']}_q_{q.get('idx', 0)}"),
            "paper_id": paper["id"],
            "section_id": q.get("section_id"),
            "sentence_id": q.get("sentence_id"),
            "idx": q.get("idx", 0),
            "question_text": q.get("question_text", ""),
            "options": json.dumps(q.get("options", []), ensure_ascii=False) if isinstance(q.get("options"), list) else q.get("options"),
            "answer": q.get("answer", ""),
            "explanation": q.get("explanation", ""),
        })
    return True


def parse_subtitle(text: str, fmt: str) -> List[Dict[str, Any]]:
    fmt = fmt.lower()
    sentences = []
    if fmt == "srt":
        blocks = re.split(r"\n\s*\n", text.strip())
        idx = 0
        for block in blocks:
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if len(lines) < 3:
                continue
            time_line = lines[1]
            m = re.match(r"(.+?)\s*-->\s*(.+)", time_line)
            if not m:
                continue
            start = _parse_time(m.group(1).strip())
            end = _parse_time(m.group(2).strip())
            content = " ".join(lines[2:])
            idx += 1
            sentences.append({"idx": idx, "english": content, "start_time": start, "end_time": end})
    elif fmt == "lrc":
        pattern = re.compile(r"\[(\d{2}):(.+?)\](.*)")
        entries = []
        for line in text.splitlines():
            m = pattern.match(line.strip())
            if m:
                mm = int(m.group(1))
                ss = float(m.group(2))
                entries.append({"time": mm * 60 + ss, "text": m.group(3).strip()})
        entries.sort(key=lambda x: x["time"])
        for i, e in enumerate(entries):
            end_time = entries[i + 1]["time"] if i + 1 < len(entries) else e["time"] + 5
            sentences.append({"idx": i + 1, "english": e["text"], "start_time": e["time"], "end_time": end_time})
    elif fmt == "txt":
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            sentences.append({"idx": i + 1, "english": line, "start_time": 0, "end_time": 0})
    return sentences


def _parse_time(t: str) -> float:
    t = t.replace(",", ".")
    parts = t.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def handle_import(paper_id: str, audio_file_path: str, subtitle_text: str, subtitle_format: str) -> Dict[str, Any]:
    os.makedirs(IMPORTED_DIR, exist_ok=True)
    paper_dir = os.path.join(IMPORTED_DIR, paper_id)
    os.makedirs(paper_dir, exist_ok=True)

    dest_audio = os.path.join(paper_dir, "audio.mp3")
    if os.path.exists(audio_file_path):
        shutil.copy2(audio_file_path, dest_audio)

    sentences = []
    if subtitle_text.strip():
        sentences = parse_subtitle(subtitle_text, subtitle_format)
        for s in sentences:
            s["id"] = f"{paper_id}_s_{s['idx']}"
            s["paper_id"] = paper_id
            s["section_id"] = None
            s["chinese"] = ""
            s["audio_path"] = None
            s["key_vocab"] = "[]"
            s["status"] = "unread"
            s["is_bookmarked"] = 0
            s["dictation_accuracy"] = None
    else:
        sentences = [{
            "id": f"{paper_id}_s_1",
            "paper_id": paper_id,
            "section_id": None,
            "idx": 1,
            "english": "Imported audio",
            "chinese": "",
            "start_time": 0,
            "end_time": 0,
            "audio_path": None,
            "key_vocab": "[]",
            "status": "unread",
            "is_bookmarked": 0,
            "dictation_accuracy": None,
        }]

    paper = {
        "id": paper_id,
        "title": f"Imported: {paper_id}",
        "year": 0,
        "month": 0,
        "set_number": 0,
        "category": "custom-import",
        "total_duration_sec": 0,
        "sentence_count": len(sentences),
        "version": 1,
        "audio_path": dest_audio,
    }

    db.upsert_paper(paper)
    conn = db.get_conn()
    try:
        conn.execute("DELETE FROM sentences WHERE paper_id = ?", (paper_id,))
        conn.execute("DELETE FROM sections WHERE paper_id = ?", (paper_id,))
        conn.execute("DELETE FROM questions WHERE paper_id = ?", (paper_id,))
        conn.commit()
    finally:
        conn.close()

    for s in sentences:
        db.insert_sentence(s)

    return {"paper_id": paper_id, "sentences_imported": len(sentences), "audio_path": dest_audio}