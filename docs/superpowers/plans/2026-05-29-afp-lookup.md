# AFP Affiliation Lookup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit app that recibe un Excel con RUTs, consulta la AFP de cada uno en spensiones.cl, y devuelve el mismo Excel con la columna AFP 2 completada.

**Architecture:** Playwright headless reutiliza una instancia de browser almacenada en `st.session_state` a través de reruns. Se procesa un RUT por rerun con `st.rerun()` para actualizar el progreso sin threading. openpyxl maneja la lectura y escritura del Excel en memoria.

**Tech Stack:** Python 3.12, Streamlit ≥ 1.32, Playwright ≥ 1.44, openpyxl ≥ 3.1, pytest ≥ 8.0

## Global Constraints

- URL objetivo: `https://www.spensiones.cl/apps/certificados/formConsultaAfiliacion.php`
- RUTs en Excel: formato `15800185-3` (con guión, sin puntos)
- RUTs para el sitio: `158001853` (sin puntos ni guión)
- AFP 2 es el nombre de la columna destino en el Excel
- Pausa entre consultas: 1.5 segundos
- Resultados posibles por RUT: nombre AFP (ej. `HABITAT`), `SIN DATOS`, `ERROR`
- Sin threading — un RUT por rerun de Streamlit
- Sin archivos temporales — todo en memoria

---

## File Map

| Archivo | Responsabilidad |
|---------|----------------|
| `requirements.txt` | Dependencias del proyecto |
| `.gitignore` | Excluir venv, cache, __pycache__ |
| `bot/__init__.py` | Vacío |
| `bot/scraper.py` | normalize_rut, extract_afp, query_rut |
| `bot/excel.py` | read_ruts, find_or_create_afp2_column, write_afp, to_bytes |
| `app.py` | Streamlit UI — paso 0 (bienvenida), 1 (subir), 2 (procesar), 3 (descargar) |
| `tests/test_scraper.py` | Tests unitarios scraper |
| `tests/test_excel.py` | Tests unitarios excel |
| `tests/__init__.py` | Vacío |

---

## Task 1: Scaffold del proyecto

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `bot/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Crear `requirements.txt`**

```
streamlit>=1.32.0
playwright>=1.44.0
openpyxl>=3.1.0
pytest>=8.0.0
```

- [ ] **Step 2: Crear `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
build/
```

- [ ] **Step 3: Crear archivos vacíos**

```bash
touch bot/__init__.py tests/__init__.py
```

- [ ] **Step 4: Crear y activar entorno virtual**

```bash
cd ~/Documents/desarrollo/SuperIntendencia
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Expected: instala streamlit, playwright, openpyxl, pytest sin errores.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore bot/__init__.py tests/__init__.py
git commit -m "feat: scaffold project with dependencies"
```

---

## Task 2: Módulo scraper

**Files:**
- Create: `bot/scraper.py`
- Create: `tests/test_scraper.py`

**Interfaces:**
- Produces:
  - `normalize_rut(rut: str) -> str`
  - `extract_afp(text: str) -> str | None`
  - `query_rut(page: Page, rut: str) -> str`

- [ ] **Step 1: Escribir los tests**

Crear `tests/test_scraper.py`:

```python
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.scraper import normalize_rut, extract_afp


def test_normalize_rut_con_puntos_y_guion():
    assert normalize_rut("15.800.185-3") == "158001853"


def test_normalize_rut_solo_guion():
    assert normalize_rut("15800185-3") == "158001853"


def test_normalize_rut_ya_limpio():
    assert normalize_rut("158001853") == "158001853"


def test_normalize_rut_strips_espacios():
    assert normalize_rut("  15800185-3  ") == "158001853"


def test_extract_afp_habitat():
    texto = (
        "Certifico que el(la) señor(a) RODRIGO IGNACIO ESCANILLA MIRANDA, "
        "RUT N° 15800185-3 se encuentra incorporado(a) a AFP HABITAT, "
        "con fecha 1 de Marzo de 2006."
    )
    assert extract_afp(texto) == "HABITAT"


def test_extract_afp_capital():
    texto = "...se encuentra incorporado(a) a AFP CAPITAL, con fecha..."
    assert extract_afp(texto) == "CAPITAL"


def test_extract_afp_planvital():
    texto = "...se encuentra incorporado(a) a AFP PLANVITAL, con fecha..."
    assert extract_afp(texto) == "PLANVITAL"


def test_extract_afp_no_encontrado():
    texto = "RUT no registrado o no encontrado en el sistema."
    assert extract_afp(texto) is None
```

- [ ] **Step 2: Correr tests — deben fallar**

```bash
cd ~/Documents/desarrollo/SuperIntendencia
source .venv/bin/activate
python -m pytest tests/test_scraper.py -v
```

Expected: `ModuleNotFoundError: No module named 'bot.scraper'`

- [ ] **Step 3: Crear `bot/scraper.py`**

```python
import re
import time

from playwright.sync_api import Page

_URL = "https://www.spensiones.cl/apps/certificados/formConsultaAfiliacion.php"
_PAUSE = 1.5
_AFP_RE = re.compile(r"incorporado\(a\) a AFP\s+([A-ZÁÉÍÓÚÑ]+)", re.IGNORECASE)


def normalize_rut(rut: str) -> str:
    """'15.800.185-3' o '15800185-3' → '158001853'"""
    return re.sub(r"[.\-]", "", rut.strip())


def extract_afp(text: str) -> str | None:
    """Extrae nombre AFP del texto de resultado. Retorna ej. 'HABITAT' o None."""
    match = _AFP_RE.search(text)
    return match.group(1).strip() if match else None


def query_rut(page: Page, rut: str) -> str:
    """Consulta un RUT en spensiones.cl. Retorna AFP, 'SIN DATOS' o 'ERROR'."""
    try:
        page.goto(_URL, timeout=15_000)
        page.wait_for_load_state("domcontentloaded")
        page.fill("input[name='rut']", normalize_rut(rut))
        page.locator("input[type='submit']").first.click()
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
        text = page.locator("body").inner_text()
        afp = extract_afp(text)
        return afp if afp else "SIN DATOS"
    except Exception:
        return "ERROR"
    finally:
        time.sleep(_PAUSE)
```

- [ ] **Step 4: Correr tests — deben pasar**

```bash
python -m pytest tests/test_scraper.py -v
```

Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/scraper.py tests/test_scraper.py
git commit -m "feat: add scraper module with RUT normalization and AFP extraction"
```

---

## Task 3: Módulo Excel

**Files:**
- Create: `bot/excel.py`
- Create: `tests/test_excel.py`

**Interfaces:**
- Consumes: nada de tareas anteriores
- Produces:
  - `read_ruts(file_bytes: bytes) -> tuple[Workbook, Worksheet, int, list[int]]`
  - `find_or_create_afp2_column(ws: Worksheet) -> int`
  - `write_afp(ws: Worksheet, row: int, col: int, value: str) -> None`
  - `to_bytes(wb: Workbook) -> bytes`

- [ ] **Step 1: Escribir los tests**

Crear `tests/test_excel.py`:

```python
import io
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook, load_workbook
from bot.excel import read_ruts, find_or_create_afp2_column, write_afp, to_bytes


def _make_excel(headers: list, rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_read_ruts_detecta_columna_rut():
    data = _make_excel(
        ["Nombre", "RUT", "AFP"],
        [["Juan", "15800185-3", ""], ["Maria", "12345678-9", ""]],
    )
    wb, ws, rut_col, data_rows = read_ruts(data)
    assert rut_col == 2
    assert data_rows == [2, 3]


def test_read_ruts_case_insensitive():
    data = _make_excel(["Nombre", "Rut Trabajador"], [["Juan", "15800185-3"]])
    wb, ws, rut_col, data_rows = read_ruts(data)
    assert rut_col == 2


def test_read_ruts_sin_columna_rut_lanza_error():
    data = _make_excel(["Nombre", "AFP"], [["Juan", "HABITAT"]])
    with pytest.raises(ValueError, match="No se encontró"):
        read_ruts(data)


def test_read_ruts_ignora_filas_vacias():
    data = _make_excel(
        ["RUT"],
        [["15800185-3"], [None], ["12345678-9"]],
    )
    wb, ws, rut_col, data_rows = read_ruts(data)
    assert data_rows == [2, 4]


def test_find_or_create_afp2_existente():
    wb = Workbook()
    ws = wb.active
    ws.append(["RUT", "AFP 2", "Nombre"])
    assert find_or_create_afp2_column(ws) == 2


def test_find_or_create_afp2_crea_nueva():
    wb = Workbook()
    ws = wb.active
    ws.append(["RUT", "Nombre"])
    col = find_or_create_afp2_column(ws)
    assert col == 3
    assert ws.cell(1, 3).value == "AFP 2"


def test_write_afp():
    wb = Workbook()
    ws = wb.active
    ws.append(["RUT", "AFP 2"])
    ws.append(["15800185-3", ""])
    write_afp(ws, 2, 2, "HABITAT")
    assert ws.cell(2, 2).value == "HABITAT"


def test_to_bytes_roundtrip():
    wb = Workbook()
    wb.active.append(["RUT", "AFP 2"])
    wb.active.append(["15800185-3", "HABITAT"])
    raw = to_bytes(wb)
    wb2 = load_workbook(io.BytesIO(raw))
    assert wb2.active.cell(2, 2).value == "HABITAT"
```

- [ ] **Step 2: Correr tests — deben fallar**

```bash
python -m pytest tests/test_excel.py -v
```

Expected: `ModuleNotFoundError: No module named 'bot.excel'`

- [ ] **Step 3: Crear `bot/excel.py`**

```python
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet


def read_ruts(file_bytes: bytes) -> tuple[Workbook, Worksheet, int, list[int]]:
    """Carga el Excel, detecta columna RUT, retorna (wb, ws, rut_col, data_rows).
    rut_col y columnas son índices 1-based (convención openpyxl).
    """
    wb = load_workbook(BytesIO(file_bytes))
    ws = wb.active

    rut_col = None
    for cell in next(ws.iter_rows(1, 1)):
        if cell.value and "rut" in str(cell.value).lower():
            rut_col = cell.column
            break

    if rut_col is None:
        raise ValueError("No se encontró columna con 'RUT' en el header")

    data_rows = [
        row
        for row in range(2, ws.max_row + 1)
        if ws.cell(row, rut_col).value is not None
    ]
    return wb, ws, rut_col, data_rows


def find_or_create_afp2_column(ws: Worksheet) -> int:
    """Retorna la columna 'AFP 2' (1-based). La crea al final si no existe."""
    for cell in next(ws.iter_rows(1, 1)):
        if cell.value and str(cell.value).strip().upper() == "AFP 2":
            return cell.column
    new_col = ws.max_column + 1
    ws.cell(1, new_col, "AFP 2")
    return new_col


def write_afp(ws: Worksheet, row: int, col: int, value: str) -> None:
    ws.cell(row, col, value)


def to_bytes(wb: Workbook) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Correr tests — deben pasar**

```bash
python -m pytest tests/test_excel.py -v
```

Expected: 8 tests PASS.

- [ ] **Step 5: Correr todos los tests**

```bash
python -m pytest tests/ -v
```

Expected: 16 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/excel.py tests/test_excel.py
git commit -m "feat: add excel module with RUT detection and AFP 2 column writing"
```

---

## Task 4: Streamlit app

**Files:**
- Create: `app.py`

No hay unit tests para la UI — se verifica con smoke test manual en Task 5.

**Interfaces:**
- Consumes:
  - `bot.scraper.query_rut(page: Page, rut: str) -> str`
  - `bot.excel.read_ruts(file_bytes: bytes) -> tuple[Workbook, Worksheet, int, list[int]]`
  - `bot.excel.find_or_create_afp2_column(ws: Worksheet) -> int`
  - `bot.excel.write_afp(ws: Worksheet, row: int, col: int, value: str) -> None`
  - `bot.excel.to_bytes(wb: Workbook) -> bytes`

- [ ] **Step 1: Crear `app.py`**

```python
from playwright.sync_api import sync_playwright
import streamlit as st

from bot.excel import find_or_create_afp2_column, read_ruts, to_bytes, write_afp
from bot.scraper import query_rut

st.set_page_config(page_title="AFP Lookup", page_icon="🔍", layout="centered")

# URL del ejecutable Windows — completar cuando esté disponible
_DOWNLOAD_URL = ""

for key, default in {
    "paso": 0,
    "wb": None,
    "ws": None,
    "rut_col": None,
    "afp2_col": None,
    "data_rows": None,
    "current_idx": 0,
    "resultados": [],
    "excel_bytes": None,
    "pw": None,
    "browser": None,
    "browser_page": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def _barra_pasos(actual: int):
    pasos = ["1. Subir", "2. Procesando", "3. Descargar"]
    cols = st.columns(len(pasos))
    for i, (col, nombre) in enumerate(zip(cols, pasos), start=1):
        if i < actual:
            col.markdown(f"<div style='text-align:center;color:#888'>✓ {nombre}</div>", unsafe_allow_html=True)
        elif i == actual:
            col.markdown(f"<div style='text-align:center;font-weight:bold;color:#7B2FBE'>{nombre}</div>", unsafe_allow_html=True)
        else:
            col.markdown(f"<div style='text-align:center;color:#ccc'>{nombre}</div>", unsafe_allow_html=True)
    st.divider()


# ── PASO 0: Bienvenida / Descarga ────────────────────────────────────────────
def paso_descarga():
    st.markdown("<br>", unsafe_allow_html=True)
    st.title("🔍 AFP Lookup")
    st.markdown(
        "Sube un Excel con RUTs y la app consulta automáticamente en la "
        "Superintendencia de Pensiones qué AFP tiene cada trabajador."
    )
    st.divider()

    col_info, col_cta = st.columns([3, 2])
    with col_info:
        st.markdown("#### ¿Cómo funciona?")
        st.markdown(
            "- Sube el Excel con la columna RUT\n"
            "- La app consulta spensiones.cl uno a uno\n"
            "- Descarga el mismo Excel con la columna **AFP 2** completada"
        )
    with col_cta:
        st.markdown("#### Descarga la app")
        if _DOWNLOAD_URL:
            st.link_button("⬇  Descargar para Windows", _DOWNLOAD_URL,
                           use_container_width=True, type="primary")
        else:
            st.button("⬇  Descargar para Windows", disabled=True,
                      use_container_width=True, type="primary",
                      help="Próximamente disponible")
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if st.button("Continuar en el navegador →", use_container_width=True):
            st.session_state.paso = 1
            st.rerun()


# ── PASO 1: Subir archivo ─────────────────────────────────────────────────────
def paso_subir():
    _barra_pasos(1)
    st.title("📂 Sube el archivo Excel")

    archivo = st.file_uploader("Selecciona el Excel con los RUTs", type=["xlsx"])
    if archivo is None:
        return

    try:
        wb, ws, rut_col, data_rows = read_ruts(archivo.read())
    except ValueError as e:
        st.error(str(e))
        return

    afp2_col = find_or_create_afp2_column(ws)
    st.success(f"✅ {len(data_rows)} RUTs encontrados.")

    if st.button("▶ Iniciar consulta", type="primary", use_container_width=True):
        st.session_state.wb = wb
        st.session_state.ws = ws
        st.session_state.rut_col = rut_col
        st.session_state.afp2_col = afp2_col
        st.session_state.data_rows = data_rows
        st.session_state.current_idx = 0
        st.session_state.resultados = []
        st.session_state.paso = 2
        st.rerun()


# ── PASO 2: Procesando ────────────────────────────────────────────────────────
def paso_procesando():
    _barra_pasos(2)
    st.title("⏳ Consultando RUTs...")

    ws = st.session_state.ws
    rut_col = st.session_state.rut_col
    afp2_col = st.session_state.afp2_col
    data_rows = st.session_state.data_rows
    idx = st.session_state.current_idx
    total = len(data_rows)

    # Abrir browser solo la primera vez
    if st.session_state.browser_page is None:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        st.session_state.pw = pw
        st.session_state.browser = browser
        st.session_state.browser_page = page

    page = st.session_state.browser_page

    # Mostrar progreso
    st.progress(idx / total if total > 0 else 0)
    st.caption(f"{idx} / {total} RUTs consultados")
    secs_restantes = (total - idx) * 2
    if secs_restantes > 0:
        mins, secs = divmod(secs_restantes, 60)
        st.caption(f"Tiempo estimado restante: {mins}m {secs}s")

    if idx < total:
        row = data_rows[idx]
        rut = str(ws.cell(row, rut_col).value)
        afp = query_rut(page, rut)
        write_afp(ws, row, afp2_col, afp)
        st.session_state.current_idx += 1
        st.session_state.resultados.append((rut, afp))
        st.rerun()
    else:
        # Cerrar browser y avanzar
        st.session_state.browser.close()
        st.session_state.pw.stop()
        st.session_state.browser_page = None
        st.session_state.browser = None
        st.session_state.pw = None
        st.session_state.excel_bytes = to_bytes(st.session_state.wb)
        st.session_state.paso = 3
        st.rerun()


# ── PASO 3: Descargar ─────────────────────────────────────────────────────────
def paso_descargar():
    _barra_pasos(3)
    st.title("🎉 ¡Consulta completa!")

    resultados = st.session_state.resultados
    ok = sum(1 for _, a in resultados if a not in ("SIN DATOS", "ERROR"))
    sin_datos = sum(1 for _, a in resultados if a == "SIN DATOS")
    errores = sum(1 for _, a in resultados if a == "ERROR")

    col1, col2, col3 = st.columns(3)
    col1.metric("✅ Encontrados", ok)
    col2.metric("⚠️ Sin datos", sin_datos)
    col3.metric("❌ Errores", errores)

    st.divider()

    st.download_button(
        label="⬇️ Descargar Excel con AFP 2",
        data=st.session_state.excel_bytes,
        file_name="resultado_afp.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
    )

    if st.button("↩ Nueva consulta", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ── Despacho ──────────────────────────────────────────────────────────────────
paso = st.session_state.paso
if paso == 0:
    paso_descarga()
elif paso == 1:
    paso_subir()
elif paso == 2:
    paso_procesando()
elif paso == 3:
    paso_descargar()
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "feat: add Streamlit app with 3-step AFP lookup flow"
```

---

## Task 5: Smoke test manual

- [ ] **Step 1: Correr todos los tests unitarios**

```bash
cd ~/Documents/desarrollo/SuperIntendencia
source .venv/bin/activate
python -m pytest tests/ -v
```

Expected: 16 tests PASS.

- [ ] **Step 2: Lanzar la app**

```bash
streamlit run app.py
```

Expected: app abre en `http://localhost:8501`.

- [ ] **Step 3: Verificar paso 0 (bienvenida)**

- Botón "Descargar para Windows" aparece deshabilitado (gris) — correcto, `_DOWNLOAD_URL` está vacío
- Click en "Continuar en el navegador →" avanza al paso 1

- [ ] **Step 4: Crear Excel de prueba**

Crear un archivo `test_ruts.xlsx` con:
```
| Nombre              | RUT          | AFP |
|---------------------|-------------|-----|
| RODRIGO ESCANILLA   | 15800185-3   |     |
| (otro RUT válido)   | 12345678-9   |     |
```

- [ ] **Step 5: Verificar paso 1 (subir)**

- Subir `test_ruts.xlsx`
- App muestra "✅ 2 RUTs encontrados"
- Click en "▶ Iniciar consulta"

- [ ] **Step 6: Verificar paso 2 (procesando)**

- Barra de progreso avanza de 0/2 a 1/2 a 2/2
- Cada RUT tarda ~2 segundos
- Avanza solo al paso 3 al terminar

- [ ] **Step 7: Verificar paso 3 (descargar)**

- Métricas muestran cuántos encontrados / sin datos / errores
- Click en "⬇️ Descargar Excel con AFP 2"
- Abrir el Excel descargado y verificar que la columna AFP 2 tiene los valores correctos (ej. `HABITAT`)

- [ ] **Step 8: Commit final**

```bash
git add .
git commit -m "feat: complete AFP lookup MVP — scraper, excel, streamlit UI"
```
