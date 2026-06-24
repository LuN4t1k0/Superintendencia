import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.scraper import extract_afp, get_public_ip, normalize_rut


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
