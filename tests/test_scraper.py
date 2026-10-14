import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.scraper import extract_afp, format_rut_for_portal, get_public_ip, normalize_rut
from desktop_backend import worker


def test_normalize_rut_con_puntos_y_guion():
    assert normalize_rut("15.800.185-3") == "158001853"


def test_normalize_rut_solo_guion():
    assert normalize_rut("15800185-3") == "158001853"


def test_normalize_rut_ya_limpio():
    assert normalize_rut("158001853") == "158001853"


def test_normalize_rut_strips_espacios():
    assert normalize_rut("  15800185-3  ") == "158001853"


def test_format_rut_for_portal():
    assert format_rut_for_portal("15.800.185-3") == "15800185-3"


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


def test_get_public_ip_retorna_string():
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"1.2.3.4"
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        ip = get_public_ip()
    assert ip == "1.2.3.4"


def test_get_public_ip_retorna_none_en_error():
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        ip = get_public_ip()
    assert ip is None


def test_wait_for_ip_change_reintenta_hasta_detectar_una_nueva(monkeypatch):
    commands = iter(["verify_ip\n", "verify_ip\n"])
    emitted = []

    monkeypatch.setattr(worker.sys.stdin, "readline", lambda: next(commands))
    monkeypatch.setattr(worker, "get_public_ip", MagicMock(side_effect=["1.2.3.4", "5.6.7.8"]))
    monkeypatch.setattr(worker, "emit", lambda event_type, **payload: emitted.append((event_type, payload)))
    monkeypatch.setattr(worker, "STOP_REQUESTED", False)

    assert worker.wait_for_ip_change("1.2.3.4") == "5.6.7.8"
    assert [event_type for event_type, _ in emitted] == ["ip_check", "ip_changed"]


def test_wait_for_ip_change_acepta_ip_si_no_hubo_lectura_inicial(monkeypatch):
    monkeypatch.setattr(worker.sys.stdin, "readline", lambda: "verify_ip\n")
    monkeypatch.setattr(worker, "get_public_ip", lambda: "5.6.7.8")
    monkeypatch.setattr(worker, "emit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(worker, "STOP_REQUESTED", False)

    assert worker.wait_for_ip_change(None) == "5.6.7.8"
