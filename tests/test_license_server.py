import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from license_server.server import (
    create_app,
    create_license,
    init_db,
    revoke_license,
    validate_license,
)


def test_validate_license_activa_equipo(tmp_path):
    db_path = tmp_path / "licenses.sqlite3"
    init_db(db_path)
    create_app(db_path, "afp-lookup", "AFP Lookup")
    token = create_license(db_path, "Operaciones", max_devices=1, expires_at=None, app_id="afp-lookup")

    status, payload = validate_license(
        db_path,
        {
            "appId": "afp-lookup",
            "token": token,
            "deviceId": "mac-1",
            "platform": "darwin",
            "appVersion": "0.1.0",
        },
    )

    assert status == 200
    assert payload["valid"] is True
    assert payload["appId"] == "afp-lookup"
    assert payload["label"] == "Operaciones"


def test_validate_license_respeta_limite_de_equipos(tmp_path):
    db_path = tmp_path / "licenses.sqlite3"
    init_db(db_path)
    create_app(db_path, "afp-lookup", "AFP Lookup")
    token = create_license(db_path, "RRHH", max_devices=1, expires_at=None, app_id="afp-lookup")

    first_status, first_payload = validate_license(
        db_path,
        {"appId": "afp-lookup", "token": token, "deviceId": "device-1"},
    )
    second_status, second_payload = validate_license(
        db_path,
        {"appId": "afp-lookup", "token": token, "deviceId": "device-2"},
    )

    assert first_status == 200
    assert first_payload["valid"] is True
    assert second_status == 200
    assert second_payload["valid"] is False
    assert "maximo" in second_payload["message"]


def test_validate_license_revocada(tmp_path):
    db_path = tmp_path / "licenses.sqlite3"
    init_db(db_path)
    create_app(db_path, "afp-lookup", "AFP Lookup")
    token = create_license(db_path, "Finanzas", max_devices=1, expires_at=None, app_id="afp-lookup")

    assert revoke_license(db_path, token, app_id="afp-lookup") is True
    status, payload = validate_license(
        db_path,
        {"appId": "afp-lookup", "token": token, "deviceId": "device-1"},
    )

    assert status == 200
    assert payload["valid"] is False
    assert payload["message"] == "Licencia revocada."


def test_validate_license_no_cruza_apps(tmp_path):
    db_path = tmp_path / "licenses.sqlite3"
    init_db(db_path)
    create_app(db_path, "afp-lookup", "AFP Lookup")
    create_app(db_path, "other-app", "Other App")
    token = create_license(db_path, "AFP", max_devices=1, expires_at=None, app_id="afp-lookup")

    status, payload = validate_license(
        db_path,
        {"appId": "other-app", "token": token, "deviceId": "device-1"},
    )

    assert status == 200
    assert payload["valid"] is False
    assert payload["message"] == "Licencia no existe."
