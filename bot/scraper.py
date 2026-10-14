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
_BLOCKED_TEXT_RE = re.compile(
    r"(?:"
    r"error\s+de\s+validaci[oó]n|recaptcha|demasiadas\s+(?:solicitudes|consultas)|"
    r"too\s+many\s+requests|acceso\s+(?:temporalmente\s+)?bloqueado|"
    r"intente\s+(?:nuevamente\s+)?m[aá]s\s+tarde|rate\s*limit"
    r")",
    re.IGNORECASE,
)
_BLOCKING_HTTP_STATUSES = {403, 429}


class PortalBlockedError(RuntimeError):
    """Raised when the portal explicitly rejects or throttles a query."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def detect_block_reason(text: str, http_statuses: list[int] | None = None) -> str | None:
    """Return a human-readable reason when a portal response indicates blocking."""
    statuses = http_statuses or []
    for status in statuses:
        if status in _BLOCKING_HTTP_STATUSES:
            return f"El portal rechazo la consulta con codigo HTTP {status}."

    match = _BLOCKED_TEXT_RE.search(text or "")
    if match:
        return f"El portal mostro una señal de bloqueo: {match.group(0)}."
    return None


def _is_query_response(response) -> bool:
    """Limit status inspection to calls made by the consultation portal or its API."""
    try:
        url = response.url.lower()
        resource_type = response.request.resource_type
    except Exception:
        return False
    is_portal_url = (
        "spensiones.gob.cl" in url or "execute-api" in url or "consulta" in url
    )
    return is_portal_url and resource_type in {"document", "fetch", "xhr"}


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

    blocking_statuses: list[int] = []

    def inspect_response(response) -> None:
        if _is_query_response(response) and response.status in _BLOCKING_HTTP_STATUSES:
            blocking_statuses.append(response.status)

    page.on("response", inspect_response)
    try:
        page.locator("input[placeholder*='33333333']").fill(format_rut_for_portal(rut))
        page.locator("button").filter(has_text="BUSCAR").click(timeout=10_000)

        try:
            page.wait_for_function(
                """() => {
                    const text = document.body ? document.body.innerText : "";
                    return /se encuentra incorporado\\(a\\) a AFP|no se encuentra incorporada a ninguna Administradora|Error de validaci|ReCaptcha|demasiadas solicitudes|intente nuevamente m[aá]s tarde/i.test(text);
                }""",
                timeout=20_000,
            )
        except Exception:
            pass

        text = page.locator("body").inner_text(timeout=5_000)
    finally:
        try:
            page.remove_listener("response", inspect_response)
        except Exception:
            pass

    block_reason = detect_block_reason(text, blocking_statuses)
    if block_reason:
        status_code = blocking_statuses[0] if blocking_statuses else None
        raise PortalBlockedError(block_reason, status_code=status_code)

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
        except PortalBlockedError:
            raise
        except Exception as exc:
            if log:
                log(f"Primer intento fallo: {exc}. Reintentando")
            return _query_once(page, rut, log=log)
    except PortalBlockedError:
        raise
    except Exception as exc:
        if log:
            log(f"Consulta fallo definitivamente: {exc}")
        return "ERROR"
    finally:
        if log:
            log(f"Pausa de {pause_seconds:.2f}s antes de continuar")
        time.sleep(max(0.0, pause_seconds))
