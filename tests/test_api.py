import unittest
import os
import sys
import json
import tempfile
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db, server, import_data


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.environ["LISTENINGLAB_DB"] = cls.db_path
        db.init_db()
        import_data.import_seed_papers()
        cls.server = server.HTTPServer(("127.0.0.1", 0), server.APIHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        os.close(cls.db_fd)
        os.unlink(cls.db_path)

    def _req(self, path, method="GET", data=None, headers=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url, method=method)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        if data:
            req.data = json.dumps(data).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_papers_list(self):
        r = self._req("/api/papers")
        self.assertIn("papers", r)
        self.assertGreaterEqual(len(r["papers"]), 2)

    def test_paper_detail(self):
        r = self._req("/api/papers/cet6-2024-06-1")
        self.assertEqual(r["id"], "cet6-2024-06-1")
        self.assertIn("sentences", r)
        self.assertGreaterEqual(len(r["sentences"]), 5)

    def test_progress_save_restore(self):
        self._req("/api/progress", "POST", {
            "paper_id": "cet6-2024-06-1",
            "current_sentence_idx": 3,
            "playback_rate": 1.2,
            "loop_mode": "sentence",
            "loop_count_target": 3,
            "transcript_visibility": "blur",
        })
        r = self._req("/api/progress?paper_id=cet6-2024-06-1")
        self.assertEqual(r["current_sentence_idx"], 3)
        self.assertEqual(r["playback_rate"], 1.2)

    def test_bookmark_toggle(self):
        r = self._req("/api/bookmarks", "POST", {
            "sentence_id": "cet6-2024-06-1_s_1",
            "paper_id": "cet6-2024-06-1",
        })
        self.assertIn("bookmarked", r)
        r2 = self._req("/api/bookmarks")
        self.assertIn("bookmarks", r2)

    def test_dictation(self):
        r = self._req("/api/dictation", "POST", {
            "sentence_id": "cet6-2024-06-1_s_1",
            "paper_id": "cet6-2024-06-1",
            "user_input": "Good morning everyone today we discuss urban planning",
            "expected": "Good morning, everyone. Today we'll discuss urban planning and sustainable development.",
        })
        self.assertIn("accuracy", r)
        self.assertIn("tokens", r)
        self.assertGreaterEqual(r["accuracy"], 0)
        self.assertLessEqual(r["accuracy"], 100)

    def test_settings(self):
        self._req("/api/settings", "POST", {
            "default_playback_rate": 1.25,
            "default_loop_count": 3,
            "theme": "dark",
        })
        r = self._req("/api/settings")
        self.assertEqual(r["default_playback_rate"], 1.25)
        self.assertEqual(r["default_loop_count"], 3)

    def test_static_file(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            html = resp.read().decode("utf-8")
            self.assertIn("ListeningLab", html)

    def test_audio_path(self):
        r = self._req("/api/papers/cet6-2024-06-1")
        self.assertTrue(r.get("audio_path") or any(s.get("audio_path") for s in r.get("sentences", [])))


if __name__ == "__main__":
    unittest.main()