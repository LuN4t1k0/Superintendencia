import http.server
import json
import os
import socketserver
import urllib.error
import urllib.request
from pathlib import Path

PORT = int(os.environ.get("PORT", 8000))
HTML = Path(__file__).parent / "landing.html"
LATEST_RELEASE_API = "https://api.github.com/repos/LuN4t1k0/Superintendencia/releases/latest"
FALLBACK_DOWNLOAD_URL = (
    "https://github.com/LuN4t1k0/Superintendencia/releases/download/"
    "v0.1.6/AFP-Lookup-Setup-0.1.6.exe"
)


def latest_windows_installer_url():
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "afp-lookup-landing"
        }
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return FALLBACK_DOWNLOAD_URL

    for asset in payload.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".exe") and name.startswith("AFP-Lookup-Setup-"):
            return asset.get("browser_download_url") or FALLBACK_DOWNLOAD_URL

    return FALLBACK_DOWNLOAD_URL


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") == "/download/windows":
            self.send_response(302)
            self.send_header("Location", latest_windows_installer_url())
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.read_bytes())

    def log_message(self, *args):
        pass


with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Landing page en puerto {PORT}", flush=True)
    httpd.serve_forever()
