import re
import time

from playwright.sync_api import Page

_URL = "https://www.spensiones.cl/apps/certificados/formConsultaAfiliacion.php"
_PAUSE = 1.5
_AFP_RE = re.compile(r"incorporado\(a\) a AFP\s+([A-ZÁÉÍÓÚÑ]+)", re.IGNORECASE)


def normalize_rut(rut: str) -> str:
    """Return a RUT without dots or hyphen."""
    return re.sub(r"[.\-]", "", rut.strip())


def extract_afp(text: str) -> str | None:
    """Extract the AFP name from the result page text."""
    match = _AFP_RE.search(text)
    return match.group(1).strip().upper() if match else None


def _query_once(page: Page, rut: str) -> str:
    page.goto(_URL, timeout=15_000)
    page.wait_for_load_state("domcontentloaded")
    page.fill("input[name='rut']", normalize_rut(rut))
    page.locator("input[type='submit']").first.click()
    page.wait_for_load_state("domcontentloaded", timeout=15_000)

    text = page.locator("body").inner_text()
    afp = extract_afp(text)
    return afp if afp else "SIN DATOS"


def query_rut(page: Page, rut: str) -> str:
    """Query spensiones.cl for one RUT and return AFP, SIN DATOS, or ERROR."""
    try:
        try:
            return _query_once(page, rut)
        except Exception:
            return _query_once(page, rut)
    except Exception:
        return "ERROR"
    finally:
        time.sleep(_PAUSE)
