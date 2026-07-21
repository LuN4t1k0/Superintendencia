import http.server
import os
import socketserver
from pathlib import Path

PORT = int(os.environ.get("PORT", 8000))
HTML = Path(__file__).parent / "landing.html"


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.read_bytes())

    def log_message(self, *args):
        pass


with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Landing page en puerto {PORT}", flush=True)
    httpd.serve_forever()
