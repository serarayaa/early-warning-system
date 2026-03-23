# ui/enrollment_data.py
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_GOLD = Path("data/gold/enrollment")
CURATED_ENROLLMENT = Path("data/curated/enrollment")

_MET_RE = re.compile(r"enrollment_metrics__(\d{8})\.parquet$", re.IGNORECASE)
_DIFF_CURR_RE = re.compile(r"__to__matricula_snapshot_(\d{8})_(\d{6})\.parquet$", re.IGNORECASE)


def list_enrollment_dates() -> list[str]:
    if not DATA_GOLD.exists():
        return []

    fechas = []
    for p in DATA_GOLD.glob("enrollment_metrics__*.parquet"):
        m = _MET_RE.match(p.name)
        if m:
            stamp = m.group(1)
            if stamp != "20261231":  # excluir parquet basura
                fechas.append(stamp)

    return sorted(set(fechas))



@st.cache_data(ttl=30, show_spinner=False)
def load_parquet_cached(path_str: str, _mtime: float):
    """Cache con TTL + mtime como key — se invalida si el archivo cambia."""
    path = Path(path_str)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def load_parquet_safe(path_str: str):
    """Lee parquet con cache inteligente basado en mtime del archivo."""
    path = Path(path_str)
    if not path.exists():
        return None
    try:
        mtime = path.stat().st_mtime
        return load_parquet_cached(path_str, mtime)
    except Exception:
        return None




def gold(name: str) -> Path:
    return DATA_GOLD / name


def load_diff_for_stamp(stamp: str):
    if not CURATED_ENROLLMENT.exists():
        return None

    candidates = []
    for p in CURATED_ENROLLMENT.glob("enrollment_diff__*.parquet"):
        m = _DIFF_CURR_RE.search(p.name)
        if m and m.group(1) == stamp:
            candidates.append(p)

    if not candidates:
        return None

    selected = max(candidates, key=lambda p: p.stat().st_mtime)
    return load_parquet_safe(str(selected))


def load_transfers_for_stamp(stamp: str):
    if not DATA_GOLD.exists():
        return None

    exact = list(DATA_GOLD.glob(f"enrollment_transfers_all__{stamp}*.parquet"))
    if exact:
        selected = max(exact, key=lambda p: p.stat().st_mtime)
        return load_parquet_safe(str(selected))

    generic = list(DATA_GOLD.glob("enrollment_transfers*.parquet"))
    if generic:
        selected = max(generic, key=lambda p: p.stat().st_mtime)
        return load_parquet_safe(str(selected))

    return None



def _load_direccion_from_raw() -> pd.DataFrame | None:
    """
    Carga columna 'direccion' y 'rut_norm' directamente desde el CSV raw más reciente.
    Esto garantiza que la dirección siempre esté disponible aunque el pipeline
    no la haya propagado al parquet gold todavía.
    """
    import csv as _csv, unicodedata as _ud
    raw_dir = Path("data/raw/matricula")
    if not raw_dir.exists():
        return None
    csvs = sorted(raw_dir.glob("matricula_snapshot_*.csv"), key=lambda f: f.stat().st_mtime)
    if not csvs:
        return None
    latest = csvs[-1]
    try:
        # Probar encodings — Syscol exporta en latin-1
        for enc in ["latin1", "utf-8-sig", "utf-8", "cp1252"]:
            try:
                df = pd.read_csv(latest, sep=";", encoding=enc, dtype=str,
                                 on_bad_lines="skip")
                if len(df.columns) >= 5:
                    break
            except Exception:
                continue

        df.columns = [str(c).strip() for c in df.columns]

        # Normalizar nombre de columna dirección
        def _norm(s):
            s = str(s).strip().lower()
            s = _ud.normalize("NFKD", s)
            return "".join(c for c in s if not _ud.combining(c))

        col_dir = next((c for c in df.columns if _norm(c) == "direccion"), None)
        col_rut = next((c for c in df.columns
                        if _norm(c) in ("numero rut", "rut", "numero_rut")), None)
        col_nombre = next((c for c in df.columns
                           if _norm(c) in ("nombre", "nombres alumno")), None)

        if not col_dir:
            return None

        cols = [c for c in [col_rut, col_nombre, col_dir] if c]
        df_dir = df[cols].copy()

        # Normalizar rut igual que el pipeline
        if col_rut:
            import re as _re
            df_dir["rut_norm"] = df_dir[col_rut].fillna("").astype(str).str.strip().apply(
                lambda v: _re.sub(r"[^0-9kK\-]", "", v).upper()
            )
        if col_nombre:
            df_dir["nombre"] = df_dir[col_nombre].fillna("").astype(str).str.strip().str.upper()
        df_dir["direccion"] = df_dir[col_dir].fillna("").astype(str).str.strip()

        return df_dir[["rut_norm", "nombre", "direccion"]].drop_duplicates("rut_norm")
    except Exception:
        return None

def load_enrollment_bundle(stamp: str, prev_stamp: str | None = None) -> dict:
    return {
        "metrics": load_parquet_safe(str(gold(f"enrollment_metrics__{stamp}.parquet"))),
        "df_current": load_parquet_safe(str(gold(f"enrollment_current__{stamp}.parquet"))),
        "df_prev_current": load_parquet_safe(str(gold(f"enrollment_current__{prev_stamp}.parquet"))) if prev_stamp else None,
        "df_demo": load_parquet_safe(str(gold(f"enrollment_demographics__{stamp}.parquet"))),
        "df_comunas": load_parquet_safe(str(gold(f"enrollment_by_comuna__{stamp}.parquet"))),
        "df_nacs": load_parquet_safe(str(gold(f"enrollment_by_nacionalidad__{stamp}.parquet"))),
        "df_specs": load_parquet_safe(str(gold(f"enrollment_by_specialty__{stamp}.parquet"))),
        "df_anomalies": load_parquet_safe(str(gold(f"enrollment_age_anomalies__{stamp}.parquet"))),
        "df_master": load_parquet_safe(str(gold(f"enrollment_master_metrics__{stamp}.parquet"))),
        "prev_metrics": load_parquet_safe(str(gold(f"enrollment_metrics__{prev_stamp}.parquet"))) if prev_stamp else None,
        "df_transfers": load_transfers_for_stamp(stamp),
        "df_diff":     load_diff_for_stamp(stamp),
    }


def enrich_with_direccion(df_current: pd.DataFrame | None) -> pd.DataFrame | None:
    """
    Inyecta columna 'direccion' en df_current desde el CSV raw más reciente.
    Se llama siempre que df_current no tenga la columna.
    """
    if df_current is None or df_current.empty:
        return df_current
    if "direccion" in df_current.columns:
        return df_current  # ya la tiene

    df_dir = _load_direccion_from_raw()
    if df_dir is None:
        return df_current

    # Cruce por rut_norm
    df_out = df_current.copy()
    if "rut_norm" in df_out.columns and "rut_norm" in df_dir.columns:
        dir_map = df_dir.set_index("rut_norm")["direccion"]
        df_out["direccion"] = df_out["rut_norm"].map(dir_map).fillna("")
    else:
        # Cruce por nombre como fallback
        if "nombre" in df_out.columns and "nombre" in df_dir.columns:
            dir_map = df_dir.set_index("nombre")["direccion"]
            df_out["direccion"] = df_out["nombre"].map(dir_map).fillna("")

    return df_out