from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config.settings import PATHS, SPECIALTY_BY_SECTION
from src.utils.logging_utils import get_logger
from src.utils.transforms import (
    normalize_rut,
    normalize_text,
    parse_date,
    parse_int,
    ensure_dir,
)

log = get_logger("EWS.stg_matricula")

ALLOWED_EXTS = {".csv", ".xlsx", ".xls"}


# ---------------------------------------------------------------------
# Helpers locales (específicos de este módulo, NO son duplicados)
# ---------------------------------------------------------------------

def derive_level(course_code: str) -> int | None:
    if not course_code:
        return None
    m = re.match(r"^(\d)", str(course_code).strip())
    return int(m.group(1)) if m else None


def derive_section_letter(course_code: str) -> str | None:
    if not course_code:
        return None
    cc = str(course_code).strip().upper()
    return cc[-1] if cc else None


def derive_specialty(course_code: str) -> str:
    letter = derive_section_letter(course_code)
    if not letter:
        return "COMUN"
    return SPECIALTY_BY_SECTION.get(letter, "COMUN")


def _read_csv_robust(file_path: Path) -> pd.DataFrame:
    encodings = ["utf-8", "latin1", "cp1252"]
    last_err: Exception | None = None
    for enc in encodings:
        try:
            log.info(f"🔎 Intentando leer CSV con encoding={enc}")
            return pd.read_csv(file_path, dtype=str, encoding=enc, sep=None, engine="python")
        except (UnicodeDecodeError, pd.errors.ParserError) as e:
            last_err = e
            continue
    raise ValueError(f"No se pudo leer el CSV con encodings {encodings}. Error: {last_err}")


def _read_excel(file_path: Path) -> pd.DataFrame:
    log.info("🔎 Leyendo Excel (matrícula)")
    return pd.read_excel(file_path, dtype=str)


def _read_input(file_path: Path) -> pd.DataFrame:
    ext = file_path.suffix.lower()
    if ext == ".csv":
        return _read_csv_robust(file_path)
    if ext in {".xlsx", ".xls"}:
        return _read_excel(file_path)
    raise ValueError(f"Extensión no soportada: {ext}")


def _pick_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    cols = list(df.columns)
    lower_map = {str(c).strip().lower(): c for c in cols}
    for cand in candidates:
        key = cand.strip().lower()
        if key in lower_map:
            return lower_map[key]
    for cand in candidates:
        key = cand.strip().lower()
        for c in cols:
            if key in str(c).strip().lower():
                return c
    return None


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def build_staging(snapshot_file: Path, out_dir: Path | None = None) -> Path:
    if not snapshot_file.exists():
        raise FileNotFoundError(f"No existe snapshot: {snapshot_file}")
    if snapshot_file.suffix.lower() not in ALLOWED_EXTS:
        raise ValueError(f"Extensión no soportada: {snapshot_file.suffix}. Permitidas: {sorted(ALLOWED_EXTS)}")

    if out_dir is None:
        out_dir = PATHS.staging / "matricula"
    ensure_dir(out_dir)

    log.info(f"📥 Leyendo snapshot raw: {snapshot_file.name}")
    df = _read_input(snapshot_file)
    df.columns = [str(c).strip() for c in df.columns]

    col_rut      = _pick_col(df, ["Número Rut", "Numero Rut", "Rut", "RUT", "N° Rut"])
    col_nombre   = _pick_col(df, ["Nombre", "Nombres Alumno", "Alumno", "Estudiante"])
    col_comuna   = _pick_col(df, ["Comuna"])
    col_curso    = _pick_col(df, ["Código Curso", "Codigo Curso", "CCurso", "Curso"])
    col_rep      = _pick_col(df, ["Repitente"])
    col_retiro   = _pick_col(df, ["Fecha Retiro", "Fecha de Retiro", "Fec. Retiro", "Retiro"])
    col_motivo   = _pick_col(df, ["Motivo Retiro", "Motivo de Retiro", "Motivo"])
    col_estado   = _pick_col(df, ["Estado Matrícula", "Estado Matricula", "Estado"])
    col_sexo     = _pick_col(df, ["Sexo", "Género", "Genero"])
    col_nac      = _pick_col(df, ["Nacionalidad", "País", "Pais"])
    col_edad     = _pick_col(df, ["Edad"])
    col_nac_date = _pick_col(df, ["Nacimiento", "Fecha Nacimiento", "F. Nacimiento", "Fecha de Nacimiento"])

    missing = []
    if col_rut is None:
        missing.append("RUT (ej: 'Número Rut')")
    if col_nombre is None:
        missing.append("Nombre (ej: 'Nombre')")
    if col_curso is None:
        missing.append("Curso (ej: 'Código Curso')")
    if missing:
        raise KeyError(f"Faltan columnas críticas en matrícula: {', '.join(missing)}")

    out = pd.DataFrame()

    out["rut_raw"]  = df[col_rut].fillna("").astype(str)
    out["rut_norm"] = out["rut_raw"].map(normalize_rut)

    out["nombre_raw"] = df[col_nombre].fillna("").astype(str)
    out["nombre"]     = out["nombre_raw"].map(normalize_text).str.upper()

    out["comuna_raw"] = df[col_comuna].fillna("").astype(str) if col_comuna else ""
    out["comuna"]     = out["comuna_raw"].map(normalize_text).str.upper()

    out["course_raw"]  = df[col_curso].fillna("").astype(str)
    out["course_code"] = out["course_raw"].map(normalize_text).str.upper()
    out["level"]       = out["course_code"].map(derive_level)
    out["specialty"]   = out["course_code"].map(derive_specialty)

    if col_rep:
        rep = df[col_rep].fillna("").astype(str).str.strip().str.upper()
        out["is_repeat"] = rep.isin(["SI", "S", "TRUE", "1", "YES", "Y"])
    else:
        out["is_repeat"] = False

    out["fecha_retiro_raw"] = df[col_retiro].fillna("").astype(str) if col_retiro else ""
    out["fecha_retiro"]     = parse_date(out["fecha_retiro_raw"])

    out["motivo_retiro_raw"]    = df[col_motivo].fillna("").astype(str) if col_motivo else ""
    out["estado_matricula_raw"] = df[col_estado].fillna("").astype(str) if col_estado else ""

    if col_sexo:
        sx = df[col_sexo].fillna("").astype(str).str.strip().str.upper()
        out["sexo"] = sx.replace({"MASCULINO": "M", "FEMENINO": "F"})
    else:
        out["sexo"] = ""

    if col_nac:
        out["nacionalidad_raw"] = df[col_nac].fillna("").astype(str)
        out["nacionalidad"]     = out["nacionalidad_raw"].map(normalize_text).str.upper()
    else:
        out["nacionalidad_raw"] = ""
        out["nacionalidad"]     = ""

    if col_edad:
        out["edad_raw"] = df[col_edad].fillna("").astype(str)
        out["edad"]     = parse_int(df[col_edad])
    else:
        out["edad_raw"] = ""
        out["edad"]     = pd.Series([pd.NA] * len(df), dtype="Int64")

    if col_nac_date:
        out["nacimiento_raw"] = df[col_nac_date].fillna("").astype(str)
        out["nacimiento"]     = parse_date(df[col_nac_date])
    else:
        out["nacimiento_raw"] = ""
        out["nacimiento"]     = pd.NaT

    out["source_snapshot"] = snapshot_file.name
    out["ingested_at"]     = datetime.now().strftime("%Y%m%d_%H%M%S")

    out_path = out_dir / snapshot_file.with_suffix(".parquet").name
    out.to_parquet(out_path, index=False)

    ruts_vacios     = int((out["rut_norm"] == "").sum())
    cursos_vacios   = int((out["course_code"] == "").sum())
    retiro_count    = int(out["fecha_retiro"].notna().sum())
    nacimiento_count = int(out["nacimiento"].notna().sum())
    dup_ruts        = int(out[out["rut_norm"] != ""].duplicated("rut_norm").sum())

    log.info(f"✅ Staging generado: {out_path}")
    log.info(f"Rows: {len(out):,}")
    log.info(f"RUT vacíos: {ruts_vacios:,} | Duplicados por RUT (no vacío): {dup_ruts:,}")
    log.info(f"Cursos vacíos: {cursos_vacios:,} | Con fecha_retiro (no nula): {retiro_count:,}")
    log.info(f"Nacimiento parseado (no nulo): {nacimiento_count:,}")

    return out_path