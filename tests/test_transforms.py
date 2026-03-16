# tests/test_transforms.py
import pandas as pd

from src.utils.transforms import normalize_rut, parse_date, pick_one_per_rut


def test_normalize_rut_ok():
    assert normalize_rut("12.345.678-9") == "12345678-9"


def test_normalize_rut_with_spaces():
    assert normalize_rut(" 12 345 678 9 ") == "12345678-9"


def test_normalize_rut_invalid():
    assert normalize_rut("") == ""
    assert normalize_rut(None) == ""


def test_parse_date_chilean_format():
    s = pd.Series(["13/03/2026"])
    out = parse_date(s)
    assert str(out.iloc[0].date()) == "2026-03-13"


def test_parse_date_invalid_values():
    s = pd.Series(["", "0000-00-00", "1900-01-01"])
    out = parse_date(s)
    assert pd.isna(out.iloc[0])
    assert pd.isna(out.iloc[1])
    assert pd.isna(out.iloc[2])


def test_pick_one_per_rut_prefers_active_record():
    df = pd.DataFrame({
        "rut_norm": ["12345678-9", "12345678-9"],
        "nombre": ["Alumno X", "Alumno X"],
        "course_code": ["1MA", "1MB"],
        "fecha_retiro": ["2026-03-01", None],
    })

    out = pick_one_per_rut(df, snapshot_date=pd.Timestamp("2026-03-12"))

    assert len(out) == 1
    assert out.iloc[0]["course_code"] == "1MB"


def test_pick_one_per_rut_without_snapshot_prefers_nat():
    df = pd.DataFrame({
        "rut_norm": ["12345678-9", "12345678-9"],
        "nombre": ["Alumno X", "Alumno X"],
        "course_code": ["1MA", "1MB"],
        "fecha_retiro": ["2026-03-01", None],
    })

    out = pick_one_per_rut(df)

    assert len(out) == 1
    assert out.iloc[0]["course_code"] == "1MB"