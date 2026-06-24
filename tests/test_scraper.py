import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.scraper import extract_afp, normalize_rut


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
