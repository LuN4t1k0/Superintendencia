import re
import time
import urllib.request
from collections.abc import Callable

from playwright.sync_api import Page

_URL = "https://miportal.spensiones.gob.cl/tramitesServicios/ConsultaAfiliacion"
_PAUSE = 1.5
_AFP_RE = re.compile(r"incorporado\(a\) a AFP\s+([A-ZÁÉÍÓÚÑ]+)", re.IGNORECASE)
_NOT_AFFILIATED_RE = re.compile(
    r"no se encuentra incorporad[ao] a ninguna Administradora", re.IGNORECASE
)


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


def format_rut_for_portal(rut: str) -> str:
    """Return a RUT without dots and with hyphen before the verifier digit."""
    clean = normalize_rut(rut)
    if len(clean) < 2:
        return clean
    return f"{clean[:-1]}-{clean[-1]}"


def extract_afp(text: str) -> str | None:
    """Extract the AFP name from the result page text."""
    match = _AFP_RE.search(text)
    return match.group(1).strip().upper() if match else None


def _ensure_form_loaded(page: Page, log: Callable[[str], None] | None = None) -> None:
    try:
        if page.locator("input[placeholder*='33333333']").count() > 0:
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
        log("Consultando en nuevo portal Mi Portal SP")

    page.locator("input[placeholder*='33333333']").fill(format_rut_for_portal(rut))
    page.locator("button").filter(has_text="BUSCAR").click(timeout=10_000)

    try:
        page.wait_for_function(
            """() => {
                const text = document.body ? document.body.innerText : "";
                return /se encuentra incorporado\\(a\\) a AFP|no se encuentra incorporada a ninguna Administradora|Error de validaci/i.test(text);
            }""",
            timeout=20_000,
        )
    except Exception:
        pass

    text = page.locator("body").inner_text(timeout=5_000)
    if "Error de validación" in text or "ReCaptcha" in text:
        raise RuntimeError("El portal rechazo la validacion reCAPTCHA.")

    if log:
        log("Leyendo respuesta")
    afp = extract_afp(text)
    if afp:
        return afp
    if _NOT_AFFILIATED_RE.search(text):
        return "SIN DATOS"
    raise RuntimeError("El portal no entrego un resultado reconocible.")


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
