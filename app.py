from playwright.sync_api import sync_playwright
import streamlit as st

from bot.excel import find_or_create_afp2_column, read_ruts, to_bytes, write_afp
from bot.scraper import query_rut

st.set_page_config(page_title="AFP Lookup", page_icon="🔍", layout="centered")

_DOWNLOAD_URL = ""


def _init_state() -> None:
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


def _barra_pasos(actual: int) -> None:
    pasos = ["1. Subir", "2. Procesando", "3. Descargar"]
    cols = st.columns(len(pasos))
    for i, (col, nombre) in enumerate(zip(cols, pasos), start=1):
        if i < actual:
            col.markdown(
                f"<div style='text-align:center;color:#888'>✓ {nombre}</div>",
                unsafe_allow_html=True,
            )
        elif i == actual:
            col.markdown(
                f"<div style='text-align:center;font-weight:bold;color:#7B2FBE'>{nombre}</div>",
                unsafe_allow_html=True,
            )
        else:
            col.markdown(
                f"<div style='text-align:center;color:#ccc'>{nombre}</div>",
                unsafe_allow_html=True,
            )
    st.divider()


def _close_browser() -> None:
    browser = st.session_state.get("browser")
    pw = st.session_state.get("pw")

    if browser is not None:
        browser.close()
    if pw is not None:
        pw.stop()

    st.session_state.browser_page = None
    st.session_state.browser = None
    st.session_state.pw = None


def paso_descarga() -> None:
    st.markdown("<br>", unsafe_allow_html=True)
    st.title("🔍 AFP Lookup")
    st.markdown(
        "Sube un Excel con RUTs y la app consulta automaticamente en la "
        "Superintendencia de Pensiones que AFP tiene cada trabajador."
    )
    st.divider()

    col_info, col_cta = st.columns([3, 2])
    with col_info:
        st.markdown("#### Como funciona")
        st.markdown(
            "- Sube el Excel con la columna RUT\n"
            "- La app consulta spensiones.cl uno a uno\n"
            "- Descarga el mismo Excel con la columna **AFP 2** completada"
        )
    with col_cta:
        st.markdown("#### Descarga la app")
        if _DOWNLOAD_URL:
            st.link_button(
                "Descargar para Windows",
                _DOWNLOAD_URL,
                use_container_width=True,
                type="primary",
            )
        else:
            st.button(
                "Descargar para Windows",
                disabled=True,
                use_container_width=True,
                type="primary",
                help="Proximamente disponible",
            )
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if st.button("Continuar en el navegador", use_container_width=True):
            st.session_state.paso = 1
            st.rerun()


def paso_subir() -> None:
    _barra_pasos(1)
    st.title("Sube el archivo Excel")

    archivo = st.file_uploader("Selecciona el Excel con los RUTs", type=["xlsx"])
    if archivo is None:
        return

    try:
        wb, ws, rut_col, data_rows = read_ruts(archivo.read())
    except ValueError as exc:
        st.error(str(exc))
        return

    afp2_col = find_or_create_afp2_column(ws)
    st.success(f"{len(data_rows)} RUTs encontrados.")

    if st.button("Iniciar consulta", type="primary", use_container_width=True):
        st.session_state.wb = wb
        st.session_state.ws = ws
        st.session_state.rut_col = rut_col
        st.session_state.afp2_col = afp2_col
        st.session_state.data_rows = data_rows
        st.session_state.current_idx = 0
        st.session_state.resultados = []
        st.session_state.paso = 2
        st.rerun()


def paso_procesando() -> None:
    _barra_pasos(2)
    st.title("Consultando RUTs...")

    ws = st.session_state.ws
    rut_col = st.session_state.rut_col
    afp2_col = st.session_state.afp2_col
    data_rows = st.session_state.data_rows or []
    idx = st.session_state.current_idx
    total = len(data_rows)

    if st.session_state.browser_page is None:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        st.session_state.pw = pw
        st.session_state.browser = browser
        st.session_state.browser_page = page

    page = st.session_state.browser_page

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
        _close_browser()
        st.session_state.excel_bytes = to_bytes(st.session_state.wb)
        st.session_state.paso = 3
        st.rerun()


def paso_descargar() -> None:
    _barra_pasos(3)
    st.title("Consulta completa")

    resultados = st.session_state.resultados
    ok = sum(1 for _, afp in resultados if afp not in ("SIN DATOS", "ERROR"))
    sin_datos = sum(1 for _, afp in resultados if afp == "SIN DATOS")
    errores = sum(1 for _, afp in resultados if afp == "ERROR")

    col1, col2, col3 = st.columns(3)
    col1.metric("Encontrados", ok)
    col2.metric("Sin datos", sin_datos)
    col3.metric("Errores", errores)

    st.divider()

    st.download_button(
        label="Descargar Excel con AFP 2",
        data=st.session_state.excel_bytes,
        file_name="resultado_afp.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
    )

    if st.button("Nueva consulta", use_container_width=True):
        _close_browser()
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


_init_state()

paso = st.session_state.paso
if paso == 0:
    paso_descarga()
elif paso == 1:
    paso_subir()
elif paso == 2:
    paso_procesando()
elif paso == 3:
    paso_descargar()
