"""SQLite database layer for ListeningLab."""
import sqlite3
import json
import os
from typing import Optional, List, Dict, Any

DB_PATH = os.environ.get("LISTENINGLAB_DB", "data/listeninglab.db")
SCHEMA_VERSION = 1


def get_db_path() -> str:
    return os.environ.get("LISTENINGLAB_DB", DB_PATH)


def get_conn() -> sqlite3.Connection:
    db_path = get_db_path()
    dirname = os.path.dirname(db_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (id, version) VALUES (1, ?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    year INTEGER,
    month INTEGER,
    set_number INTEGER,
    category TEXT DEFAULT 'cet6-real',
    total_duration_sec INTEGER DEFAULT 0,
    sentence_count INTEGER DEFAULT 0,
    completed_sentences INTEGER DEFAULT 0,
    average_accuracy REAL DEFAULT 0,
    version INTEGER DEFAULT 1,
    audio_path TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sections (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    section_type TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sentences (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    section_id TEXT REFERENCES sections(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    english TEXT NOT NULL,
    chinese TEXT,
    start_time REAL DEFAULT 0,
    end_time REAL DEFAULT 0,
    audio_path TEXT,
    key_vocab TEXT,
    status TEXT DEFAULT 'unread',
    is_bookmarked INTEGER DEFAULT 0,
    dictation_accuracy REAL,
    UNIQUE(paper_id, idx)
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    section_id TEXT REFERENCES sections(id) ON DELETE CASCADE,
    sentence_id TEXT REFERENCES sentences(id) ON DELETE SET NULL,
    idx INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    options TEXT,
    answer TEXT,
    explanation TEXT
);

CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    current_sentence_idx INTEGER DEFAULT 0,
    playback_rate REAL DEFAULT 1.0,
    loop_mode TEXT DEFAULT 'sentence',
    loop_count_target INTEGER DEFAULT 2,
    transcript_visibility TEXT DEFAULT 'visible',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(paper_id)
);

CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sentence_id TEXT NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sentence_id)
);

CREATE TABLE IF NOT EXISTS dictation_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sentence_id TEXT NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL,
    user_input TEXT NOT NULL,
    accuracy REAL NOT NULL,
    diff_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    default_playback_rate REAL DEFAULT 1.0,
    default_loop_count INTEGER DEFAULT 2,
    default_transcript_visibility TEXT DEFAULT 'visible',
    auto_play_next INTEGER DEFAULT 0,
    case_sensitive_dictation INTEGER DEFAULT 0,
    ignore_punctuation INTEGER DEFAULT 1,
    theme TEXT DEFAULT 'light'
);
"""


def upsert_paper(paper: Dict[str, Any]) -> bool:
    conn = get_conn()
    try:
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
        conn.commit()
        return True
    finally:
        conn.close()


def insert_section(section: Dict[str, Any]):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO sections (id, paper_id, title, section_type, sort_order) VALUES (:id, :paper_id, :title, :section_type, :sort_order)",
            section,
        )
        conn.commit()
    finally:
        conn.close()


def insert_sentence(sentence: Dict[str, Any]):
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO sentences
            (id, paper_id, section_id, idx, english, chinese, start_time, end_time, audio_path, key_vocab, status, is_bookmarked, dictation_accuracy)
            VALUES (:id, :paper_id, :section_id, :idx, :english, :chinese, :start_time, :end_time, :audio_path, :key_vocab, :status, :is_bookmarked, :dictation_accuracy)
            """,
            sentence,
        )
        conn.commit()
    finally:
        conn.close()


def insert_question(question: Dict[str, Any]):
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO questions
            (id, paper_id, section_id, sentence_id, idx, question_text, options, answer, explanation)
            VALUES (:id, :paper_id, :section_id, :sentence_id, :idx, :question_text, :options, :answer, :explanation)
            """,
            question,
        )
        conn.commit()
    finally:
        conn.close()


def get_papers() -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM papers ORDER BY year DESC, month DESC, set_number DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_paper(paper_id: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if not row:
            return None
        paper = dict(row)
        paper["sections"] = [dict(r) for r in conn.execute("SELECT * FROM sections WHERE paper_id = ? ORDER BY sort_order", (paper_id,)).fetchall()]
        paper["sentences"] = [dict(r) for r in conn.execute("SELECT * FROM sentences WHERE paper_id = ? ORDER BY idx", (paper_id,)).fetchall()]
        paper["questions"] = [dict(r) for r in conn.execute("SELECT * FROM questions WHERE paper_id = ? ORDER BY idx", (paper_id,)).fetchall()]
        return paper
    finally:
        conn.close()


def save_progress(paper_id: str, data: Dict[str, Any]):
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO progress (paper_id, current_sentence_idx, playback_rate, loop_mode, loop_count_target, transcript_visibility)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO UPDATE SET
                current_sentence_idx=excluded.current_sentence_idx,
                playback_rate=excluded.playback_rate,
                loop_mode=excluded.loop_mode,
                loop_count_target=excluded.loop_count_target,
                transcript_visibility=excluded.transcript_visibility,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                paper_id,
                data.get("current_sentence_idx", 0),
                data.get("playback_rate", 1.0),
                data.get("loop_mode", "sentence"),
                data.get("loop_count_target", 2),
                data.get("transcript_visibility", "visible"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_progress(paper_id: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM progress WHERE paper_id = ?", (paper_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_progress() -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM progress").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def toggle_bookmark(sentence_id: str, paper_id: str, note: str = "") -> Dict[str, Any]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT id FROM bookmarks WHERE sentence_id = ?", (sentence_id,)).fetchone()
        if row:
            conn.execute("DELETE FROM bookmarks WHERE sentence_id = ?", (sentence_id,))
            conn.execute("UPDATE sentences SET is_bookmarked = 0 WHERE id = ?", (sentence_id,))
            conn.commit()
            return {"bookmarked": False}
        else:
            conn.execute(
                "INSERT INTO bookmarks (sentence_id, paper_id, note) VALUES (?, ?, ?)",
                (sentence_id, paper_id, note),
            )
            conn.execute("UPDATE sentences SET is_bookmarked = 1 WHERE id = ?", (sentence_id,))
            conn.commit()
            return {"bookmarked": True}
    finally:
        conn.close()


def get_bookmarks() -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT b.*, s.english, s.chinese, s.start_time, s.end_time, s.idx, p.title as paper_title
            FROM bookmarks b
            JOIN sentences s ON b.sentence_id = s.id
            JOIN papers p ON b.paper_id = p.id
            ORDER BY b.created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_dictation(sentence_id: str, paper_id: str, user_input: str, accuracy: float, diff_json: str):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO dictation_attempts (sentence_id, paper_id, user_input, accuracy, diff_json) VALUES (?, ?, ?, ?, ?)",
            (sentence_id, paper_id, user_input, accuracy, diff_json),
        )
        conn.execute(
            "UPDATE sentences SET status = 'dictated', dictation_accuracy = ? WHERE id = ?",
            (accuracy, sentence_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_dictation_history(sentence_id: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM dictation_attempts WHERE sentence_id = ? ORDER BY created_at DESC",
            (sentence_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_settings() -> Dict[str, Any]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        if not row:
            conn.execute(
                "INSERT INTO settings (id) VALUES (1)"
            )
            conn.commit()
            row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        return dict(row)
    finally:
        conn.close()


def save_settings(data: Dict[str, Any]):
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO settings (id, default_playback_rate, default_loop_count, default_transcript_visibility,
                auto_play_next, case_sensitive_dictation, ignore_punctuation, theme)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                default_playback_rate=excluded.default_playback_rate,
                default_loop_count=excluded.default_loop_count,
                default_transcript_visibility=excluded.default_transcript_visibility,
                auto_play_next=excluded.auto_play_next,
                case_sensitive_dictation=excluded.case_sensitive_dictation,
                ignore_punctuation=excluded.ignore_punctuation,
                theme=excluded.theme
            """,
            (
                data.get("default_playback_rate", 1.0),
                data.get("default_loop_count", 2),
                data.get("default_transcript_visibility", "visible"),
                1 if data.get("auto_play_next", False) else 0,
                1 if data.get("case_sensitive_dictation", False) else 0,
                1 if data.get("ignore_punctuation", True) else 0,
                data.get("theme", "light"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_stats() -> Dict[str, Any]:
    conn = get_conn()
    try:
        total_sentences = conn.execute("SELECT COUNT(*) as c FROM sentences").fetchone()["c"]
        completed = conn.execute("SELECT COUNT(*) as c FROM sentences WHERE status = 'dictated'").fetchone()["c"]
        bookmarked = conn.execute("SELECT COUNT(*) as c FROM bookmarks").fetchone()["c"]
        avg_accuracy_row = conn.execute("SELECT AVG(dictation_accuracy) as a FROM sentences WHERE dictation_accuracy IS NOT NULL").fetchone()
        avg_accuracy = round(avg_accuracy_row["a"] or 0, 1)
        attempts = conn.execute("SELECT COUNT(*) as c FROM dictation_attempts").fetchone()["c"]
        return {
            "total_sentences": total_sentences,
            "completed_sentences": completed,
            "bookmarked_count": bookmarked,
            "average_accuracy": avg_accuracy,
            "total_attempts": attempts,
        }
    finally:
        conn.close()