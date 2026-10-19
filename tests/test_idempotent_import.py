"""Test idempotent re-import of seed papers preserving user progress and bookmarks."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db, import_data


class TestIdempotentImport(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.environ["LISTENINGLAB_DB"] = self.db_path
        db.init_db()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_idempotent_refresh_preserves_user_state(self):
        # 1. First import old placeholder version (5 sentences, duration 1560, version 1)
        placeholder_data = {
            "id": "cet6-2024-06-1",
            "title": "2024年6月 六级听力真题（第1套）[占位]",
            "year": 2024,
            "month": 6,
            "set_number": 1,
            "category": "cet6-real",
            "total_duration_sec": 1560,
            "sentence_count": 5,
            "version": 1,
            "audio_path": "content/papers/cet6-2024-06-1/placeholder.mp3",
            "sections": [
                {
                    "id": "cet6-2024-06-1_sec_1",
                    "paper_id": "cet6-2024-06-1",
                    "title": "Section A · 旧长对话",
                    "section_type": "Section A",
                    "sort_order": 1,
                }
            ],
            "sentences": [
                {
                    "id": f"cet6-2024-06-1_s_{i}",
                    "paper_id": "cet6-2024-06-1",
                    "section_id": "cet6-2024-06-1_sec_1",
                    "idx": i,
                    "english": f"Old placeholder sentence {i}.",
                    "chinese": f"旧占位句子 {i}。",
                    "start_time": (i - 1) * 3.0,
                    "end_time": i * 3.0,
                    "audio_path": "placeholder.mp3",
                    "key_vocab": [],
                    "status": "unread",
                    "is_bookmarked": 0,
                    "dictation_accuracy": None,
                }
                for i in range(1, 6)
            ],
            "questions": [
                {
                    "id": "cet6-2024-06-1_q_1",
                    "paper_id": "cet6-2024-06-1",
                    "section_id": "cet6-2024-06-1_sec_1",
                    "sentence_id": "cet6-2024-06-1_s_1",
                    "idx": 1,
                    "question_text": "Old placeholder question?",
                    "options": ["A) opt1", "B) opt2", "C) opt3", "D) opt4"],
                    "answer": "A",
                    "explanation": "Old explanation",
                }
            ],
        }

        success = import_data.import_paper_data(placeholder_data)
        self.assertTrue(success)

        old_p = db.get_paper("cet6-2024-06-1")
        self.assertEqual(old_p["total_duration_sec"], 1560)
        self.assertEqual(old_p["sentence_count"], 5)
        self.assertEqual(len(old_p["sentences"]), 5)
        self.assertEqual(len(old_p["questions"]), 1)

        # 2. Simulate user activity: save progress, bookmark sentence 1, submit dictation
        db.save_progress(
            "cet6-2024-06-1",
            {
                "current_sentence_idx": 3,
                "playback_rate": 1.25,
                "loop_mode": "sentence",
                "loop_count_target": 3,
                "transcript_visibility": "blur",
            },
        )
        db.toggle_bookmark("cet6-2024-06-1_s_1", "cet6-2024-06-1", note="难词复习")
        db.save_dictation(
            "cet6-2024-06-1_s_1",
            "cet6-2024-06-1",
            "Old placeholder sentence 1.",
            100.0,
            "[]",
        )

        bms = db.get_bookmarks()
        self.assertEqual(len(bms), 1)
        self.assertEqual(bms[0]["sentence_id"], "cet6-2024-06-1_s_1")

        # 3. Re-import the real paper JSON (40 sentences, 25 questions, version 1)
        real_json_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "content",
            "papers",
            "cet6-2024-06-1.json",
        )
        with open(real_json_path, "r", encoding="utf-8") as f:
            real_data = json.load(f)

        # Both have version 1, but seed import must idempotently refresh from JSON
        self.assertEqual(real_data.get("version", 1), 1)
        success = import_data.import_paper_data(real_data)
        self.assertTrue(success)

        # 4. Assert new content took effect in DB
        new_p = db.get_paper("cet6-2024-06-1")
        self.assertEqual(new_p["sentence_count"], 40)
        self.assertEqual(len(new_p["sentences"]), 40)
        self.assertEqual(len(new_p["questions"]), 25)
        self.assertNotEqual(new_p["total_duration_sec"], 1560)
        self.assertAlmostEqual(new_p["total_duration_sec"], real_data["total_duration_sec"], places=2)
        self.assertEqual(new_p["title"], real_data["title"])

        # Check question 1 and sentence 1 are the new real content
        self.assertIn("Hi Sarah", new_p["sentences"][0]["english"])
        self.assertEqual(new_p["questions"][0]["answer"], real_data["questions"][0]["answer"])

        # 5. Assert user state is NOT destroyed
        prog = db.get_progress("cet6-2024-06-1")
        self.assertIsNotNone(prog)
        self.assertEqual(prog["current_sentence_idx"], 3)
        self.assertEqual(prog["playback_rate"], 1.25)
        self.assertEqual(prog["loop_count_target"], 3)
        self.assertEqual(prog["transcript_visibility"], "blur")

        bms_after = db.get_bookmarks()
        self.assertEqual(len(bms_after), 1)
        self.assertEqual(bms_after[0]["sentence_id"], "cet6-2024-06-1_s_1")
        # Text in bookmark view now reflects new real sentence text
        self.assertIn("Hi Sarah", bms_after[0]["english"])

        dict_history = db.get_dictation_history("cet6-2024-06-1_s_1")
        self.assertEqual(len(dict_history), 1)
        self.assertEqual(dict_history[0]["accuracy"], 100.0)


if __name__ == "__main__":
    unittest.main()
