from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger

log = get_logger("EWS.curated_enrollment")


@dataclass(frozen=True)
class DiffResultPaths:
    snapshot_out: Path
    diff_out: Path


_TS_RE = re.compile(r"matricula_snapshot_(\d{8})_(\d{6})", re.IGNORECASE)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _extract_ts(p: Path) -> Tuple[str, str]:
    """
    Extrae (YYYYMMDD, HHMMSS) desde el nombre.
    Si no calza, devuelve mínimos para no romper (y usaremos fallback mtime).
    """
    m = _TS_RE.search(p.stem)
    if not m:
        return ("00000000", "000000")
    return (m.group(1), m.group(2))


def _list_parquet_sorted(stg_dir: Path) -> List[Path]:
    """
    Ordena por timestamp en nombre; si no hay timestamp, usa mtime como fallback.
    Así no dependemos 100% del naming.
    """
    files = list(stg_dir.glob("*.parquet"))
    if not files:
        return []

    def sort_key(p: Path):
        d, t = _extract_ts(p)
        has_ts = (d, t) != ("00000000", "000000")
        # Primero los que sí tienen ts (ideal), luego los que no, y esos por mtime
        if has_ts:
            return (0, d, t, 0.0)
        return (1, "99999999", "999999", p.stat().st_mtime)

    files.sort(key=sort_key)
    return files


def _norm_str_series(s: pd.Series) -> pd.Series:
    return (
        s.fillna("")
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.upper()
    )


def _norm_bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    x = s.fillna("").astype(str).str.strip().str.upper()
    return x.isin(["TRUE", "1", "SI", "S", "YES", "Y"])


def _norm_date_series(s: pd.Series) -> pd.Series:
    """
    Normalizamos fechas a YYYY-MM-DD string para comparar sin falsos positivos.
    """
    dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return dt.dt.strftime("%Y-%m-%d").fillna("")


def _prepare_for_compare(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            continue
        if c == "is_repeat":
            out[c] = _norm_bool_series(out[c])
        elif c == "level":
            out[c] = out[c].fillna("").astype(str).str.strip()
        elif c == "fecha_retiro":
            out[c] = _norm_date_series(out[c])
        else:
            out[c] = _norm_str_series(out[c])
    return out


def _dedupe_by_rut(df: pd.DataFrame, key: str = "rut_norm") -> pd.DataFrame:
    """
    Si hay duplicados por RUT (pasa en Syscol), elegimos 1 registro representativo:
    - prioriza activo (fecha_retiro NaT/vacío)
    - si hay varios, toma el último por ingested_at (si existe), o deja el primero
    """
    if key not in df.columns:
        return df

    d = df.copy()
    d[key] = d[key].fillna("").astype(str).str.strip()
    d = d[d[key] != ""].copy()

    if d.empty:
        return d

    # Activo vs retirado
    if "fecha_retiro" in d.columns:
        fr = pd.to_datetime(d["fecha_retiro"], errors="coerce", dayfirst=True)
        d["_activo"] = fr.isna()
    else:
        d["_activo"] = True

    # ingested_at (si existe) para elegir “más reciente”
    if "ingested_at" in d.columns:
        # formato esperado YYYYMMDD_HHMMSS o similar
        ia = d["ingested_at"].fillna("").astype(str)
        d["_ing"] = ia
    else:
        d["_ing"] = ""

    # Orden: rut, activo primero, luego ingested_at desc, luego estable
    d = d.sort_values([key, "_activo", "_ing"], ascending=[True, False, False])
    out = d.drop_duplicates(key, keep="first").drop(columns=["_activo", "_ing"], errors="ignore")
    return out


def build_curated_enrollment(compare_retiro: bool = True) -> DiffResultPaths:
    """
    Usa los 2 staging parquet más recientes y genera:
    - snapshot curated (actual)
    - diff vs anterior: NEW/REMOVED/UPDATED/UNCHANGED

    compare_retiro=True:
      incluye fecha_retiro en la comparación (auditoría).
    """
    stg_dir = PATHS.staging / "matricula"
    curated_dir = PATHS.curated / "enrollment"
    _ensure_dir(curated_dir)

    files = _list_parquet_sorted(stg_dir)
    if len(files) < 2:
        raise ValueError(f"Se requieren al menos 2 parquet en {stg_dir} para generar diff.")

    prev_path = files[-2]
    curr_path = files[-1]

    log.info(f"📦 Snapshot anterior: {prev_path.name}")
    log.info(f"📦 Snapshot actual:   {curr_path.name}")

    prev_raw = pd.read_parquet(prev_path)
    curr_raw = pd.read_parquet(curr_path)

    key = "rut_norm"
    if key not in prev_raw.columns or key not in curr_raw.columns:
        raise ValueError(f"Column '{key}' debe existir en staging.")

    # Normalizar key
    prev_raw[key] = prev_raw[key].fillna("").astype(str).str.strip()
    curr_raw[key] = curr_raw[key].fillna("").astype(str).str.strip()

    # ✅ Dedupe por RUT para evitar diffs raros por duplicados
    prev = _dedupe_by_rut(prev_raw, key=key)
    curr = _dedupe_by_rut(curr_raw, key=key)

    # Snapshot curated = curr deduplicado (y con RUT no vacío)
    prev_valid = prev[prev[key] != ""].copy()
    curr_valid = curr[curr[key] != ""].copy()

    # Columnas a comparar
    compare_cols = ["course_code", "comuna", "is_repeat", "level", "specialty", "nombre"]
    if compare_retiro and "fecha_retiro" in prev_valid.columns and "fecha_retiro" in curr_valid.columns:
        compare_cols.append("fecha_retiro")

    # Nos quedamos solo con las que existan en ambos
    compare_cols = [c for c in compare_cols if c in prev_valid.columns and c in curr_valid.columns]

    prev_cmp = _prepare_for_compare(prev_valid[[key] + compare_cols], compare_cols)
    curr_cmp = _prepare_for_compare(curr_valid[[key] + compare_cols], compare_cols)

    merged = curr_cmp.merge(
        prev_cmp,
        on=key,
        how="left",
        suffixes=("", "_prev"),
        indicator=True,
    )

    merged["change_type"] = "UNCHANGED"
    merged.loc[merged["_merge"] == "left_only", "change_type"] = "NEW"

    # UPDATED si cambió cualquier campo comparable
    both = merged["_merge"] == "both"
    changed_fields: List[list[str]] = [[] for _ in range(len(merged))]

    if compare_cols:
        diffs = pd.Series(False, index=merged.index)
        for c in compare_cols:
            diff_c = merged[c] != merged[f"{c}_prev"]
            diffs = diffs | diff_c

            # guardamos campos cambiados
            idxs = merged.index[diff_c & both]
            for i in idxs:
                changed_fields[i].append(c)

        merged.loc[both & diffs, "change_type"] = "UPDATED"

    merged["changed_fields"] = changed_fields

    # REMOVED: ruts que estaban antes y ya no están
    removed_keys = prev_valid[~prev_valid[key].isin(curr_valid[key])][key].copy()
    removed = prev_cmp[prev_cmp[key].isin(removed_keys)].copy()
    removed["change_type"] = "REMOVED"
    removed["changed_fields"] = [[] for _ in range(len(removed))]

    # Paths output
    snapshot_out = curated_dir / f"enrollment_snapshot__{curr_path.stem}.parquet"
    diff_out = curated_dir / f"enrollment_diff__{prev_path.stem}__to__{curr_path.stem}.parquet"

    # Guardar snapshot curated (curr dedupe)
    curr_valid.to_parquet(snapshot_out, index=False)

    diff_current = merged.drop(columns=["_merge"], errors="ignore")
    diff_all = pd.concat([diff_current, removed], ignore_index=True, sort=False)

    # ✅ Campos extra para reportes de cambios de curso
    if "course_code" in diff_all.columns and "course_code_prev" in diff_all.columns:
        diff_all["course_from"] = diff_all["course_code_prev"].fillna("")
        diff_all["course_to"] = diff_all["course_code"].fillna("")
        diff_all["changed_course_flag"] = (
            (diff_all["change_type"] == "UPDATED")
            & (diff_all["course_from"] != "")
            & (diff_all["course_to"] != "")
            & (diff_all["course_from"] != diff_all["course_to"])
        ).astype(int)
    else:
        diff_all["course_from"] = ""
        diff_all["course_to"] = ""
        diff_all["changed_course_flag"] = 0

    # Orden de salida
    order = {"NEW": 0, "UPDATED": 1, "REMOVED": 2, "UNCHANGED": 3}
    diff_all["_ord"] = diff_all["change_type"].map(order).fillna(9).astype(int)
    diff_all = diff_all.sort_values(["_ord", key]).drop(columns=["_ord"])

    diff_all.to_parquet(diff_out, index=False)

    counts = diff_all["change_type"].value_counts(dropna=False).to_dict()
    log.info(f"✅ Curated snapshot: {snapshot_out.name}")
    log.info(f"✅ Diff generado:    {diff_out.name}")
    log.info(f"📊 Resumen cambios: {counts}")

    # Auditoría: duplicados detectados (antes del dedupe)
    try:
        prev_dups = int(prev_raw[prev_raw[key] != ""].duplicated(key).sum())
        curr_dups = int(curr_raw[curr_raw[key] != ""].duplicated(key).sum())
        if prev_dups or curr_dups:
            log.info(f"🧼 Dedupe aplicado por RUT | prev_dups={prev_dups} | curr_dups={curr_dups}")
    except Exception:
        pass

    return DiffResultPaths(snapshot_out=snapshot_out, diff_out=diff_out)