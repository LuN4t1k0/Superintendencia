import argparse
import json
import signal
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.excel import find_or_create_afp2_column, get_pending_rows, read_ruts, to_bytes, write_afp
from bot.scraper import get_public_ip, normalize_rut, query_rut

BATCH_LIMIT = 90
MAX_CONSECUTIVE_ERRORS = 5
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
    output_path.write_bytes(to_bytes(wb))


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

                if queries_this_ip >= BATCH_LIMIT:
                    save_output(wb, output_path)
                    emit("ip_limit", outputPath=str(output_path))
                    return 0

                rut = str(ws.cell(row, rut_col).value)
                cache_key = normalize_rut(rut).upper()

                if cache_key in afp_cache:
                    afp = afp_cache[cache_key]
                    stats["cacheHits"] += 1
                    log(f"RUT {rut} reutilizado desde cache: {afp}")
                else:
                    log(f"Consultando RUT {rut}")
                    afp = query_rut(
                        page,
                        rut,
                        pause_seconds=pause_seconds,
                        log=lambda msg, rut=rut: log(f"{rut}: {msg}"),
                    )
                    stats["remoteQueries"] += 1
                    queries_this_ip += 1
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
