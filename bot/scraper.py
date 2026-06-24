import re
import time
import urllib.request
from collections.abc import Callable

from playwright.sync_api import Page

_URL = "https://www.spensiones.cl/apps/certificados/formConsultaAfiliacion.php"
_ACTION_URL = "consultaAfiliacion.php"
_PAUSE = 1.5
_AFP_RE = re.compile(r"incorporado\(a\) a AFP\s+([A-ZÁÉÍÓÚÑ]+)", re.IGNORECASE)


def get_public_ip() -> str | None:
    """Return the current public IP, or None if the request fails."""
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as resp:
            return resp.read().decode().strip()
    except Exception:
        return None


def normalize_rut(rut: str) -> str:
    """Return a RUT without dots or hyphen."""
    return re.sub(r"[.\-]", "", rut.strip())


def extract_afp(text: str) -> str | None:
    """Extract the AFP name from the result page text."""
    match = _AFP_RE.search(text)
    return match.group(1).strip().upper() if match else None


def _ensure_form_loaded(page: Page, log: Callable[[str], None] | None = None) -> None:
    try:
        if page.locator("input[name='sessionid']").count() > 0:
            return
    except Exception:
        pass

    if log:
        log("Abriendo formulario de spensiones.cl")
    page.goto(_URL, timeout=15_000)
    page.wait_for_load_state("domcontentloaded")


def _query_once(page: Page, rut: str, log: Callable[[str], None] | None = None) -> str:
    _ensure_form_loaded(page, log=log)

    if log:
        log("Enviando POST directo desde contexto navegador")

    text = page.evaluate(
        """async ({ actionUrl, rut }) => {
            const sessionInput = document.querySelector("input[name='sessionid']");
            if (!sessionInput) {
                throw new Error("No se encontro sessionid en el formulario");
            }

            const body = new URLSearchParams({
                sessionid: sessionInput.value,
                rut,
                "g-recaptcha-response": "",
            });

            const response = await fetch(actionUrl, {
                method: "POST",
                headers: {"Content-Type": "application/x-www-form-urlencoded"},
                body,
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, "text/html");
            return doc.body ? doc.body.innerText : html;
        }""",
        {"actionUrl": _ACTION_URL, "rut": normalize_rut(rut)},
    )

    if log:
        log("Leyendo respuesta")
    afp = extract_afp(text)
    return afp if afp else "SIN DATOS"


def query_rut(
    page: Page,
    rut: str,
    pause_seconds: float = _PAUSE,
    log: Callable[[str], None] | None = None,
) -> str:
    """Query spensiones.cl for one RUT and return AFP, SIN DATOS, or ERROR."""
    try:
        try:
            return _query_once(page, rut, log=log)
        except Exception as exc:
            if log:
                log(f"Primer intento fallo: {exc}. Reintentando")
            return _query_once(page, rut, log=log)
    except Exception as exc:
        if log:
            log(f"Consulta fallo definitivamente: {exc}")
        return "ERROR"
    finally:
        if log:
            log(f"Pausa de {pause_seconds:.2f}s antes de continuar")
        time.sleep(max(0.0, pause_seconds))
