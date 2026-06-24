import shutil
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

import requests

try:
    from config import GITHUB_BRANCH, GITHUB_OWNER, GITHUB_REPO, GITHUB_TOKEN
except ModuleNotFoundError:
    from config_example import GITHUB_BRANCH, GITHUB_OWNER, GITHUB_REPO, GITHUB_TOKEN
from setup import BASE_DIR, PYTHON_DIR

APP_DIR = BASE_DIR / "app"
VERSION_FILE = BASE_DIR / ".version"

_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def get_remote_sha() -> str:
    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/commits/{GITHUB_BRANCH}"
    )
    resp = requests.get(url, headers=_HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()["sha"]


def get_local_sha() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return ""


def needs_update() -> bool:
    return get_remote_sha() != get_local_sha()


def extract_zip_contents(raw_zip: bytes, app_dir: Path) -> None:
    """Extract a GitHub zipball into app_dir, removing any previous app copy."""
    if app_dir.exists():
        shutil.rmtree(app_dir)
    app_dir.mkdir(parents=True)
    app_root = app_dir.resolve()

    with zipfile.ZipFile(BytesIO(raw_zip)) as zf:
        names = zf.namelist()
        if not names:
            return

        top = names[0].split("/")[0] + "/"
        for member in names:
            relative = member[len(top):]
            if not relative:
                continue

            target = app_dir / relative
            resolved_target = target.resolve()
            if app_root not in (resolved_target, *resolved_target.parents):
                raise ValueError(f"Unsafe zip member path: {member}")

            if member.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))


def download_and_install(on_status=None) -> None:
    if on_status:
        on_status("Descargando actualizacion...")
    sha = get_remote_sha()
    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/zipball/{GITHUB_BRANCH}"
    )
    resp = requests.get(url, headers=_HEADERS, timeout=60)
    resp.raise_for_status()

    if on_status:
        on_status("Instalando actualizacion...")
    extract_zip_contents(resp.content, APP_DIR)

    if on_status:
        on_status("Actualizando dependencias...")
    pip_exe = PYTHON_DIR / "Scripts" / "pip.exe"
    subprocess.run(
        [str(pip_exe), "install", "-r", str(APP_DIR / "requirements.txt"), "-q"],
        check=True,
        creationflags=_NO_WINDOW,
    )

    VERSION_FILE.write_text(sha)
