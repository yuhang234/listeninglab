"""Test playback settings, audio serving Range requests, and missing audio hints."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db, server, import_data


class TestSettingsAndPlayback(unittest.TestCase):
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
        if os.path.exists(cls.db_path):
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
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_settings_storage_and_retrieval(self):
        # Update settings
        status, _, body = self._req("/api/settings", "POST", {
            "default_playback_rate": 1.75,
            "default_loop_count": 5,
            "default_transcript_visibility": "hidden",
            "auto_play_next": True,
            "case_sensitive_dictation": False,
            "ignore_punctuation": True,
            "theme": "dark",
        })
        self.assertEqual(status, 200)

        # Get settings
        status, _, body = self._req("/api/settings")
        self.assertEqual(status, 200)
        settings = json.loads(body.decode("utf-8"))
        self.assertEqual(settings["default_playback_rate"], 1.75)
        self.assertEqual(settings["default_loop_count"], 5)
        self.assertEqual(settings["default_transcript_visibility"], "hidden")
        self.assertEqual(settings["auto_play_next"], 1)
        self.assertEqual(settings["theme"], "dark")

    def test_audio_range_request(self):
        # Request first 16 bytes of full.mp3
        status, headers, body = self._req(
            "/content/papers/cet6-2024-06-1/full.mp3",
            headers={"Range": "bytes=0-15"},
        )
        self.assertEqual(status, 206)
        self.assertEqual(len(body), 16)
        self.assertIn("content-range", {k.lower(): v for k, v in headers.items()})
        self.assertIn("accept-ranges", {k.lower(): v for k, v in headers.items()})

    def test_missing_audio_gives_actionable_tts_command(self):
        # Request non-existent audio file under content/papers
        status, _, body = self._req("/content/papers/cet6-nonexistent-1/full.mp3")
        self.assertEqual(status, 404)
        err_json = json.loads(body.decode("utf-8"))
        self.assertIn("error", err_json)
        self.assertIn("python3 content/tts/synthesize.py content/papers/cet6-nonexistent-1.json", err_json["error"])

    def test_imported_audio_missing_returns_404(self):
        status, _, body = self._req("/content/imported/nonexistent_id/audio.mp3")
        self.assertEqual(status, 404)
        err_json = json.loads(body.decode("utf-8"))
        self.assertIn("error", err_json)


if __name__ == "__main__":
    unittest.main()
