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
        "sentence_count": len(data.get("sentences", [])),
        "version": data.get("version", 1),
        "audio_path": data.get("audio_path"),
    }
    if not paper["id"]:
        return False

    paper_id = paper["id"]
    conn = db.get_conn()
    try:
        # 1. Upsert paper row (metadata always updated from JSON truth)
        conn.execute(
            """
            INSERT INTO papers (id, title, year, month, set_number, category, total_duration_sec, sentence_count, version, audio_path)
            VALUES (:id, :title, :year, :month, :set_number, :category, :total_duration_sec, :sentence_count, :version, :audio_path)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                year=excluded.year,
                month=excluded.month,
                set_number=excluded.set_number,
                category=excluded.category,
                total_duration_sec=excluded.total_duration_sec,
                sentence_count=excluded.sentence_count,
                version=excluded.version,
                audio_path=excluded.audio_path
            """,
            paper,
        )

        # 2. Upsert sections first so new section IDs exist for sentences
        sections = data.get("sections", [])
        new_sec_ids = []
        for sec in sections:
            sec_id = sec.get("id", f"{paper_id}_sec_{sec.get('sort_order', 0)}")
            new_sec_ids.append(sec_id)
            conn.execute(
                """
                INSERT INTO sections (id, paper_id, title, section_type, sort_order)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    section_type=excluded.section_type,
                    sort_order=excluded.sort_order
                """,
                (sec_id, paper_id, sec.get("title", ""), sec.get("section_type", ""), sec.get("sort_order", 0)),
            )

        # 3. Upsert sentences (updating fields while preserving user bookmark/accuracy/status)
        sentences = data.get("sentences", [])
        new_sent_ids = []
        for sent in sentences:
            sent_id = sent.get("id", f"{paper_id}_s_{sent.get('idx', 0)}")
            new_sent_ids.append(sent_id)

        # Invert existing idx temporarily to avoid unique(paper_id, idx) conflict during reordering
        conn.execute("UPDATE sentences SET idx = -idx WHERE paper_id = ?", (paper_id,))

        for sent in sentences:
            sent_id = sent.get("id", f"{paper_id}_s_{sent.get('idx', 0)}")
            kv = json.dumps(sent.get("key_vocab", []), ensure_ascii=False) if isinstance(sent.get("key_vocab"), list) else sent.get("key_vocab")
            conn.execute(
                """
                INSERT INTO sentences (id, paper_id, section_id, idx, english, chinese, start_time, end_time, audio_path, key_vocab, status, is_bookmarked, dictation_accuracy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    section_id=excluded.section_id,
                    idx=excluded.idx,
                    english=excluded.english,
                    chinese=excluded.chinese,
                    start_time=excluded.start_time,
                    end_time=excluded.end_time,
                    audio_path=excluded.audio_path,
                    key_vocab=excluded.key_vocab
                """,
                (
                    sent_id, paper_id, sent.get("section_id"), sent.get("idx", 0),
                    sent.get("english", ""), sent.get("chinese", ""),
                    sent.get("start_time", 0), sent.get("end_time", 0),
                    sent.get("audio_path"), kv,
                    sent.get("status", "unread"),
                    1 if sent.get("is_bookmarked") else 0,
                    sent.get("dictation_accuracy"),
                ),
            )

        # 4. Clean up obsolete sections and sentences that no longer exist in new data
        if new_sec_ids:
            placeholders_sec = ",".join("?" for _ in new_sec_ids)
            conn.execute(f"DELETE FROM sections WHERE paper_id = ? AND id NOT IN ({placeholders_sec})", [paper_id] + new_sec_ids)
        else:
            conn.execute("DELETE FROM sections WHERE paper_id = ?", (paper_id,))

        if new_sent_ids:
            placeholders_sent = ",".join("?" for _ in new_sent_ids)
            conn.execute(f"DELETE FROM sentences WHERE paper_id = ? AND id NOT IN ({placeholders_sent})", [paper_id] + new_sent_ids)
        else:
            conn.execute("DELETE FROM sentences WHERE paper_id = ?", (paper_id,))

        # 5. Recreate questions for this paper
        conn.execute("DELETE FROM questions WHERE paper_id = ?", (paper_id,))
        for q in data.get("questions", []):
            opts = json.dumps(q.get("options", []), ensure_ascii=False) if isinstance(q.get("options"), list) else q.get("options")
            conn.execute(
                """
                INSERT INTO questions (id, paper_id, section_id, sentence_id, idx, question_text, options, answer, explanation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    q.get("id", f"{paper_id}_q_{q.get('idx', 0)}"),
                    paper_id,
                    q.get("section_id"),
                    q.get("sentence_id"),
                    q.get("idx", 0),
                    q.get("question_text", ""),
                    opts,
                    q.get("answer", ""),
                    q.get("explanation", ""),
                ),
            )

        conn.commit()
        return True
    finally:
        conn.close()


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