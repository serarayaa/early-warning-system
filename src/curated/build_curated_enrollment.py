from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger
from src.utils.transforms import (
    ensure_dir,
    normalize_text_series,
    parse_date,
    pick_one_per_rut,
)

log = get_logger("EWS.curated_enrollment")


@dataclass(frozen=True)
class DiffResultPaths:
    snapshot_out: Path
    diff_out: Path


_TS_RE = re.compile(r"matricula_snapshot_(\d{8})_(\d{6})", re.IGNORECASE)


# ---------------------------------------------------------------------
# Helpers locales (específicos de curated, NO son duplicados)
# ---------------------------------------------------------------------

def _extract_ts(p: Path) -> Tuple[str, str]:
    """
    Extrae (YYYYMMDD, HHMMSS) desde el nombre del archivo.
    Si no calza el patrón, devuelve mínimos como fallback.
    """
    m = _TS_RE.search(p.stem)
    if not m:
        return ("00000000", "000000")
    return (m.group(1), m.group(2))


def _list_parquet_sorted(stg_dir: Path) -> List[Path]:
    """
    Lista y ordena parquets por timestamp en nombre;
    usa mtime como fallback si no hay timestamp.
    """
    files = list(stg_dir.glob("*.parquet"))
    if not files:
        return []

    def sort_key(p: Path):
        d, t = _extract_ts(p)
        if (d, t) != ("00000000", "000000"):
            return (0, d, t, 0.0)
        return (1, "99999999", "999999", p.stat().st_mtime)

    files.sort(key=sort_key)
    return files


def _prepare_for_compare(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """
    Normaliza columnas antes de comparar entre snapshots.
    Cada tipo de columna tiene su normalización específica
    para evitar falsos positivos en el diff.
    """
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            continue
        if c == "is_repeat":
            x = out[c].fillna("").astype(str).str.strip().str.upper()
            out[c] = x.isin(["TRUE", "1", "SI", "S", "YES", "Y"])
        elif c == "level":
            out[c] = out[c].fillna("").astype(str).str.strip()
        elif c == "fecha_retiro":
            # Normalizar a string YYYY-MM-DD para comparar sin falsos positivos de formato
            dt = parse_date(out[c])
            out[c] = dt.dt.strftime("%Y-%m-%d").fillna("")
        else:
            out[c] = normalize_text_series(out[c])
    return out


def _dedupe_by_rut(df: pd.DataFrame, key: str = "rut_norm") -> pd.DataFrame:
    """
    Deduplica por RUT eligiendo 1 fila representativa.
    Delega en pick_one_per_rut (sin snapshot_date → solo prioriza activo).
    Mantiene el parámetro `key` por compatibilidad, aunque siempre usa rut_norm.
    """
    if key not in df.columns:
        return df

    d = df.copy()
    d[key] = d[key].fillna("").astype(str).str.strip()
    d = d[d[key] != ""].copy()

    if d.empty:
        return d

    # pick_one_per_rut requiere 'rut_norm'; si key es distinto, renombramos temporalmente
    if key != "rut_norm":
        d = d.rename(columns={key: "rut_norm"})
        d = pick_one_per_rut(d)
        d = d.rename(columns={"rut_norm": key})
    else:
        d = pick_one_per_rut(d)

    return d


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def build_curated_enrollment(compare_retiro: bool = True) -> DiffResultPaths:
    """
    Usa los 2 staging parquet más recientes y genera:
    - snapshot curated (actual, deduplicado)
    - diff vs anterior: NEW / REMOVED / UPDATED / UNCHANGED

    compare_retiro=True: incluye fecha_retiro en la comparación (auditoría).
    """
    stg_dir = PATHS.staging / "matricula"
    curated_dir = PATHS.curated / "enrollment"
    ensure_dir(curated_dir)

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
        raise ValueError(f"Columna '{key}' debe existir en staging.")

    prev_raw[key] = prev_raw[key].fillna("").astype(str).str.strip()
    curr_raw[key] = curr_raw[key].fillna("").astype(str).str.strip()

    prev = _dedupe_by_rut(prev_raw, key=key)
    curr = _dedupe_by_rut(curr_raw, key=key)

    prev_valid = prev[prev[key] != ""].copy()
    curr_valid = curr[curr[key] != ""].copy()

    compare_cols = ["course_code", "comuna", "is_repeat", "level", "specialty", "nombre"]
    if compare_retiro and "fecha_retiro" in prev_valid.columns and "fecha_retiro" in curr_valid.columns:
        compare_cols.append("fecha_retiro")
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

    both = merged["_merge"] == "both"
    changed_fields: List[list[str]] = [[] for _ in range(len(merged))]

    if compare_cols:
        diffs = pd.Series(False, index=merged.index)
        for c in compare_cols:
            diff_c = merged[c] != merged[f"{c}_prev"]
            diffs = diffs | diff_c
            for i in merged.index[diff_c & both]:
                changed_fields[i].append(c)
        merged.loc[both & diffs, "change_type"] = "UPDATED"

    merged["changed_fields"] = changed_fields

    removed_keys = prev_valid[~prev_valid[key].isin(curr_valid[key])][key].copy()
    removed = prev_cmp[prev_cmp[key].isin(removed_keys)].copy()
    removed["change_type"] = "REMOVED"
    removed["changed_fields"] = [[] for _ in range(len(removed))]

    snapshot_out = curated_dir / f"enrollment_snapshot__{curr_path.stem}.parquet"
    diff_out = curated_dir / f"enrollment_diff__{prev_path.stem}__to__{curr_path.stem}.parquet"

    curr_valid.to_parquet(snapshot_out, index=False)

    diff_current = merged.drop(columns=["_merge"], errors="ignore")
    diff_all = pd.concat([diff_current, removed], ignore_index=True, sort=False)

    if "course_code" in diff_all.columns and "course_code_prev" in diff_all.columns:
        diff_all["course_from"] = diff_all["course_code_prev"].fillna("")
        diff_all["course_to"]   = diff_all["course_code"].fillna("")
        diff_all["changed_course_flag"] = (
            (diff_all["change_type"] == "UPDATED")
            & (diff_all["course_from"] != "")
            & (diff_all["course_to"] != "")
            & (diff_all["course_from"] != diff_all["course_to"])
        ).astype(int)
    else:
        diff_all["course_from"] = ""
        diff_all["course_to"]   = ""
        diff_all["changed_course_flag"] = 0

    order = {"NEW": 0, "UPDATED": 1, "REMOVED": 2, "UNCHANGED": 3}
    diff_all["_ord"] = diff_all["change_type"].map(order).fillna(9).astype(int)
    diff_all = diff_all.sort_values(["_ord", key]).drop(columns=["_ord"])
    diff_all.to_parquet(diff_out, index=False)

    counts = diff_all["change_type"].value_counts(dropna=False).to_dict()
    log.info(f"✅ Curated snapshot: {snapshot_out.name}")
    log.info(f"✅ Diff generado:    {diff_out.name}")
    log.info(f"📊 Resumen cambios: {counts}")

    try:
        prev_dups = int(prev_raw[prev_raw[key] != ""].duplicated(key).sum())
        curr_dups = int(curr_raw[curr_raw[key] != ""].duplicated(key).sum())
        if prev_dups or curr_dups:
            log.info(f"🧼 Dedupe aplicado | prev_dups={prev_dups} | curr_dups={curr_dups}")
    except Exception:
        pass

    return DiffResultPaths(snapshot_out=snapshot_out, diff_out=diff_out)