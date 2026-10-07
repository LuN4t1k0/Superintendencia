import argparse
import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:
    psycopg = None
    dict_row = None

DEFAULT_DB = Path(os.environ.get("LICENSE_DB_PATH", Path(__file__).with_name("licenses.sqlite3")))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DEFAULT_HOST = os.environ.get("HOST", "0.0.0.0")
DEFAULT_PORT = int(os.environ.get("PORT", "8787"))
DEFAULT_APP_ID = os.environ.get("DEFAULT_APP_ID", "afp-lookup").strip()
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_app_id(value: str | None) -> str:
    app_id = str(value or DEFAULT_APP_ID or "").strip()
    if not app_id:
        raise ValueError("appId es requerido.")
    return app_id


def is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    return datetime.now(timezone.utc) > expires


class SQLiteStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                create table if not exists apps (
                    id integer primary key autoincrement,
                    app_id text not null unique,
                    name text not null,
                    active integer not null default 1,
                    created_at text not null
                );

                create table if not exists licenses (
                    id integer primary key autoincrement,
                    app_id text not null,
                    token_hash text not null,
                    label text not null,
                    active integer not null default 1,
                    max_devices integer not null default 1,
                    expires_at text,
                    created_at text not null,
                    unique (app_id, token_hash),
                    foreign key (app_id) references apps(app_id)
                );

                create table if not exists activations (
                    id integer primary key autoincrement,
                    license_id integer not null,
                    device_id text not null,
                    platform text,
                    app_version text,
                    first_seen_at text not null,
                    last_seen_at text not null,
                    unique (license_id, device_id),
                    foreign key (license_id) references licenses(id)
                );
                """
            )

    def upsert_app(self, app_id: str, name: str | None = None) -> dict:
        app_id = normalize_app_id(app_id)
        name = str(name or app_id).strip()
        with self.connect() as conn:
            conn.execute(
                """
                insert into apps (app_id, name, active, created_at)
                values (?, ?, 1, ?)
                on conflict(app_id) do update set name = excluded.name
                """,
                (app_id, name, utc_now()),
            )
            row = conn.execute("select * from apps where app_id = ?", (app_id,)).fetchone()
        return dict(row)

    def list_apps(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("select * from apps order by app_id").fetchall()
        return [dict(row) for row in rows]

    def create_license(
        self,
        app_id: str,
        label: str,
        max_devices: int,
        expires_at: str | None,
    ) -> str:
        app_id = normalize_app_id(app_id)
        token = f"lic_{secrets.token_urlsafe(32)}"
        self.upsert_app(app_id)
        with self.connect() as conn:
            conn.execute(
                """
                insert into licenses
                    (app_id, token_hash, label, max_devices, expires_at, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (app_id, hash_token(token), label, max_devices, expires_at, utc_now()),
            )
        return token

    def revoke_license(self, token: str, app_id: str | None = None) -> bool:
        params: list[object] = [hash_token(token)]
        clause = "token_hash = ?"
        if app_id:
            clause += " and app_id = ?"
            params.append(normalize_app_id(app_id))
        with self.connect() as conn:
            cur = conn.execute(f"update licenses set active = 0 where {clause}", params)
            return cur.rowcount > 0

    def list_licenses(self, app_id: str | None = None) -> list[dict]:
        params: list[object] = []
        where = ""
        if app_id:
            where = "where l.app_id = ?"
            params.append(normalize_app_id(app_id))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select
                    l.id,
                    l.app_id as appId,
                    l.label,
                    l.active,
                    l.max_devices as maxDevices,
                    l.expires_at as expiresAt,
                    l.created_at as createdAt,
                    count(a.id) as devices
                from licenses l
                left join activations a on a.license_id = l.id
                {where}
                group by l.id
                order by l.created_at desc
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def validate_license(self, payload: dict) -> tuple[int, dict]:
        app_id = normalize_app_id(payload.get("appId") or payload.get("app_id"))
        token = str(payload.get("token") or "").strip()
        device_id = str(payload.get("deviceId") or "").strip()
        platform = str(payload.get("platform") or "").strip()
        app_version = str(payload.get("appVersion") or "").strip()

        if not token or not device_id:
            return 400, {"valid": False, "message": "Token y deviceId son requeridos."}

        with self.connect() as conn:
            app = conn.execute("select * from apps where app_id = ?", (app_id,)).fetchone()
            if not app or not app["active"]:
                return 200, {"valid": False, "message": "Aplicacion no autorizada."}

            license_row = conn.execute(
                "select * from licenses where app_id = ? and token_hash = ?",
                (app_id, hash_token(token)),
            ).fetchone()

            if not license_row:
                return 200, {"valid": False, "message": "Licencia no existe."}
            if not license_row["active"]:
                return 200, {"valid": False, "message": "Licencia revocada."}
            if is_expired(license_row["expires_at"]):
                return 200, {"valid": False, "message": "Licencia expirada."}

            activation = conn.execute(
                "select * from activations where license_id = ? and device_id = ?",
                (license_row["id"], device_id),
            ).fetchone()

            devices = conn.execute(
                "select count(*) as total from activations where license_id = ?",
                (license_row["id"],),
            ).fetchone()["total"]

            if not activation and devices >= license_row["max_devices"]:
                return 200, {
                    "valid": False,
                    "message": "Licencia alcanzo el maximo de equipos autorizados.",
                }

            now = utc_now()
            if activation:
                conn.execute(
                    """
                    update activations
                    set platform = ?, app_version = ?, last_seen_at = ?
                    where id = ?
                    """,
                    (platform, app_version, now, activation["id"]),
                )
            else:
                conn.execute(
                    """
                    insert into activations
                        (license_id, device_id, platform, app_version, first_seen_at, last_seen_at)
                    values (?, ?, ?, ?, ?, ?)
                    """,
                    (license_row["id"], device_id, platform, app_version, now, now),
                )

        return 200, {
            "valid": True,
            "appId": app_id,
            "label": license_row["label"],
            "expiresAt": license_row["expires_at"],
            "maxDevices": license_row["max_devices"],
        }


class PostgresStore(SQLiteStore):
    def __init__(self, database_url: str):
        if psycopg is None:
            raise RuntimeError("psycopg no esta instalado.")
        self.database_url = database_url

    @contextmanager
    def connect(self):
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            yield conn
            conn.commit()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                create table if not exists apps (
                    id bigserial primary key,
                    app_id text not null unique,
                    name text not null,
                    active boolean not null default true,
                    created_at timestamptz not null
                );

                create table if not exists licenses (
                    id bigserial primary key,
                    app_id text not null references apps(app_id),
                    token_hash text not null,
                    label text not null,
                    active boolean not null default true,
                    max_devices integer not null default 1,
                    expires_at timestamptz,
                    created_at timestamptz not null,
                    unique (app_id, token_hash)
                );

                create table if not exists activations (
                    id bigserial primary key,
                    license_id bigint not null references licenses(id),
                    device_id text not null,
                    platform text,
                    app_version text,
                    first_seen_at timestamptz not null,
                    last_seen_at timestamptz not null,
                    unique (license_id, device_id)
                );
                """
            )

    def upsert_app(self, app_id: str, name: str | None = None) -> dict:
        app_id = normalize_app_id(app_id)
        name = str(name or app_id).strip()
        with self.connect() as conn:
            conn.execute(
                """
                insert into apps (app_id, name, active, created_at)
                values (%s, %s, true, %s)
                on conflict(app_id) do update set name = excluded.name
                """,
                (app_id, name, utc_now()),
            )
            row = conn.execute("select * from apps where app_id = %s", (app_id,)).fetchone()
        return dict(row)

    def list_apps(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("select * from apps order by app_id").fetchall()
        return [dict(row) for row in rows]

    def create_license(
        self,
        app_id: str,
        label: str,
        max_devices: int,
        expires_at: str | None,
    ) -> str:
        app_id = normalize_app_id(app_id)
        token = f"lic_{secrets.token_urlsafe(32)}"
        self.upsert_app(app_id)
        with self.connect() as conn:
            conn.execute(
                """
                insert into licenses
                    (app_id, token_hash, label, max_devices, expires_at, created_at)
                values (%s, %s, %s, %s, %s, %s)
                """,
                (app_id, hash_token(token), label, max_devices, expires_at, utc_now()),
            )
        return token

    def revoke_license(self, token: str, app_id: str | None = None) -> bool:
        params: list[object] = [hash_token(token)]
        clause = "token_hash = %s"
        if app_id:
            clause += " and app_id = %s"
            params.append(normalize_app_id(app_id))
        with self.connect() as conn:
            cur = conn.execute(f"update licenses set active = false where {clause}", params)
            return cur.rowcount > 0

    def list_licenses(self, app_id: str | None = None) -> list[dict]:
        params: list[object] = []
        where = ""
        if app_id:
            where = "where l.app_id = %s"
            params.append(normalize_app_id(app_id))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select
                    l.id,
                    l.app_id as "appId",
                    l.label,
                    l.active,
                    l.max_devices as "maxDevices",
                    l.expires_at as "expiresAt",
                    l.created_at as "createdAt",
                    count(a.id) as devices
                from licenses l
                left join activations a on a.license_id = l.id
                {where}
                group by l.id
                order by l.created_at desc
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def validate_license(self, payload: dict) -> tuple[int, dict]:
        app_id = normalize_app_id(payload.get("appId") or payload.get("app_id"))
        token = str(payload.get("token") or "").strip()
        device_id = str(payload.get("deviceId") or "").strip()
        platform = str(payload.get("platform") or "").strip()
        app_version = str(payload.get("appVersion") or "").strip()

        if not token or not device_id:
            return 400, {"valid": False, "message": "Token y deviceId son requeridos."}

        with self.connect() as conn:
            app = conn.execute("select * from apps where app_id = %s", (app_id,)).fetchone()
            if not app or not app["active"]:
                return 200, {"valid": False, "message": "Aplicacion no autorizada."}

            license_row = conn.execute(
                "select * from licenses where app_id = %s and token_hash = %s",
                (app_id, hash_token(token)),
            ).fetchone()

            if not license_row:
                return 200, {"valid": False, "message": "Licencia no existe."}
            if not license_row["active"]:
                return 200, {"valid": False, "message": "Licencia revocada."}
            expires_at = license_row["expires_at"].isoformat() if license_row["expires_at"] else None
            if is_expired(expires_at):
                return 200, {"valid": False, "message": "Licencia expirada."}

            activation = conn.execute(
                "select * from activations where license_id = %s and device_id = %s",
                (license_row["id"], device_id),
            ).fetchone()

            devices = conn.execute(
                "select count(*) as total from activations where license_id = %s",
                (license_row["id"],),
            ).fetchone()["total"]

            if not activation and devices >= license_row["max_devices"]:
                return 200, {
                    "valid": False,
                    "message": "Licencia alcanzo el maximo de equipos autorizados.",
                }

            now = utc_now()
            if activation:
                conn.execute(
                    """
                    update activations
                    set platform = %s, app_version = %s, last_seen_at = %s
                    where id = %s
                    """,
                    (platform, app_version, now, activation["id"]),
                )
            else:
                conn.execute(
                    """
                    insert into activations
                        (license_id, device_id, platform, app_version, first_seen_at, last_seen_at)
                    values (%s, %s, %s, %s, %s, %s)
                    """,
                    (license_row["id"], device_id, platform, app_version, now, now),
                )

        return 200, {
            "valid": True,
            "appId": app_id,
            "label": license_row["label"],
            "expiresAt": expires_at,
            "maxDevices": license_row["max_devices"],
        }


def make_store(db_path: Path | None = None):
    if DATABASE_URL:
        return PostgresStore(DATABASE_URL)
    return SQLiteStore(Path(db_path or DEFAULT_DB))


def init_db(db_path: Path) -> None:
    make_store(db_path).init_db()


def create_app(db_path: Path, app_id: str, name: str | None = None) -> dict:
    store = make_store(db_path)
    store.init_db()
    return store.upsert_app(app_id, name)


def create_license(
    db_path: Path,
    label: str,
    max_devices: int,
    expires_at: str | None,
    app_id: str | None = None,
) -> str:
    store = make_store(db_path)
    store.init_db()
    return store.create_license(normalize_app_id(app_id), label, max_devices, expires_at)


def revoke_license(db_path: Path, token: str, app_id: str | None = None) -> bool:
    store = make_store(db_path)
    store.init_db()
    return store.revoke_license(token, app_id)


def list_licenses(db_path: Path, app_id: str | None = None) -> list[dict]:
    store = make_store(db_path)
    store.init_db()
    return store.list_licenses(app_id)


def validate_license(db_path: Path, payload: dict) -> tuple[int, dict]:
    store = make_store(db_path)
    store.init_db()
    return store.validate_license(payload)


class LicenseHandler(BaseHTTPRequestHandler):
    store = make_store()

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def _send_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _is_admin_request(self) -> bool:
        if not ADMIN_TOKEN:
            return False
        auth = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not auth.startswith(prefix):
            return False
        return secrets.compare_digest(auth[len(prefix):].strip(), ADMIN_TOKEN)

    def _require_admin(self) -> bool:
        if self._is_admin_request():
            return True
        self._send_json(401, {"error": "Unauthorized"})
        return False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/healthz":
                self._send_json(200, {"ok": True})
                return

            if parsed.path == "/admin/apps":
                if not self._require_admin():
                    return
                self._send_json(200, {"apps": self.store.list_apps()})
                return

            if parsed.path == "/admin/licenses":
                if not self._require_admin():
                    return
                app_id = (query.get("appId") or query.get("app_id") or [None])[0]
                self._send_json(200, {"licenses": self.store.list_licenses(app_id)})
                return

            self._send_json(404, {"error": "Not found"})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def do_POST(self) -> None:
        try:
            if self.path == "/licenses/validate":
                status, response = self.store.validate_license(self._read_json())
                self._send_json(status, response)
                return

            if self.path == "/admin/apps":
                if not self._require_admin():
                    return
                payload = self._read_json()
                app_id = normalize_app_id(payload.get("appId") or payload.get("app_id"))
                name = str(payload.get("name") or app_id).strip()
                self._send_json(201, {"app": self.store.upsert_app(app_id, name)})
                return

            if self.path == "/admin/licenses":
                if not self._require_admin():
                    return
                payload = self._read_json()
                app_id = normalize_app_id(payload.get("appId") or payload.get("app_id"))
                label = str(payload.get("label") or "").strip()
                max_devices = int(payload.get("maxDevices") or payload.get("max_devices") or 1)
                expires_at = payload.get("expiresAt") or payload.get("expires_at")
                if not label:
                    self._send_json(400, {"error": "label es requerido"})
                    return
                token = self.store.create_license(app_id, label, max_devices, expires_at)
                self._send_json(201, {"token": token, "appId": app_id})
                return

            if self.path == "/admin/licenses/revoke":
                if not self._require_admin():
                    return
                payload = self._read_json()
                token = str(payload.get("token") or "").strip()
                app_id = payload.get("appId") or payload.get("app_id")
                if not token:
                    self._send_json(400, {"error": "token es requerido"})
                    return
                self._send_json(200, {"revoked": self.store.revoke_license(token, app_id)})
                return

            self._send_json(404, {"error": "Not found"})
        except Exception as exc:
            self._send_json(500, {"valid": False, "message": str(exc)})

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def serve(db_path: Path, host: str, port: int) -> None:
    store = make_store(db_path)
    store.init_db()
    LicenseHandler.store = store
    server = ThreadingHTTPServer((host, port), LicenseHandler)
    print(f"Servidor de licencias escuchando en http://{host}:{port}")
    server.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")

    app_parser = sub.add_parser("app")
    app_parser.add_argument("--app-id", required=True)
    app_parser.add_argument("--name")

    create = sub.add_parser("create")
    create.add_argument("--app-id", default=DEFAULT_APP_ID)
    create.add_argument("--label", required=True)
    create.add_argument("--max-devices", type=int, default=1)
    create.add_argument("--expires-at")

    revoke = sub.add_parser("revoke")
    revoke.add_argument("--app-id")
    revoke.add_argument("--token", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--app-id")

    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default=DEFAULT_HOST)
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    store = make_store(db_path)
    store.init_db()

    if args.command == "init":
        print(f"Base inicializada: {DATABASE_URL or db_path}")
    elif args.command == "app":
        print(json.dumps(store.upsert_app(args.app_id, args.name), indent=2, ensure_ascii=False, default=str))
    elif args.command == "create":
        print(store.create_license(args.app_id, args.label, args.max_devices, args.expires_at))
    elif args.command == "revoke":
        print("revoked" if store.revoke_license(args.token, args.app_id) else "not-found")
    elif args.command == "list":
        print(json.dumps(store.list_licenses(args.app_id), indent=2, ensure_ascii=False, default=str))
    elif args.command == "serve":
        serve(db_path, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
