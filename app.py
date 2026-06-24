from datetime import datetime

from playwright.sync_api import sync_playwright
import streamlit as st

from bot.excel import find_or_create_afp2_column, get_pending_rows, read_ruts, to_bytes, write_afp
from bot.scraper import get_public_ip, normalize_rut, query_rut

st.set_page_config(page_title="AFP Lookup", page_icon="🔍", layout="centered")

_DOWNLOAD_URL = "https://github.com/LuN4t1k0/Superintendencia/releases/download/launcher-latest/AFPLookup.exe"
_BATCH_LIMIT = 90


def _init_state() -> None:
    for key, default in {
        "paso": 0,
        "wb": None,
        "ws": None,
        "rut_col": None,
        "afp2_col": None,
        "data_rows": None,
        "current_idx": 0,
        "batch_size": 3,
        "pause_seconds": 1.5,
        "stop_requested": False,
        "completion_reason": "completed",
        "logs": [],
        "afp_cache": {},
        "cache_hits": 0,
        "remote_queries": 0,
        "resultados": [],
        "excel_bytes": None,
        "pw": None,
        "browser": None,
        "browser_page": None,
        "pending_rows": None,
        "ip_at_start": None,
        "awaiting_ip_change": False,
        "queries_this_ip": 0,
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
    try:
        if browser is not None:
            browser.close()
    except Exception:
        pass
    try:
        if pw is not None:
            pw.stop()
    except Exception:
        pass
    st.session_state.browser_page = None
    st.session_state.browser = None
    st.session_state.pw = None


def _log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"{timestamp} | {message}"
    print(f"[AFP Lookup] {line}", flush=True)
    st.session_state.logs = [*st.session_state.logs, line][-80:]


def _render_logs() -> None:
    logs = st.session_state.get("logs", [])
    if not logs:
        st.caption("Sin eventos registrados todavia.")
        return

    st.text_area(
        "Log de proceso",
        value="\n".join(reversed(logs[-25:])),
        height=240,
        disabled=True,
    )


def _prepare_download(reason: str) -> None:
    _close_browser()
    st.session_state.excel_bytes = to_bytes(st.session_state.wb)
    st.session_state.completion_reason = reason
    st.session_state.paso = 3


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
    pending_rows = get_pending_rows(ws, rut_col, afp2_col, data_rows)
    already_done = len(data_rows) - len(pending_rows)
    unique_ruts = len({normalize_rut(str(ws.cell(row, rut_col).value)) for row in pending_rows})

    if already_done > 0:
        st.info(f"Retomando consulta: {already_done} ya procesados, {len(pending_rows)} pendientes.")
    else:
        st.success(f"{len(data_rows)} filas encontradas.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Total filas", len(data_rows))
    col2.metric("RUTs únicos pendientes", unique_ruts)
    col3.metric("Ya procesados", already_done)

    if unique_ruts > _BATCH_LIMIT:
        batches = (unique_ruts + _BATCH_LIMIT - 1) // _BATCH_LIMIT
        st.warning(
            f"Se necesitan {batches} lotes de {_BATCH_LIMIT} consultas. "
            f"Deberás reiniciar tu router {batches - 1} "
            f"{'vez' if batches == 2 else 'veces'} durante el proceso."
        )

    if not pending_rows:
        st.success("Todos los RUTs ya tienen AFP 2 completado.")
        if st.button("Descargar Excel", type="primary", use_container_width=True):
            st.session_state.wb = wb
            st.session_state.excel_bytes = to_bytes(wb)
            st.session_state.completion_reason = "completed"
            st.session_state.paso = 3
            st.rerun()
        return

    col_lote, col_pausa = st.columns(2)
    with col_lote:
        batch_size = st.number_input(
            "RUTs por ciclo",
            min_value=1,
            max_value=10,
            value=int(st.session_state.batch_size),
            step=1,
        )
    with col_pausa:
        pause_seconds = st.number_input(
            "Pausa entre consultas (s)",
            min_value=0.0,
            max_value=5.0,
            value=float(st.session_state.pause_seconds),
            step=0.25,
            format="%.2f",
        )

    if st.button("Iniciar consulta", type="primary", use_container_width=True):
        st.session_state.wb = wb
        st.session_state.ws = ws
        st.session_state.rut_col = rut_col
        st.session_state.afp2_col = afp2_col
        st.session_state.data_rows = data_rows
        st.session_state.pending_rows = pending_rows
        st.session_state.current_idx = 0
        st.session_state.batch_size = int(batch_size)
        st.session_state.pause_seconds = float(pause_seconds)
        st.session_state.stop_requested = False
        st.session_state.completion_reason = "completed"
        st.session_state.logs = []
        st.session_state.afp_cache = {}
        st.session_state.cache_hits = 0
        st.session_state.remote_queries = 0
        st.session_state.resultados = []
        st.session_state.ip_at_start = None
        st.session_state.awaiting_ip_change = False
        st.session_state.queries_this_ip = 0
        _log(
            f"Iniciando: {len(pending_rows)} filas pendientes, "
            f"{unique_ruts} RUTs únicos, lote {int(batch_size)}, "
            f"pausa {float(pause_seconds):.2f}s"
        )
        st.session_state.paso = 2
        st.rerun()


def _render_waiting_ip() -> None:
    st.markdown("#### Para continuar:")
    st.markdown(
        "1. Reinicia tu router (desconéctalo 30 segundos y vuelve a conectarlo)\n"
        "2. Espera 1-2 minutos a que la conexión se restablezca\n"
        "3. Haz clic en **Verificar nueva IP** — la app continuará automáticamente"
    )
    st.divider()

    ip_anterior = st.session_state.ip_at_start or "desconocida"
    current_ip = get_public_ip()
    processed = st.session_state.current_idx
    total_pending = len(st.session_state.pending_rows or [])

    col1, col2 = st.columns(2)
    col1.metric("IP anterior", ip_anterior)
    col2.metric("IP actual", current_ip or "sin conexión")
    st.caption(f"Progreso guardado: {processed} / {total_pending} filas procesadas.")

    if current_ip and current_ip != ip_anterior:
        st.success("¡Nueva IP detectada! Puedes continuar.")
        if st.button("Continuar procesamiento →", type="primary", use_container_width=True):
            st.session_state.awaiting_ip_change = False
            st.session_state.ip_at_start = current_ip
            st.session_state.queries_this_ip = 0
            _log(f"IP cambiada: {ip_anterior} → {current_ip}. Continuando.")
            st.rerun()
    else:
        col_btn, col_dl = st.columns(2)
        with col_btn:
            if st.button("Verificar nueva IP", use_container_width=True):
                st.rerun()
        with col_dl:
            st.download_button(
                label="Descargar avance",
                data=to_bytes(st.session_state.wb),
                file_name="resultado_afp_parcial.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )


def paso_procesando() -> None:
    _barra_pasos(2)

    if st.session_state.awaiting_ip_change:
        st.title("Límite de consultas alcanzado")
        _render_waiting_ip()
        return

    st.title("Consultando RUTs...")

    ws = st.session_state.ws
    rut_col = st.session_state.rut_col
    afp2_col = st.session_state.afp2_col
    pending_rows = st.session_state.pending_rows or st.session_state.data_rows or []
    idx = st.session_state.current_idx
    total = len(pending_rows)
    batch_size = st.session_state.batch_size
    pause_seconds = st.session_state.pause_seconds
    afp_cache = st.session_state.afp_cache

    if st.session_state.ip_at_start is None:
        ip = get_public_ip()
        st.session_state.ip_at_start = ip
        if ip:
            _log(f"IP detectada: {ip}")

    col_stop, col_download = st.columns(2)
    with col_stop:
        if st.button("Detener proceso", type="secondary", use_container_width=True):
            st.session_state.stop_requested = True
            _log("Detencion solicitada por usuario")
            _prepare_download("stopped")
            st.rerun()
    with col_download:
        st.download_button(
            label="Descargar avance",
            data=to_bytes(st.session_state.wb),
            file_name="resultado_afp_parcial.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    if st.session_state.browser_page is None:
        _log("Abriendo browser headless")
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        st.session_state.pw = pw
        st.session_state.browser = browser
        st.session_state.browser_page = page

    page = st.session_state.browser_page

    st.progress(idx / total if total > 0 else 0)
    st.caption(f"{idx} / {total} filas pendientes procesadas")
    st.caption(
        f"Consultas al sitio: {st.session_state.remote_queries} | "
        f"Reutilizados por cache: {st.session_state.cache_hits} | "
        f"Esta IP: {st.session_state.queries_this_ip}/{_BATCH_LIMIT}"
    )
    secs_restantes = int((total - idx) * (pause_seconds + 1.0))
    if secs_restantes > 0:
        mins, secs = divmod(secs_restantes, 60)
        st.caption(f"Tiempo estimado restante: {mins}m {secs}s")

    if idx < total:
        batch_end = min(idx + batch_size, total)
        st.caption(f"Procesando lote {idx + 1}-{batch_end}")
        _log(f"Procesando lote {idx + 1}-{batch_end} de {total}")
        _render_logs()

        for row in pending_rows[idx:batch_end]:
            if st.session_state.stop_requested:
                _log("Proceso detenido antes de iniciar el siguiente RUT")
                _prepare_download("stopped")
                st.rerun()

            rut = str(ws.cell(row, rut_col).value)
            cache_key = normalize_rut(rut).upper()

            if cache_key in afp_cache:
                afp = afp_cache[cache_key]
                st.session_state.cache_hits += 1
                _log(f"RUT {rut} (fila {row}) reutilizado desde cache: {afp}")
            else:
                if st.session_state.queries_this_ip >= _BATCH_LIMIT:
                    _log(f"Límite de {_BATCH_LIMIT} consultas por IP alcanzado. Pausando.")
                    st.session_state.awaiting_ip_change = True
                    _close_browser()
                    st.rerun()

                _log(f"Consultando RUT {rut} (fila {row})")
                afp = query_rut(
                    page,
                    rut,
                    pause_seconds=pause_seconds,
                    log=lambda msg, rut=rut: _log(f"{rut}: {msg}"),
                )
                st.session_state.remote_queries += 1
                st.session_state.queries_this_ip += 1
                afp_cache[cache_key] = afp

            write_afp(ws, row, afp2_col, afp)
            st.session_state.current_idx += 1
            st.session_state.resultados.append((rut, afp))
            _log(f"RUT {rut} terminado con resultado: {afp}")

        st.rerun()
    else:
        _log("Consulta completa")
        _prepare_download("completed")
        st.rerun()


def paso_descargar() -> None:
    _barra_pasos(3)
    if st.session_state.completion_reason == "stopped":
        st.title("Consulta detenida")
        st.warning("El Excel contiene los RUTs procesados hasta el momento.")
    else:
        st.title("Consulta completa")

    resultados = st.session_state.resultados
    ok = sum(1 for _, afp in resultados if afp not in ("SIN DATOS", "ERROR"))
    sin_datos = sum(1 for _, afp in resultados if afp == "SIN DATOS")
    errores = sum(1 for _, afp in resultados if afp == "ERROR")

    col1, col2, col3 = st.columns(3)
    col1.metric("Encontrados", ok)
    col2.metric("Sin datos", sin_datos)
    col3.metric("Errores", errores)

    col4, col5 = st.columns(2)
    col4.metric("Consultas al sitio", st.session_state.remote_queries)
    col5.metric("Reutilizados por cache", st.session_state.cache_hits)

    st.divider()

    st.download_button(
        label="Descargar Excel con AFP 2",
        data=st.session_state.excel_bytes,
        file_name="resultado_afp.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
    )

    st.divider()
    _render_logs()

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
