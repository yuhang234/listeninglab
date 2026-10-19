"""Test progress save/restore persistence, multiple papers, and update overwrites."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db


class TestProgressPersistence(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.environ["LISTENINGLAB_DB"] = self.db_path
        db.init_db()

        # Insert dummy paper records for testing progress
        db.upsert_paper({
            "id": "paper-alpha",
            "title": "Alpha Paper",
            "year": 2024,
            "month": 6,
            "set_number": 1,
            "category": "cet6-real",
            "total_duration_sec": 300,
            "sentence_count": 20,
            "version": 1,
            "audio_path": "audio-a.mp3",
        })
        db.upsert_paper({
            "id": "paper-beta",
            "title": "Beta Paper",
            "year": 2023,
            "month": 12,
            "set_number": 1,
            "category": "cet6-real",
            "total_duration_sec": 400,
            "sentence_count": 30,
            "version": 1,
            "audio_path": "audio-b.mp3",
        })

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_save_and_retrieve_progress(self):
        db.save_progress("paper-alpha", {
            "current_sentence_idx": 5,
            "playback_rate": 1.5,
            "loop_mode": "sentence",
            "loop_count_target": 3,
            "transcript_visibility": "blur",
        })

        prog = db.get_progress("paper-alpha")
        self.assertIsNotNone(prog)
        self.assertEqual(prog["paper_id"], "paper-alpha")
        self.assertEqual(prog["current_sentence_idx"], 5)
        self.assertEqual(prog["playback_rate"], 1.5)
        self.assertEqual(prog["loop_mode"], "sentence")
        self.assertEqual(prog["loop_count_target"], 3)
        self.assertEqual(prog["transcript_visibility"], "blur")

    def test_progress_update_overwrites_existing(self):
        db.save_progress("paper-alpha", {
            "current_sentence_idx": 2,
            "playback_rate": 1.0,
            "loop_mode": "sentence",
            "loop_count_target": 2,
            "transcript_visibility": "visible",
        })
        # Advance further
        db.save_progress("paper-alpha", {
            "current_sentence_idx": 8,
            "playback_rate": 1.25,
            "loop_mode": "infinite",
            "loop_count_target": 999,
            "transcript_visibility": "hidden",
        })

        prog = db.get_progress("paper-alpha")
        self.assertEqual(prog["current_sentence_idx"], 8)
        self.assertEqual(prog["playback_rate"], 1.25)
        self.assertEqual(prog["loop_mode"], "infinite")
        self.assertEqual(prog["loop_count_target"], 999)
        self.assertEqual(prog["transcript_visibility"], "hidden")

    def test_independent_progress_across_different_papers(self):
        db.save_progress("paper-alpha", {
            "current_sentence_idx": 10,
            "playback_rate": 1.75,
            "loop_mode": "sentence",
            "loop_count_target": 5,
            "transcript_visibility": "hidden",
        })
        db.save_progress("paper-beta", {
            "current_sentence_idx": 3,
            "playback_rate": 0.75,
            "loop_mode": "infinite",
            "loop_count_target": 999,
            "transcript_visibility": "blur",
        })

        alpha_prog = db.get_progress("paper-alpha")
        beta_prog = db.get_progress("paper-beta")

        self.assertEqual(alpha_prog["current_sentence_idx"], 10)
        self.assertEqual(alpha_prog["playback_rate"], 1.75)
        self.assertEqual(beta_prog["current_sentence_idx"], 3)
        self.assertEqual(beta_prog["playback_rate"], 0.75)

    def test_get_progress_nonexistent_returns_none(self):
        self.assertIsNone(db.get_progress("non-existent-paper"))

    def test_get_all_progress(self):
        db.save_progress("paper-alpha", {"current_sentence_idx": 1})
        db.save_progress("paper-beta", {"current_sentence_idx": 2})
        all_progs = db.get_all_progress()
        self.assertEqual(len(all_progs), 2)
        paper_ids = [p["paper_id"] for p in all_progs]
        self.assertIn("paper-alpha", paper_ids)
        self.assertIn("paper-beta", paper_ids)


if __name__ == "__main__":
    unittest.main()
