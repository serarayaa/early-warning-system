from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger
from src.utils.transforms import (
    coalesce_duplicates,
    latest_snapshot_file,
    parse_date,
    pick_one_per_rut,
    rut_key,
)

log = get_logger("EWS.enrollment_master")


@dataclass(frozen=True)
class MasterPaths:
    master_out: Path
    metrics_out: Path


def enrollment_master(snapshot_date: str, export_excel: bool = False) -> MasterPaths:
    """
    MASTER de matrícula (regla Syscol):
    - Matrícula (curated snapshot) = "Matriculados Syscol" (ya excluye DESISTE).
    - DESISTE (staging) = universo aparte (PRE_RETIRO).

    Regla de calendario (centralizada en settings — ver BUSINESS_RULES):
    - Hasta 17-03-2026 (inclusive): DESISTE se reporta como universo aparte.
    - Desde 18-03-2026: DESISTE se ignora (bajas pasan a Fecha Retiro en matrícula).
    """
    from src.config.settings import BUSINESS_RULES  # import aquí para evitar circular

    snapshot_date    = pd.to_datetime(snapshot_date)
    cutoff_desiste   = pd.to_datetime(BUSINESS_RULES.cutoff_desiste)
    phase            = "PRE_RETIRO" if snapshot_date <= cutoff_desiste else "POST_RETIRO"

    curated_dir = PATHS.curated / "enrollment"
    stg_des_dir = PATHS.staging  / "desiste"
    out_dir     = PATHS.gold / "enrollment"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Base matrícula ──────────────────────────────────────────────
    snap_path = latest_snapshot_file(curated_dir, "enrollment_snapshot__*.parquet")
    log.info(f"Usando snapshot matrícula: {snap_path.name}")

    df = coalesce_duplicates(pd.read_parquet(snap_path))

    if "rut_norm" not in df.columns:
        raise KeyError("No existe 'rut_norm' en el snapshot curated.")

    df["rut_norm"] = df["rut_norm"].fillna("").astype(str).str.strip()
    df = df[df["rut_norm"] != ""].copy()

    df["rut_key"] = rut_key(df["rut_norm"])
    df = df[df["rut_key"] != ""].copy()

    if "fecha_retiro" not in df.columns:
        df["fecha_retiro"] = pd.NaT
    df["fecha_retiro"] = parse_date(df["fecha_retiro"])

    df["retiro_efectivo_al_corte"] = df["fecha_retiro"].notna() & (df["fecha_retiro"] <= snapshot_date)
    df["activo_al_corte"]          = df["fecha_retiro"].isna()  | (df["fecha_retiro"] >  snapshot_date)

    agg = df.groupby("rut_key", dropna=False).agg(
        has_active=(  "activo_al_corte",          "max"),
        has_retiro=(  "retiro_efectivo_al_corte",  "max"),
        n_registros=( "rut_key",                   "size"),
    ).reset_index()

    agg["is_transfer_internal"] = (agg["has_active"] & agg["has_retiro"]).astype(int)
    agg["status_syscol"]        = "RETIRADO"
    agg.loc[agg["has_active"], "status_syscol"] = "MATRICULADO"
    agg["is_retirado_real"] = (
        (agg["status_syscol"] == "RETIRADO") & (agg["is_transfer_internal"] == 0)
    ).astype(int)

    master = pick_one_per_rut(df, snapshot_date=snapshot_date)
    master = master.merge(
        agg[["rut_key", "status_syscol", "is_transfer_internal", "is_retirado_real", "n_registros"]],
        on="rut_key",
        how="left",
    )
    master["snapshot_date"]         = snapshot_date
    master["transfer_internal_flag"] = master["is_transfer_internal"].fillna(0).astype(int)
    master["retirado_real_flag"]     = master["is_retirado_real"].fillna(0).astype(int)
    master["status_master"]          = master["status_syscol"]

    # ── DESISTE ─────────────────────────────────────────────────────
    desiste_path  = None
    desiste_total = 0
    desiste_keys: set[str] = set()

    des_files = sorted(stg_des_dir.glob("desiste_snapshot__*.parquet"))
    if des_files:
        desiste_path = des_files[-1]
        if phase == "PRE_RETIRO":
            log.info(f"Usando DESISTE (PRE_RETIRO): {desiste_path.name}")
        else:
            log.info(f"DESISTE detectado pero se IGNORA (POST_RETIRO): {desiste_path.name}")

        des = pd.read_parquet(desiste_path)
        rut_col = "rut_norm" if "rut_norm" in des.columns else "rut_key" if "rut_key" in des.columns else None
        if rut_col:
            des["rut_key"] = rut_key(des[rut_col].fillna("").astype(str).str.strip())
            desiste_keys  = set(des.loc[des["rut_key"] != "", "rut_key"].unique())
            desiste_total = len(desiste_keys)
        else:
            log.warning("⚠️ DESISTE staging no tiene rut_norm ni rut_key. Se ignora en métricas.")
    else:
        log.info("ℹ️ No hay staging DESISTE. (OK si estás en POST_RETIRO)")

    # ── Métricas ─────────────────────────────────────────────────────
    matricula_rows     = int(master["rut_key"].nunique())
    intersection_count = int(len(desiste_keys.intersection(set(master["rut_key"].unique()))))
    total_control_pre  = str(matricula_rows + desiste_total) if phase == "PRE_RETIRO" else ""

    if intersection_count > 0:
        log.warning(
            f"⚠️ ALERTA: {intersection_count} RUT en común entre matrícula y DESISTE. "
            "En Syscol normalmente deberían ser universos separados."
        )

    metrics = pd.DataFrame([{
        "snapshot_date":            snapshot_date.date().isoformat(),
        "phase":                    phase,
        "snapshot_file":            snap_path.name,
        "desiste_file":             desiste_path.name if desiste_path else "",
        "ruts_unicos_matricula":    matricula_rows,
        "desiste_total":            int(desiste_total),
        "total_esperado_pre_marzo": total_control_pre,
        "desiste_intersection_warn": intersection_count,
        "retirados_syscol":          int((master["status_syscol"] == "RETIRADO").sum()),
        "retirados_reales_syscol":   int(master["retirado_real_flag"].sum()),
        "transferencias_internas_syscol": int(master["transfer_internal_flag"].sum()),
    }])

    # ── Export ───────────────────────────────────────────────────────
    stamp       = snapshot_date.strftime("%Y%m%d")
    out_master  = out_dir / f"enrollment_master__{stamp}.parquet"
    out_metrics = out_dir / f"enrollment_master_metrics__{stamp}.parquet"

    master.to_parquet(out_master, index=False)
    metrics.to_parquet(out_metrics, index=False)
    log.info(f"✅ OK -> {out_master.name}")
    log.info(f"✅ OK -> {out_metrics.name}")
    log.info(metrics.to_string(index=False))

    if export_excel:
        out_xlsx = out_dir / f"enrollment_master__{stamp}.xlsx"
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
            master.to_excel(w, index=False, sheet_name="master")
            metrics.to_excel(w, index=False, sheet_name="metrics")
        log.info(f"✅ Excel -> {out_xlsx.name}")

    return MasterPaths(master_out=out_master, metrics_out=out_metrics)