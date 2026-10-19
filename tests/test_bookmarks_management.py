"""Test bookmarks addition, deletion, and cross-paper management."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db


class TestBookmarksManagement(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.environ["LISTENINGLAB_DB"] = self.db_path
        db.init_db()

        # Seed two papers with sentences
        db.upsert_paper({
            "id": "paper-1",
            "title": "Paper One",
            "year": 2024,
            "month": 6,
            "set_number": 1,
            "category": "cet6-real",
            "total_duration_sec": 300,
            "sentence_count": 2,
            "version": 1,
            "audio_path": "audio-1.mp3",
        })
        db.insert_sentence({
            "id": "paper-1_s_1",
            "paper_id": "paper-1",
            "section_id": None,
            "idx": 1,
            "english": "Sentence 1 from paper 1",
            "chinese": "试卷1第1句",
            "start_time": 0.0,
            "end_time": 4.0,
            "audio_path": "audio-1_1.mp3",
            "key_vocab": "[]",
            "status": "unread",
            "is_bookmarked": 0,
            "dictation_accuracy": None,
        })
        db.insert_sentence({
            "id": "paper-1_s_2",
            "paper_id": "paper-1",
            "section_id": None,
            "idx": 2,
            "english": "Sentence 2 from paper 1",
            "chinese": "试卷1第2句",
            "start_time": 4.0,
            "end_time": 8.0,
            "audio_path": "audio-1_2.mp3",
            "key_vocab": "[]",
            "status": "unread",
            "is_bookmarked": 0,
            "dictation_accuracy": None,
        })

        db.upsert_paper({
            "id": "paper-2",
            "title": "Paper Two",
            "year": 2023,
            "month": 12,
            "set_number": 1,
            "category": "cet6-real",
            "total_duration_sec": 350,
            "sentence_count": 1,
            "version": 1,
            "audio_path": "audio-2.mp3",
        })
        db.insert_sentence({
            "id": "paper-2_s_1",
            "paper_id": "paper-2",
            "section_id": None,
            "idx": 1,
            "english": "Sentence 1 from paper 2",
            "chinese": "试卷2第1句",
            "start_time": 0.0,
            "end_time": 5.0,
            "audio_path": "audio-2_1.mp3",
            "key_vocab": "[]",
            "status": "unread",
            "is_bookmarked": 0,
            "dictation_accuracy": None,
        })

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_toggle_bookmark_adds_and_removes(self):
        # 1. Add bookmark
        res1 = db.toggle_bookmark("paper-1_s_1", "paper-1", note="难句")
        self.assertTrue(res1["bookmarked"])

        bms = db.get_bookmarks()
        self.assertEqual(len(bms), 1)
        self.assertEqual(bms[0]["sentence_id"], "paper-1_s_1")
        self.assertEqual(bms[0]["english"], "Sentence 1 from paper 1")
        self.assertEqual(bms[0]["paper_title"], "Paper One")

        # Check sentence flag
        paper = db.get_paper("paper-1")
        self.assertEqual(paper["sentences"][0]["is_bookmarked"], 1)

        # 2. Toggle again to remove
        res2 = db.toggle_bookmark("paper-1_s_1", "paper-1")
        self.assertFalse(res2["bookmarked"])

        bms_after = db.get_bookmarks()
        self.assertEqual(len(bms_after), 0)

        paper_after = db.get_paper("paper-1")
        self.assertEqual(paper_after["sentences"][0]["is_bookmarked"], 0)

    def test_bookmarks_across_multiple_papers(self):
        db.toggle_bookmark("paper-1_s_1", "paper-1", note="Note 1")
        db.toggle_bookmark("paper-2_s_1", "paper-2", note="Note 2")

        bms = db.get_bookmarks()
        self.assertEqual(len(bms), 2)

        s_ids = [b["sentence_id"] for b in bms]
        self.assertIn("paper-1_s_1", s_ids)
        self.assertIn("paper-2_s_1", s_ids)

        titles = [b["paper_title"] for b in bms]
        self.assertIn("Paper One", titles)
        self.assertIn("Paper Two", titles)

    def test_cascade_delete_paper_cleans_bookmarks(self):
        db.toggle_bookmark("paper-1_s_1", "paper-1")
        self.assertEqual(len(db.get_bookmarks()), 1)

        conn = db.get_conn()
        try:
            conn.execute("DELETE FROM papers WHERE id = 'paper-1'")
            conn.commit()
        finally:
            conn.close()

        # Due to foreign keys CASCADE on sentence_id -> sentences(id), bookmark is deleted
        self.assertEqual(len(db.get_bookmarks()), 0)


if __name__ == "__main__":
    unittest.main()
