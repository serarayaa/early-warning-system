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
    ensure_dir,
)

log = get_logger("EWS.stg_desiste")

ALLOWED_EXTS = {".csv", ".xlsx", ".xls"}

# Solo estos estados se consideran desiste real
VALID_DESISTE_STATES = {"DESISTE"}


# ---------------------------------------------------------------------
# Helpers locales
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


def _infer_snapshot_date_from_name(name: str) -> pd.Timestamp | pd.NaT:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    if not m:
        return pd.NaT
    return pd.to_datetime(m.group(1), errors="coerce")


def _pick_first_existing_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    cols = set(df.columns)
    for c in candidates:
        if c in cols:
            return c
    return None


def _read_csv_robust(file_path: Path) -> pd.DataFrame:
    encodings = ["utf-8", "latin1", "cp1252"]
    last_err: Exception | None = None
    for enc in encodings:
        try:
            log.info(f"🔎 Leyendo DESISTE CSV con encoding={enc}")
            return pd.read_csv(file_path, dtype=str, encoding=enc, sep=None, engine="python")
        except UnicodeDecodeError as e:
            last_err = e
            continue
    raise ValueError(f"No se pudo leer el CSV con encodings {encodings}. Error: {last_err}")


def _read_excel(file_path: Path) -> pd.DataFrame:
    log.info("🔎 Leyendo DESISTE Excel")
    return pd.read_excel(file_path, dtype=str)


def _read_input(file_path: Path) -> pd.DataFrame:
    ext = file_path.suffix.lower()
    if ext == ".csv":
        return _read_csv_robust(file_path)
    if ext in {".xlsx", ".xls"}:
        return _read_excel(file_path)
    raise ValueError(f"Extensión no soportada: {ext}")


def _resolve_raw_path(input_file: str) -> tuple[Path, str]:
    p = Path(input_file).expanduser()
    if p.exists():
        raw_path = p.resolve()
        return raw_path, raw_path.name
    raw_path = (PATHS.raw / "desiste" / input_file).resolve()
    return raw_path, input_file


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def build_staging_desiste(input_file: str, out_dir: Path | None = None) -> Path:
    raw_path, snapshot_name = _resolve_raw_path(input_file)

    if not raw_path.exists():
        raise FileNotFoundError(f"No existe archivo DESISTE: {raw_path}")
    if raw_path.suffix.lower() not in ALLOWED_EXTS:
        raise ValueError(f"Extensión no soportada: {raw_path.suffix}. Permitidas: {sorted(ALLOWED_EXTS)}")

    if out_dir is None:
        out_dir = PATHS.staging / "desiste"
    ensure_dir(out_dir)

    log.info(f"📥 Leyendo snapshot DESISTE: {raw_path.name}")
    df = _read_input(raw_path)
    df.columns = [str(c).strip() for c in df.columns]

    col_rut       = _pick_first_existing_col(df, ["Número Rut", "Numero Rut", "RUT", "Rut", "rut"])
    col_curso     = _pick_first_existing_col(df, ["Código Curso", "Codigo Curso", "Curso", "course_code"])
    col_estado    = _pick_first_existing_col(df, ["Estado Matrícula", "Estado Matricula", "Estado", "estado"])
    col_nombre    = _pick_first_existing_col(df, ["Nombre", "Nombres Alumno", "Alumno", "Estudiante"])
    col_comuna    = _pick_first_existing_col(df, ["Comuna", "COMUNA"])
    col_nac       = _pick_first_existing_col(df, ["Nacionalidad", "NACIONALIDAD"])
    col_sexo      = _pick_first_existing_col(df, ["Sexo", "SEXO"])
    col_edad      = _pick_first_existing_col(df, ["Edad", "EDAD"])
    col_repitente = _pick_first_existing_col(df, ["Repitente", "REPITENTE", "repitente", "is_repeat"])

    if col_rut is None:
        raise KeyError("No se encontró columna de RUT en DESISTE (ej: 'Número Rut').")
    if col_curso is None:
        raise KeyError("No se encontró columna de curso en DESISTE (ej: 'Código Curso').")
    if col_nombre is None:
        log.warning("⚠️ No se encontró columna de nombre (se dejará vacío).")
    if col_repitente is None:
        log.warning("⚠️ No se encontró columna de repitente (se asumirá False para todos).")

    out = pd.DataFrame()

    out["rut_raw"]  = df[col_rut]
    out["rut_norm"] = out["rut_raw"].map(normalize_rut)

    out["estado_matricula_raw"] = df[col_estado] if col_estado else "DESISTE"
    out["estado_matricula"]     = out["estado_matricula_raw"].map(normalize_text).str.upper()

    out["course_raw"]  = df[col_curso]
    out["course_code"] = out["course_raw"].map(normalize_text).str.upper()
    out["level"]       = out["course_code"].map(derive_level)
    out["specialty"]   = out["course_code"].map(derive_specialty)

    out["nombre_raw"] = df[col_nombre] if col_nombre else ""
    out["nombre"]     = out["nombre_raw"].map(normalize_text).str.upper()

    out["comuna_raw"] = df[col_comuna] if col_comuna else ""
    out["comuna"]     = out["comuna_raw"].map(normalize_text).str.upper()

    out["nacionalidad_raw"] = df[col_nac] if col_nac else ""
    out["nacionalidad"]     = out["nacionalidad_raw"].map(normalize_text).str.upper()

    out["sexo_raw"] = df[col_sexo] if col_sexo else ""
    out["sexo"]     = out["sexo_raw"].map(normalize_text).str.upper()

    out["edad_raw"] = df[col_edad] if col_edad else ""
    out["edad"]     = pd.to_numeric(out["edad_raw"], errors="coerce")

    # Repitente: "SI" → True, cualquier otro valor (guión, vacío, None) → False
    if col_repitente:
        out["is_repeat"] = (
            df[col_repitente]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            == "SI"
        )
    else:
        out["is_repeat"] = False

    out["snapshot_date"]   = _infer_snapshot_date_from_name(snapshot_name)
    out["source_snapshot"] = snapshot_name
    out["ingested_at"]     = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Filtro: solo registros con estado DESISTE ────────────────────
    total_raw   = len(out)
    descartados = out[~out["estado_matricula"].isin(VALID_DESISTE_STATES)].copy()
    out = out[out["estado_matricula"].isin(VALID_DESISTE_STATES)].copy().reset_index(drop=True)

    if len(descartados) > 0:
        estados_desc = descartados["estado_matricula"].value_counts().to_dict()
        log.info(f"🔍 Descartados {len(descartados)} registros con estado no válido: {estados_desc}")
        log.info(f"   ↳ Solo se conservan estados: {VALID_DESISTE_STATES}")

    out_path = out_dir / f"desiste_snapshot__{Path(snapshot_name).stem}.parquet"
    out.to_parquet(out_path, index=False)

    log.info(f"✅ Staging DESISTE generado: {out_path}")
    log.info(f"Rows raw: {total_raw:,} | Rows válidos (DESISTE): {len(out):,}")
    log.info(f"RUT vacíos: {(out['rut_norm'] == '').sum():,}")
    log.info(f"Cursos vacíos: {(out['course_code'] == '').sum():,}")
    log.info(f"Repitentes: {out['is_repeat'].sum():,} | No repitentes: {(~out['is_repeat']).sum():,}")

    return out_path