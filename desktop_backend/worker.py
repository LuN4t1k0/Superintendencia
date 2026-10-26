import argparse
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.excel import find_or_create_afp2_column, get_pending_rows, read_ruts, to_afp2_zip_bytes, to_bytes, write_afp
from bot.scraper import PortalBlockedError, get_public_ip, normalize_rut, query_rut

SOFT_CHECKPOINT_INTERVAL = 90
CHECKPOINT_PAUSE_INCREMENT = 0.5
MAX_PAUSE_SECONDS = 5.0
BLOCK_RETRY_DELAYS = (30, 60)
MAX_CONSECUTIVE_ERRORS = 3
STOP_REQUESTED = False


def emit(event_type: str, **payload) -> None:
    print(json.dumps({"type": event_type, **payload}, ensure_ascii=False), flush=True)


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    emit("log", message=f"{timestamp} | {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--pause-seconds", type=float, default=1.5)
    return parser.parse_args()


def request_stop(_signum, _frame) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def save_output(wb, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(
        to_afp2_zip_bytes(wb) if output_path.suffix.lower() == ".zip" else to_bytes(wb)
    )


def adaptive_pause_seconds(base_pause: float, remote_queries: int) -> float:
    """Increase the pause after each soft checkpoint without forcing an IP change."""
    checkpoints = max(0, remote_queries // SOFT_CHECKPOINT_INTERVAL)
    return min(MAX_PAUSE_SECONDS, base_pause + checkpoints * CHECKPOINT_PAUSE_INCREMENT)


def wait_interruptibly(seconds: float) -> bool:
    """Wait for a cooldown while still honoring stop signals."""
    deadline = time.monotonic() + max(0.0, seconds)
    while not STOP_REQUESTED and time.monotonic() < deadline:
        time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
    return not STOP_REQUESTED


def wait_for_ip_change(previous_ip: str | None) -> str | None:
    """Wait for renderer verification requests until a new public IP is available."""
    while not STOP_REQUESTED:
        command = sys.stdin.readline()
        if not command:
            return None
        if command.strip() != "verify_ip":
            continue

        current_ip = get_public_ip()
        if not current_ip:
            emit(
                "ip_check",
                changed=False,
                currentIp=None,
                message="No se pudo detectar la IP publica. Revisa la conexion e intenta nuevamente.",
            )
            continue

        if previous_ip and current_ip == previous_ip:
            emit(
                "ip_check",
                changed=False,
                currentIp=current_ip,
                message="La IP publica todavia no ha cambiado. Reinicia el router e intenta nuevamente.",
            )
            continue

        emit(
            "ip_changed",
            previousIp=previous_ip,
            currentIp=current_ip,
            message="Nueva IP detectada. Continuando automaticamente.",
        )
        return current_ip

    return None


def main() -> int:
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    batch_size = max(1, min(10, args.batch_size))
    pause_seconds = max(0.0, min(5.0, args.pause_seconds))

    try:
        wb, ws, rut_col, data_rows = read_ruts(input_path.read_bytes())
        afp2_col = find_or_create_afp2_column(ws)
        pending_rows = get_pending_rows(ws, rut_col, afp2_col, data_rows)
    except Exception as exc:
        emit("error", message=str(exc))
        return 1

    emit("ready", totalRows=len(data_rows), pendingRows=len(pending_rows))
    if not pending_rows:
        save_output(wb, output_path)
        emit("done", outputPath=str(output_path))
        return 0

    afp_cache = {}
    stats = {
        "found": 0,
        "empty": 0,
        "errors": 0,
        "cacheHits": 0,
        "remoteQueries": 0,
    }
    consecutive_errors = 0
    queries_this_ip = 0
    current_ip = get_public_ip()
    if current_ip:
        log(f"IP detectada: {current_ip}")

    pw = None
    browser = None
    try:
        log("Abriendo navegador interno")
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        processed = 0
        for batch_start in range(0, len(pending_rows), batch_size):
            batch = pending_rows[batch_start : batch_start + batch_size]
            log(f"Procesando lote {batch_start + 1}-{batch_start + len(batch)} de {len(pending_rows)}")

            for row in batch:
                if STOP_REQUESTED:
                    save_output(wb, output_path)
                    emit("canceled", outputPath=str(output_path))
                    return 0

                rut = str(ws.cell(row, rut_col).value)
                cache_key = normalize_rut(rut).upper()
                made_remote_query = False

                if cache_key in afp_cache:
                    afp = afp_cache[cache_key]
                    stats["cacheHits"] += 1
                    log(f"RUT {rut} reutilizado desde cache: {afp}")
                else:
                    block_retries = 0
                    while True:
                        effective_pause = adaptive_pause_seconds(pause_seconds, queries_this_ip)
                        log(f"Consultando RUT {rut}")
                        stats["remoteQueries"] += 1
                        queries_this_ip += 1
                        made_remote_query = True
                        try:
                            afp = query_rut(
                                page,
                                rut,
                                pause_seconds=effective_pause,
                                log=lambda msg, rut=rut: log(f"{rut}: {msg}"),
                            )
                            break
                        except PortalBlockedError as exc:
                            save_output(wb, output_path)
                            reason = str(exc)

                            if block_retries < len(BLOCK_RETRY_DELAYS):
                                wait_seconds = BLOCK_RETRY_DELAYS[block_retries]
                                block_retries += 1
                                log(
                                    f"Señal de bloqueo detectada. Pausa preventiva de "
                                    f"{wait_seconds} segundos antes de una consulta de verificacion."
                                )
                                emit(
                                    "cooldown",
                                    outputPath=str(output_path),
                                    reason=reason,
                                    waitSeconds=wait_seconds,
                                    attempt=block_retries,
                                    maxAttempts=len(BLOCK_RETRY_DELAYS),
                                )
                                if not wait_interruptibly(wait_seconds):
                                    save_output(wb, output_path)
                                    emit("canceled", outputPath=str(output_path))
                                    return 0
                                continue

                            log("El bloqueo persistio despues de las pausas. Esperando nueva IP.")
                            emit(
                                "portal_blocked",
                                outputPath=str(output_path),
                                previousIp=current_ip,
                                processed=processed,
                                pendingRows=len(pending_rows),
                                reason=reason,
                            )
                            if browser is not None:
                                browser.close()
                                browser = None

                            new_ip = wait_for_ip_change(current_ip)
                            if new_ip is None:
                                save_output(wb, output_path)
                                emit("canceled", outputPath=str(output_path))
                                return 0

                            current_ip = new_ip
                            queries_this_ip = 0
                            block_retries = 0
                            consecutive_errors = 0
                            log(f"IP cambiada. Reanudando desde la fila pendiente {processed + 1}.")
                            browser = pw.chromium.launch(headless=True)
                            page = browser.new_page()

                    afp_cache[cache_key] = afp

                if afp == "ERROR":
                    stats["errors"] += 1
                    consecutive_errors += 1
                elif afp == "SIN DATOS":
                    stats["empty"] += 1
                    consecutive_errors = 0
                else:
                    stats["found"] += 1
                    consecutive_errors = 0

                write_afp(ws, row, afp2_col, afp)
                processed += 1
                emit(
                    "progress",
                    rut=rut,
                    processed=processed,
                    pendingRows=len(pending_rows),
                    **stats,
                )

                if (
                    made_remote_query
                    and queries_this_ip > 0
                    and queries_this_ip % SOFT_CHECKPOINT_INTERVAL == 0
                ):
                    save_output(wb, output_path)
                    next_pause = adaptive_pause_seconds(pause_seconds, queries_this_ip)
                    log(
                        f"Punto de control: {queries_this_ip} consultas con esta IP, "
                        f"sin bloqueo. Continuando con pausa de {next_pause:.2f}s."
                    )
                    emit(
                        "checkpoint",
                        outputPath=str(output_path),
                        queriesThisIp=queries_this_ip,
                        pauseSeconds=next_pause,
                    )

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    save_output(wb, output_path)
                    emit(
                        "blocked",
                        outputPath=str(output_path),
                        message=(
                            "El portal acumulo varias consultas fallidas seguidas. "
                            "Se guardo el avance para evitar marcar todo el archivo como ERROR."
                        ),
                    )
                    return 0

        save_output(wb, output_path)
        emit("done", outputPath=str(output_path))
        return 0
    except Exception as exc:
        emit("error", message=str(exc))
        return 1
    finally:
        try:
            if browser is not None:
                browser.close()
        finally:
            if pw is not None:
                pw.stop()


if __name__ == "__main__":
    raise SystemExit(main())
