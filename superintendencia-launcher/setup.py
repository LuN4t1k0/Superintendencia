import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AFPLookup"
PYTHON_DIR = BASE_DIR / "python"
PLAYWRIGHT_MARKER = BASE_DIR / ".playwright_done"

_PYTHON_VERSION = "3.12.9"
_PYTHON_URL = (
    f"https://www.python.org/ftp/python/{_PYTHON_VERSION}"
    f"/python-{_PYTHON_VERSION}-embed-amd64.zip"
)
_GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_python_ready() -> bool:
    return (PYTHON_DIR / "python.exe").exists()


def is_playwright_ready() -> bool:
    return PLAYWRIGHT_MARKER.exists()


def _format_command_error(label: str, command: list[str], exc: subprocess.CalledProcessError) -> str:
    output = "\n".join(
        part.strip()
        for part in (exc.stdout, exc.stderr)
        if part and part.strip()
    )
    if output:
        lines = output.splitlines()[-12:]
        output = "\n".join(lines)
    else:
        output = "Sin salida adicional del comando."

    return (
        f"{label} fallo con codigo {exc.returncode}.\n"
        f"Comando: {' '.join(command)}\n"
        f"Detalle:\n{output}"
    )


def _run_checked(command: list[str], label: str) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            creationflags=_NO_WINDOW,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(_format_command_error(label, command, exc)) from exc


def ensure_desktop_shortcut(on_status=None) -> None:
    if not sys.platform.startswith("win"):
        return

    exe_path = Path(sys.executable).resolve()
    desktop = Path.home() / "Desktop"
    shortcut = desktop / "AFP Lookup.lnk"

    if shortcut.exists() or not desktop.exists():
        return

    if on_status:
        on_status("Creando acceso directo...")

    ps_script = (
        "$s=(New-Object -COM WScript.Shell).CreateShortcut($args[0]);"
        "$s.TargetPath=$args[1];"
        "$s.WorkingDirectory=$args[2];"
        "$s.IconLocation=$args[1];"
        "$s.Save()"
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_script,
            str(shortcut),
            str(exe_path),
            str(exe_path.parent),
        ],
        check=False,
        creationflags=_NO_WINDOW,
    )


def install_python(on_status=None) -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    if on_status:
        on_status("Descargando Python...")
    zip_path = BASE_DIR / f"python_embed_{os.getpid()}.zip"
    get_pip = BASE_DIR / f"get-pip_{os.getpid()}.py"

    try:
        urllib.request.urlretrieve(_PYTHON_URL, zip_path)

        if on_status:
            on_status("Instalando Python...")
        PYTHON_DIR.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(PYTHON_DIR)

        pth_file = PYTHON_DIR / "python312._pth"
        text = pth_file.read_text()
        pth_file.write_text(text.replace("#import site", "import site"))

        if on_status:
            on_status("Instalando pip...")
        urllib.request.urlretrieve(_GET_PIP_URL, get_pip)
        subprocess.run(
            [str(PYTHON_DIR / "python.exe"), str(get_pip)],
            check=True,
            creationflags=_NO_WINDOW,
        )
    finally:
        zip_path.unlink(missing_ok=True)
        get_pip.unlink(missing_ok=True)


def install_playwright(on_status=None) -> None:
    if on_status:
        on_status("Descargando Chromium (primera vez, ~300 MB)...")
    python_exe = PYTHON_DIR / "python.exe"
    playwright_exe = PYTHON_DIR / "Scripts" / "playwright.exe"
    module_command = [str(python_exe), "-m", "playwright", "install", "chromium"]
    exe_command = [str(playwright_exe), "install", "chromium"]

    try:
        _run_checked(module_command, "La instalacion de Chromium con Playwright")
    except RuntimeError as first_error:
        try:
            _run_checked(exe_command, "La instalacion de Chromium con playwright.exe")
        except RuntimeError as second_error:
            raise RuntimeError(f"{first_error}\n\nReintento:\n{second_error}") from second_error

    PLAYWRIGHT_MARKER.write_text("done")
