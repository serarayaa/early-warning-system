"""
src/utils/transforms.py
=======================
Funciones de transformación compartidas por todo el pipeline EWS.

ANTES: cada módulo tenía su propia copia de normalize_rut, _rut_key,
       _coalesce_duplicates, _parse_date, _pick_one_per_rut, _latest_file, etc.

AHORA: un solo lugar. Si cambia la lógica de RUT → se cambia aquí y punto.

Uso:
    from src.utils.transforms import (
        normalize_rut, rut_key,
        coalesce_duplicates, parse_date,
        normalize_text, pick_one_per_rut,
        latest_snapshot_file,
    )
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


# ──────────────────────────────────────────────
# RUT
# ──────────────────────────────────────────────

def normalize_rut(rut) -> str:
    """
    Normaliza RUT a formato cuerpo-dv (sin puntos, con guion).
    Ej: '12.345.678-9' → '12345678-9'
    Retorna '' si el valor es inválido.
    """
    if rut is None or (isinstance(rut, float) and pd.isna(rut)):
        return ""
    rut = str(rut).upper().strip().replace(".", "").replace(" ", "").replace("-", "")
    if len(rut) < 2:
        return ""
    cuerpo, dv = rut[:-1], rut[-1]
    cuerpo = re.sub(r"\D", "", cuerpo)
    dv = re.sub(r"[^0-9K]", "", dv)
    if not cuerpo or not dv:
        return ""
    return f"{cuerpo}-{dv}"


def rut_key(series: pd.Series) -> pd.Series:
    """
    Clave estándar para comparar/mergear RUTs: solo dígitos + K, sin guion.
    Ej: '12345678-9' → '123456789'
    Útil para joins donde el formato de rut_norm puede variar.
    """
    s = series.fillna("").astype(str).str.strip().str.upper()
    return s.str.replace(r"[^0-9K]", "", regex=True)


# ──────────────────────────────────────────────
# Texto
# ──────────────────────────────────────────────

def normalize_text(x) -> str:
    """
    Normaliza un valor escalar a string limpio (strip + colapso de espacios).
    Para uso en .map() sobre una columna.
    """
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return re.sub(r"\s+", " ", str(x).strip())


def normalize_text_series(series: pd.Series) -> pd.Series:
    """
    Versión vectorizada de normalize_text para aplicar a una Series completa.
    Convierte a mayúsculas, strip y colapsa espacios múltiples.
    """
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
    )


# ──────────────────────────────────────────────
# Fechas
# ──────────────────────────────────────────────

_INVALID_DATES = {"", "0", "0000-00-00", "None", "nan", "NaT"}


def parse_date(series: pd.Series) -> pd.Series:
    """
    Parsea una columna de fechas con tolerancia a valores sucios.
    - Reemplaza strings inválidos con NaT.
    - Considera 1900-01-01 como fecha nula (artefacto frecuente en Syscol).
    - Intenta parsear con dayfirst=True (formato chileno DD/MM/YYYY).
    """
    s = series.fillna("").astype(str).str.strip().replace(_INVALID_DATES, pd.NA)
    dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return dt.mask(dt == pd.Timestamp("1900-01-01"))


def parse_int(series: pd.Series) -> pd.Series:
    """
    Parsea una columna numérica entera con tolerancia a strings sucios.
    Retorna dtype Int64 (nullable).
    """
    # Convertir a object primero para evitar conflicto con Int64 nullable
    s = series.astype(object).fillna("").astype(str).str.strip()
    s = s.replace({"": pd.NA, "None": pd.NA, "nan": pd.NA, "<NA>": pd.NA})
    return pd.to_numeric(s, errors="coerce").astype("Int64")

# ──────────────────────────────────────────────
# DataFrames
# ──────────────────────────────────────────────

def coalesce_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Coalesce de columnas duplicadas (patrón Pandas al leer parquet con merge).
    Ej: 'Nombre', 'Nombre.1', 'Nombre.2' → se quedan con la primera no-nula.
    Frecuente cuando curated snapshot viene de joins sucesivos.
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    groups: dict[str, list[str]] = {}
    for c in df.columns:
        base = c.split(".")[0].strip()
        groups.setdefault(base, []).append(c)

    out = pd.DataFrame(index=df.index)
    for base, cols in groups.items():
        out[base] = df[cols[0]] if len(cols) == 1 else df[cols].bfill(axis=1).iloc[:, 0]
    return out


def pick_one_per_rut(df: pd.DataFrame, snapshot_date: pd.Timestamp | None = None) -> pd.DataFrame:
    """
    Selecciona 1 fila representativa por rut_key.

    Estrategia (en orden de prioridad):
      1. Si hay snapshot_date: activo al corte (fecha_retiro > corte o NaT).
         Dentro de activos, prioriza NaT > fecha_retiro más lejana.
      2. Si no hay snapshot_date (o el RUT no quedó activo):
         elige el registro con fecha_retiro más reciente.

    Requiere columna 'rut_norm'. Agrega 'rut_key' temporalmente y la elimina al final
    si no estaba antes.

    Uso con corte:    pick_one_per_rut(df, snapshot_date=pd.Timestamp("2026-03-04"))
    Uso sin corte:    pick_one_per_rut(df)   ← solo dedupe, activo primero
    """
    df = df.copy()

    had_rut_key = "rut_key" in df.columns

    df["rut_norm"] = df["rut_norm"].fillna("").astype(str).str.strip()
    df["rut_key"] = rut_key(df["rut_norm"])
    df = df[df["rut_key"] != ""].copy()

    has_retiro = "fecha_retiro" in df.columns

    if has_retiro:
        dt = pd.to_datetime(df["fecha_retiro"], errors="coerce", dayfirst=True)
        df["_fecha_sort"] = dt.fillna(pd.Timestamp("1900-01-01"))

        if snapshot_date is not None:
            df["_activo"] = (dt.isna() | (dt > snapshot_date)).astype(int)
        else:
            df["_activo"] = dt.isna().astype(int)

        df["_is_nat"] = dt.isna().astype(int)

        df = df.sort_values(
            ["rut_key", "_activo", "_is_nat", "_fecha_sort"],
            ascending=[True, False, False, False],
        )
        drop_cols = ["_activo", "_is_nat", "_fecha_sort"]
    else:
        df = df.sort_values(["rut_key"], ascending=True)
        drop_cols = []

    out = df.drop_duplicates("rut_key", keep="first")
    out = out.drop(columns=drop_cols, errors="ignore")

    if not had_rut_key:
        out = out.drop(columns=["rut_key"], errors="ignore")

    return out


# ──────────────────────────────────────────────
# Archivos / paths
# ──────────────────────────────────────────────

_TS_RE = re.compile(r"matricula_snapshot_(\d{8})_(\d{6})", re.IGNORECASE)


def latest_snapshot_file(folder: Path, pattern: str) -> Path:
    """
    Retorna el archivo más reciente en `folder` que calce con `pattern`.

    Orden de prioridad:
      1. Archivos con timestamp en el nombre (matricula_snapshot_YYYYMMDD_HHMMSS).
      2. Fallback: mtime del sistema de archivos.

    Lanza FileNotFoundError si no hay archivos que calcen.
    """
    files = list(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos: {folder / pattern}")

    def _sort_key(p: Path):
        m = _TS_RE.search(p.stem)
        if m:
            return (0, m.group(1), m.group(2), 0.0)
        return (1, "99999999", "999999", p.stat().st_mtime)

    return max(files, key=_sort_key)


def ensure_dir(p: Path) -> Path:
    """Crea el directorio si no existe. Retorna el mismo Path."""
    p.mkdir(parents=True, exist_ok=True)
    return p