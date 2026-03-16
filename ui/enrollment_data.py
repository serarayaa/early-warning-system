# ui/enrollment_data.py
from __future__ import annotations

from pathlib import Path
import pandas as pd

DATA_GOLD = Path("data/gold/enrollment")


def list_enrollment_dates() -> list[str]:
    """
    Devuelve todos los snapshots disponibles de matrícula.
    """
    if not DATA_GOLD.exists():
        return []

    fechas = []

    for p in DATA_GOLD.glob("enrollment_metrics__*.parquet"):
        try:
            stamp = p.name.split("__")[1].replace(".parquet", "")
            fechas.append(stamp)
        except Exception:
            pass

    return sorted(set(fechas))


def _load_if_exists(path: Path):
    if path.exists():
        try:
            return pd.read_parquet(path)
        except Exception:
            return None
    return None


def load_enrollment_bundle(stamp: str) -> dict:
    """
    Carga todos los datasets asociados a un snapshot de matrícula.
    """

    bundle = {}

    files = {
        "metrics": f"enrollment_metrics__{stamp}.parquet",
        "current": f"enrollment_current__{stamp}.parquet",
        "demo": f"enrollment_demo__{stamp}.parquet",
        "comunas": f"enrollment_comunas__{stamp}.parquet",
        "nacionalidades": f"enrollment_nacs__{stamp}.parquet",
        "especialidades": f"enrollment_specs__{stamp}.parquet",
        "anomalies": f"enrollment_anomalies__{stamp}.parquet",
        "master": f"enrollment_master__{stamp}.parquet",
        "transfers": f"enrollment_transfers__{stamp}.parquet",
        "diff": f"enrollment_diff__{stamp}.parquet",
        "desiste": f"enrollment_desiste__{stamp}.parquet",
    }

    for key, filename in files.items():
        bundle[key] = _load_if_exists(DATA_GOLD / filename)

    return bundle