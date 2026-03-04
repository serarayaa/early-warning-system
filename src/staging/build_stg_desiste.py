from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config.settings import PATHS, SPECIALTY_BY_SECTION
from src.utils.logging_utils import get_logger

log = get_logger("EWS.stg_desiste")

ALLOWED_EXTS = {".csv", ".xlsx", ".xls"}


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _normalize_text(x) -> str:
    s = "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_rut(rut) -> str:
    """
    Normaliza RUT: deja solo dígitos y K, con guion.
    Ej: 12.345.678-9 -> 12345678-9
    """
    if rut is None or (isinstance(rut, float) and pd.isna(rut)):
        return ""
    rut = str(rut).upper().strip()
    rut = rut.replace(".", "").replace(" ", "").replace("-", "")
    if len(rut) < 2:
        return ""
    cuerpo, dv = rut[:-1], rut[-1]
    cuerpo = re.sub(r"\D", "", cuerpo)
    dv = re.sub(r"[^0-9K]", "", dv)
    if not cuerpo or not dv:
        return ""
    return f"{cuerpo}-{dv}"


def derive_level(course_code: str) -> int | None:
    if not course_code:
        return None
    m = re.match(r"^(\d)", str(course_code).strip())
    return int(m.group(1)) if m else None


def derive_section_letter(course_code: str) -> str | None:
    if not course_code:
        return None
    cc = str(course_code).strip().upper()
    # caso tipo: 1MA, 2MB, 3MG...
    return cc[-1] if cc else None


def derive_specialty(course_code: str) -> str:
    letter = derive_section_letter(course_code)
    if not letter:
        return "COMUN"
    return SPECIALTY_BY_SECTION.get(letter, "COMUN")


def _infer_snapshot_date_from_name(name: str) -> pd.Timestamp | pd.NaT:
    """
    Intenta extraer fecha desde nombre tipo: desiste_2026-03-03.csv / desiste_2026-03-03.xlsx
    """
    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    if not m:
        return pd.NaT
    return pd.to_datetime(m.group(1), errors="coerce")


def _pick_first_existing_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """
    Retorna la primera columna que exista (match exacto) en df.columns.
    """
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
    # dtype=str para mantener todo controlado
    return pd.read_excel(file_path, dtype=str)


def _read_input(file_path: Path) -> pd.DataFrame:
    ext = file_path.suffix.lower()
    if ext == ".csv":
        return _read_csv_robust(file_path)
    if ext in {".xlsx", ".xls"}:
        return _read_excel(file_path)
    raise ValueError(f"Extensión no soportada: {ext}")


def _resolve_raw_path(input_file: str) -> tuple[Path, str]:
    """
    input_file puede ser ruta completa o nombre dentro de data/raw/desiste/
    Retorna (raw_path, snapshot_name)
    """
    p = Path(input_file).expanduser()
    if p.exists():
        raw_path = p.resolve()
        snapshot_name = raw_path.name
        return raw_path, snapshot_name

    raw_dir = PATHS.raw / "desiste"
    raw_path = (raw_dir / input_file).resolve()
    snapshot_name = input_file
    return raw_path, snapshot_name


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def build_staging_desiste(input_file: str, out_dir: Path | None = None) -> Path:
    """
    Construye staging parquet para un snapshot DESISTE.

    input_file puede ser:
    - nombre dentro de data/raw/desiste/ (ej: desiste_2026-03-03.csv)
    - ruta completa al archivo (csv/xlsx/xls)
    """
    raw_path, snapshot_name = _resolve_raw_path(input_file)

    if not raw_path.exists():
        raise FileNotFoundError(f"No existe archivo DESISTE: {raw_path}")

    if raw_path.suffix.lower() not in ALLOWED_EXTS:
        raise ValueError(f"Extensión no soportada: {raw_path.suffix}. Permitidas: {sorted(ALLOWED_EXTS)}")

    if out_dir is None:
        out_dir = PATHS.staging / "desiste"
    _ensure_dir(out_dir)

    log.info(f"📥 Leyendo snapshot DESISTE: {raw_path.name}")
    df = _read_input(raw_path)
    df.columns = [str(c).strip() for c in df.columns]

    # Columnas esperadas (tolerante a variaciones)
    col_rut = _pick_first_existing_col(df, ["Número Rut", "Numero Rut", "RUT", "Rut", "rut"])
    col_curso = _pick_first_existing_col(df, ["Código Curso", "Codigo Curso", "Curso", "course_code"])
    col_estado = _pick_first_existing_col(df, ["Estado Matrícula", "Estado Matricula", "Estado", "estado"])
    col_nombre = _pick_first_existing_col(df, ["Nombre", "Nombres Alumno", "Alumno", "Estudiante"])
    col_comuna = _pick_first_existing_col(df, ["Comuna", "COMUNA"])
    col_nac = _pick_first_existing_col(df, ["Nacionalidad", "NACIONALIDAD"])
    col_sexo = _pick_first_existing_col(df, ["Sexo", "SEXO"])
    col_edad = _pick_first_existing_col(df, ["Edad", "EDAD"])

    if col_rut is None:
        raise KeyError("No se encontró columna de RUT en DESISTE (ej: 'Número Rut').")
    if col_curso is None:
        raise KeyError("No se encontró columna de curso en DESISTE (ej: 'Código Curso').")
    if col_nombre is None:
        log.warning("⚠️ No se encontró columna de nombre (se dejará vacío).")

    out = pd.DataFrame()

    out["rut_raw"] = df[col_rut]
    out["rut_norm"] = out["rut_raw"].map(normalize_rut)

    if col_estado:
        out["estado_matricula_raw"] = df[col_estado]
    else:
        out["estado_matricula_raw"] = "DESISTE"
    out["estado_matricula"] = out["estado_matricula_raw"].map(_normalize_text).str.upper()

    out["course_raw"] = df[col_curso]
    out["course_code"] = out["course_raw"].map(_normalize_text).str.upper()

    out["level"] = out["course_code"].map(derive_level)
    out["specialty"] = out["course_code"].map(derive_specialty)

    out["nombre_raw"] = df[col_nombre] if col_nombre else ""
    out["nombre"] = out["nombre_raw"].map(_normalize_text).str.upper()

    out["comuna_raw"] = df[col_comuna] if col_comuna else ""
    out["comuna"] = out["comuna_raw"].map(_normalize_text).str.upper()

    out["nacionalidad_raw"] = df[col_nac] if col_nac else ""
    out["nacionalidad"] = out["nacionalidad_raw"].map(_normalize_text).str.upper()

    out["sexo_raw"] = df[col_sexo] if col_sexo else ""
    out["sexo"] = out["sexo_raw"].map(_normalize_text).str.upper()

    out["edad_raw"] = df[col_edad] if col_edad else ""
    out["edad"] = pd.to_numeric(out["edad_raw"], errors="coerce")

    out["snapshot_date"] = _infer_snapshot_date_from_name(snapshot_name)
    out["source_snapshot"] = snapshot_name
    out["ingested_at"] = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Guardar parquet
    out_path = out_dir / f"desiste_snapshot__{Path(snapshot_name).stem}.parquet"
    out.to_parquet(out_path, index=False)

    # Auditoría
    log.info(f"✅ Staging DESISTE generado: {out_path}")
    log.info(f"Rows: {len(out):,}")
    log.info(f"RUT vacíos: {(out['rut_norm'] == '').sum():,}")
    log.info(f"Cursos vacíos: {(out['course_code'] == '').sum():,}")

    return out_path