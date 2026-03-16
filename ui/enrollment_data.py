# ui/enrollment_data.py
from __future__ import annotations

import re
from pathlib import Path
import pandas as pd
import streamlit as st

DATA_GOLD = Path("data/gold/enrollment")
CURATED_ENROLLMENT = Path("data/curated/enrollment")
STAGING_DESISTE = Path("data/staging/desiste")

_MET_RE = re.compile(r"enrollment_metrics__(\d{8})\.parquet$", re.IGNORECASE)
_DIFF_CURR_RE = re.compile(r"__to__matricula_snapshot_(\d{8})_(\d{6})\.parquet$", re.IGNORECASE)


@st.cache_data(show_spinner=False)
def list_enrollment_dates() -> list[str]:
    if not DATA_GOLD.exists():
        return []
    return sorted(
        {
            m.group(1)
            for p in DATA_GOLD.glob("enrollment_metrics__*.parquet")
            if (m := _MET_RE.match(p.name))
        }
    )


@st.cache_data(show_spinner=False)
def load_parquet_safe(path_str: str):
    path = Path(path_str)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def gold(name: str) -> Path:
    return DATA_GOLD / name


def load_diff_for_stamp(stamp: str):
    """
    Busca el diff cuyo snapshot destino sea el stamp actual.
    Así evitamos usar 'el último por mtime', que puede no coincidir.
    """
    if not CURATED_ENROLLMENT.exists():
        return None

    candidates = []
    for p in CURATED_ENROLLMENT.glob("enrollment_diff__*.parquet"):
        m = _DIFF_CURR_RE.search(p.name)
        if m and m.group(1) == stamp:
            candidates.append(p)

    if not candidates:
        return None

    # Si hubiera más de uno, nos quedamos con el más reciente
    selected = max(candidates, key=lambda p: p.stat().st_mtime)
    return load_parquet_safe(str(selected))


def load_transfers_for_stamp(stamp: str):
    """
    Busca transferencias asociadas al corte actual.
    Primero intenta match exacto por stamp; si no encuentra, devuelve None.
    """
    if not DATA_GOLD.exists():
        return None

    candidates = list(DATA_GOLD.glob(f"enrollment_transfers_all__{stamp}*.parquet"))
    if not candidates:
        return None

    selected = max(candidates, key=lambda p: p.stat().st_mtime)
    return load_parquet_safe(str(selected))


def load_desiste_for_stamp(stamp: str):
    """
    Convierte YYYYMMDD -> YYYY-MM-DD para buscar el snapshot de desiste del mismo corte.
    """
    if len(stamp) != 8:
        return None

    iso = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
    path = STAGING_DESISTE / f"desiste_snapshot__desiste_{iso}.parquet"
    return load_parquet_safe(str(path))


def load_enrollment_bundle(stamp: str, prev_stamp: str | None = None) -> dict:
    return {
        "metrics": load_parquet_safe(str(gold(f"enrollment_metrics__{stamp}.parquet"))),
        "df_current": load_parquet_safe(str(gold(f"enrollment_current__{stamp}.parquet"))),
        "df_demo": load_parquet_safe(str(gold(f"enrollment_demographics__{stamp}.parquet"))),
        "df_comunas": load_parquet_safe(str(gold(f"enrollment_by_comuna__{stamp}.parquet"))),
        "df_nacs": load_parquet_safe(str(gold(f"enrollment_by_nacionalidad__{stamp}.parquet"))),
        "df_specs": load_parquet_safe(str(gold(f"enrollment_by_specialty__{stamp}.parquet"))),
        "df_anomalies": load_parquet_safe(str(gold(f"enrollment_age_anomalies__{stamp}.parquet"))),
        "df_master": load_parquet_safe(str(gold(f"enrollment_master_metrics__{stamp}.parquet"))),
        "prev_metrics": load_parquet_safe(str(gold(f"enrollment_metrics__{prev_stamp}.parquet"))) if prev_stamp else None,
        "df_transfers": load_transfers_for_stamp(stamp),
        "df_diff": load_diff_for_stamp(stamp),
        "df_desiste_curr": load_desiste_for_stamp(stamp),
        "df_desiste_prev": load_desiste_for_stamp(prev_stamp) if prev_stamp else None,
    }