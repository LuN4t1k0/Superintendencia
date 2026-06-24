import subprocess
import time
import webbrowser

import requests

from setup import BASE_DIR, PYTHON_DIR

APP_DIR = BASE_DIR / "app"
PORT = 8502
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def wait_for_server(port: int, timeout: float = 30) -> bool:
    """Poll localhost until Streamlit responds or timeout expires."""
    url = f"http://localhost:{port}/healthz"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=1)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            time.sleep(0.5)
    return False


def launch(on_status=None) -> subprocess.Popen:
    """Start Streamlit and open the browser. Returns the subprocess."""
    if on_status:
        on_status("Iniciando aplicacion...")

    python_exe = PYTHON_DIR / "python.exe"
    app_script = APP_DIR / "app.py"

    proc = subprocess.Popen(
        [
            str(python_exe),
            "-m",
            "streamlit",
            "run",
            str(app_script),
            "--server.port",
            str(PORT),
            "--server.headless",
            "true",
            "--server.enableCORS",
            "false",
            "--server.enableXsrfProtection",
            "false",
        ],
        creationflags=_NO_WINDOW,
    )

    if on_status:
        on_status("Esperando que la app este lista...")
    if wait_for_server(PORT, timeout=60):
        webbrowser.open(f"http://localhost:{PORT}")
        if on_status:
            on_status("Listo. App abierta en el navegador.")
    else:
        if on_status:
            on_status("Advertencia: la app tardo mas de lo esperado.")
        webbrowser.open(f"http://localhost:{PORT}")

    return proc
