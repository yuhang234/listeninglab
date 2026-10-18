"""ListeningLab HTTP server using Python 3.13 stdlib only."""
import json
import os
import re
import sys
import shutil
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Ensure app modules are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db, diff, import_data

STATIC_DIR = "web"
UPLOAD_DIR = "content/imported"
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200MB


def json_response(handler, data, status=200):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def error_response(handler, message, status=400):
    json_response(handler, {"error": message}, status)


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Quiet logs

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # API routes
        if path == "/api/papers":
            papers = db.get_papers()
            for p in papers:
                p["progress"] = db.get_progress(p["id"])
            json_response(self, {"papers": papers})
            return

        m = re.match(r"^/api/papers/([^/]+)$", path)
        if m:
            paper_id = urllib.parse.unquote(m.group(1))
            paper = db.get_paper(paper_id)
            if not paper:
                error_response(self, "paper not found", 404)
                return
            paper["progress"] = db.get_progress(paper_id)
            json_response(self, paper)
            return

        if path == "/api/progress":
            query = urllib.parse.parse_qs(parsed.query)
            paper_id = query.get("paper_id", [None])[0]
            if paper_id:
                prog = db.get_progress(paper_id)
                json_response(self, prog or {})
            else:
                json_response(self, {"progress": db.get_all_progress()})
            return

        if path == "/api/bookmarks":
            json_response(self, {"bookmarks": db.get_bookmarks()})
            return

        if path == "/api/stats":
            json_response(self, db.get_stats())
            return

        if path == "/api/settings":
            json_response(self, db.get_settings())
            return

        if path == "/api/dictation":
            query = urllib.parse.parse_qs(parsed.query)
            sentence_id = query.get("sentence_id", [None])[0]
            if sentence_id:
                history = db.get_dictation_history(sentence_id)
                json_response(self, {"history": history})
            else:
                json_response(self, {"history": []})
            return

        # Static files
        if path == "/":
            path = "/index.html"
        file_path = os.path.join(STATIC_DIR, path.lstrip("/"))
        safe_path = os.path.abspath(os.path.normpath(file_path))
        if not safe_path.startswith(os.path.abspath(STATIC_DIR)):
            # Allow serving content/papers/ audio files
            if path.startswith("/content/papers/"):
                content_path = os.path.abspath(os.path.normpath(path.lstrip("/")))
                if os.path.isfile(content_path):
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/mpeg")
                    self.end_headers()
                    with open(content_path, "rb") as f:
                        shutil.copyfileobj(f, self.wfile)
                    return
            error_response(self, "forbidden", 403)
            return

        if os.path.isfile(safe_path):
            content_type = "application/octet-stream"
            if safe_path.endswith(".html"):
                content_type = "text/html; charset=utf-8"
            elif safe_path.endswith(".css"):
                content_type = "text/css; charset=utf-8"
            elif safe_path.endswith(".js"):
                content_type = "application/javascript; charset=utf-8"
            elif safe_path.endswith(".json"):
                content_type = "application/json; charset=utf-8"
            elif safe_path.endswith(".mp3"):
                content_type = "audio/mpeg"
            elif safe_path.endswith(".svg"):
                content_type = "image/svg+xml"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            with open(safe_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        error_response(self, "not found", 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > MAX_UPLOAD_SIZE:
            error_response(self, "payload too large", 413)
            return

        body = self.rfile.read(content_length)
        content_type = self.headers.get("Content-Type", "")

        # Handle multipart form data (file uploads)
        if content_type.startswith("multipart/form-data"):
            self._handle_multipart(path, content_type, body)
            return

        # JSON endpoints
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError as e:
            error_response(self, f"invalid JSON: {e}")
            return

        if path == "/api/progress":
            paper_id = data.get("paper_id")
            if not paper_id:
                error_response(self, "paper_id required")
                return
            db.save_progress(paper_id, data)
            json_response(self, {"ok": True})
            return

        if path == "/api/bookmarks":
            sentence_id = data.get("sentence_id")
            paper_id = data.get("paper_id")
            if not sentence_id or not paper_id:
                error_response(self, "sentence_id and paper_id required")
                return
            result = db.toggle_bookmark(sentence_id, paper_id, data.get("note", ""))
            json_response(self, result)
            return

        if path == "/api/dictation":
            sentence_id = data.get("sentence_id")
            paper_id = data.get("paper_id")
            user_input = data.get("user_input", "")
            if not sentence_id or not paper_id:
                error_response(self, "sentence_id and paper_id required")
                return
            settings = db.get_settings()
            diff_result = diff.compute_diff(
                data.get("expected", ""),
                user_input,
                ignore_punctuation=bool(settings.get("ignore_punctuation", 1)),
                case_sensitive=bool(settings.get("case_sensitive_dictation", 0)),
            )
            db.save_dictation(sentence_id, paper_id, user_input, diff_result["accuracy"], json.dumps(diff_result["tokens"], ensure_ascii=False))
            json_response(self, diff_result)
            return

        if path == "/api/settings":
            db.save_settings(data)
            json_response(self, {"ok": True})
            return

        error_response(self, "not found", 404)

    def _handle_multipart(self, path, content_type, body):
        if path != "/api/import":
            error_response(self, "not found", 404)
            return

        boundary = re.search(r'boundary=([^;\s]+)', content_type)
        if not boundary:
            error_response(self, "missing boundary")
            return
        b = boundary.group(1).strip('"')
        parts = body.split(("--" + b).encode())

        fields = {}
        uploaded_audio_path = None

        for part in parts:
            part = part.strip()
            if not part or part == b"--":
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                header_end = part.find(b"\n\n")
                sep = b"\n\n"
            else:
                sep = b"\r\n\r\n"
            headers = part[:header_end].decode("utf-8", errors="ignore")
            payload = part[header_end + len(sep):]
            if payload.endswith(b"\r\n"):
                payload = payload[:-2]
            elif payload.endswith(b"\n"):
                payload = payload[:-1]

            cd_match = re.search(r'Content-Disposition:[^;]*;\s*name="([^"]+)"(?:;\s*filename="([^"]*)")?', headers, re.IGNORECASE)
            if not cd_match:
                continue
            name = cd_match.group(1)
            filename = cd_match.group(2)

            if filename:
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                dest = os.path.join(UPLOAD_DIR, filename)
                with open(dest, "wb") as f:
                    f.write(payload)
                uploaded_audio_path = dest
            else:
                fields[name] = payload.decode("utf-8", errors="ignore")

        paper_id = fields.get("paper_id", "imported_" + str(int(__import__("time").time())))
        subtitle_text = fields.get("subtitle", "")
        subtitle_format = fields.get("subtitle_format", "txt")

        try:
            result = import_data.handle_import(paper_id, uploaded_audio_path or "", subtitle_text, subtitle_format)
            json_response(self, result)
        except Exception as e:
            error_response(self, str(e), 500)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        m = re.match(r"^/api/bookmarks/([^/]+)$", path)
        if m:
            sentence_id = urllib.parse.unquote(m.group(1))
            conn = db.get_conn()
            try:
                conn.execute("DELETE FROM bookmarks WHERE sentence_id = ?", (sentence_id,))
                conn.execute("UPDATE sentences SET is_bookmarked = 0 WHERE id = ?", (sentence_id,))
                conn.commit()
                json_response(self, {"ok": True})
            finally:
                conn.close()
            return

        error_response(self, "not found", 404)


def run_server(port=8765):
    db.init_db()
    import_data.import_seed_papers()
    server = HTTPServer(("127.0.0.1", port), APIHandler)
    print(f"ListeningLab server running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    port = 8765
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])
    elif len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)