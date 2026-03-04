from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger

log = get_logger("EWS.enrollment_master")


@dataclass(frozen=True)
class MasterPaths:
    master_out: Path
    metrics_out: Path


_TS_RE = re.compile(r"enrollment_snapshot__matricula_snapshot_(\d{8})_(\d{6})", re.IGNORECASE)


def _latest_file(folder: Path, pattern: str) -> Path:
    files = list(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos con patrón: {folder}/{pattern}")

    def key(p: Path):
        m = _TS_RE.search(p.stem)
        if m:
            return (0, m.group(1), m.group(2), 0.0)  # por timestamp del nombre
        return (1, "99999999", "999999", p.stat().st_mtime)  # fallback mtime

    files.sort(key=key)
    return files[-1]


def _parse_date(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
    dt = dt.mask(dt == pd.Timestamp("1900-01-01"))
    return dt


def _coalesce_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Si el parquet trae columnas duplicadas tipo: Nombre, Nombre.1, ...
    nos quedamos con la primera no nula (coalesce).
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    groups: dict[str, list[str]] = {}
    for c in df.columns:
        base = c.split(".")[0].strip()
        groups.setdefault(base, []).append(c)

    out = pd.DataFrame(index=df.index)
    for base, cols in groups.items():
        if len(cols) == 1:
            out[base] = df[cols[0]]
        else:
            out[base] = df[cols].bfill(axis=1).iloc[:, 0]
    return out


def _rut_key(series: pd.Series) -> pd.Series:
    """
    Key estándar para comparar/mergear: solo dígitos + K, sin guion.
    Entrada típica: '12345678-9' / '12.345.678-9' / '123456789'
    Salida: '123456789'
    """
    s = series.fillna("").astype(str).str.strip().str.upper()
    s = s.str.replace(r"[^0-9K]", "", regex=True)
    return s


def _pick_one_row_per_rut(df: pd.DataFrame, snapshot_date: pd.Timestamp) -> pd.DataFrame:
    """
    Elige 1 fila representativa por rut_key al corte.
    - Si hay activo al corte: preferir fecha_retiro NaT, luego la más lejana (> corte)
    - Si no hay activo: el retiro más reciente (max fecha_retiro <= corte)
    """
    d = df.copy()

    d["retiro_efectivo_al_corte"] = d["fecha_retiro"].notna() & (d["fecha_retiro"] <= snapshot_date)
    d["activo_al_corte"] = d["fecha_retiro"].isna() | (d["fecha_retiro"] > snapshot_date)

    d["_is_nat"] = d["fecha_retiro"].isna().astype(int)
    d["_fecha_sort"] = d["fecha_retiro"].fillna(pd.Timestamp("1900-01-01"))

    active = d[d["activo_al_corte"]].copy()
    active = active.sort_values(
        ["rut_key", "_is_nat", "_fecha_sort"],
        ascending=[True, False, False],
    ).drop_duplicates("rut_key", keep="first")

    retired_pool = d[~d["rut_key"].isin(active["rut_key"])].copy()
    retired_pool = retired_pool.sort_values(
        ["rut_key", "_fecha_sort"],
        ascending=[True, False],
    ).drop_duplicates("rut_key", keep="first")

    out = pd.concat([active, retired_pool], ignore_index=True)
    out = out.drop(columns=["_is_nat", "_fecha_sort"], errors="ignore")
    return out


def enrollment_master(snapshot_date: str, export_excel: bool = False) -> MasterPaths:
    """
    MASTER de matrícula (regla Syscol):
    - Matricula (curated enrollment_snapshot) = “Matriculados Syscol” (Syscol ya excluye DESISTE).
    - DESISTE (staging) = universo aparte (PRE_RETIRO).

    Regla de calendario:
    - Hasta 17-03-2026 (inclusive): DESISTE se reporta como universo aparte.
    - Desde 18-03-2026: DESISTE se ignora (bajas pasan a Fecha Retiro en matrícula).
    """
    snapshot_date = pd.to_datetime(snapshot_date)
    cutoff_desiste = pd.to_datetime("2026-03-17")
    phase = "PRE_RETIRO" if snapshot_date <= cutoff_desiste else "POST_RETIRO"

    curated_dir = PATHS.curated / "enrollment"
    stg_des_dir = PATHS.staging / "desiste"
    out_dir = PATHS.gold / "enrollment"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- Base matrícula (curated snapshot) ----------
    snap_path = _latest_file(curated_dir, "enrollment_snapshot__*.parquet")
    log.info(f"Usando snapshot matrícula: {snap_path.name}")

    df_raw = pd.read_parquet(snap_path)
    df = _coalesce_duplicates(df_raw)

    if "rut_norm" not in df.columns:
        raise KeyError("No existe 'rut_norm' en el snapshot curated. Revisa staging matrícula.")

    df["rut_norm"] = df["rut_norm"].fillna("").astype(str).str.strip()
    df = df[df["rut_norm"] != ""].copy()

    # ✅ key estándar para todo lo lógico
    df["rut_key"] = _rut_key(df["rut_norm"])
    df = df[df["rut_key"] != ""].copy()

    # Fecha retiro (cuando Syscol la traiga poblada)
    if "fecha_retiro" not in df.columns:
        df["fecha_retiro"] = pd.NaT
    df["fecha_retiro"] = _parse_date(df["fecha_retiro"])

    # Flags al corte
    df["retiro_efectivo_al_corte"] = df["fecha_retiro"].notna() & (df["fecha_retiro"] <= snapshot_date)
    df["activo_al_corte"] = df["fecha_retiro"].isna() | (df["fecha_retiro"] > snapshot_date)

    # Agregación por rut_key (para transferencias internas)
    agg = df.groupby("rut_key", dropna=False).agg(
        has_active=("activo_al_corte", "max"),
        has_retiro=("retiro_efectivo_al_corte", "max"),
        n_registros=("rut_key", "size"),
    ).reset_index()

    agg["is_transfer_internal"] = (agg["has_active"] & agg["has_retiro"]).astype(int)
    agg["status_syscol"] = "RETIRADO"
    agg.loc[agg["has_active"], "status_syscol"] = "MATRICULADO"
    agg["is_retirado_real"] = ((agg["status_syscol"] == "RETIRADO") & (agg["is_transfer_internal"] == 0)).astype(int)

    # ✅ Elegir 1 fila por rut_key (representativa)
    master = _pick_one_row_per_rut(df, snapshot_date)
    master = master.merge(
        agg[["rut_key", "status_syscol", "is_transfer_internal", "is_retirado_real", "n_registros"]],
        on="rut_key",
        how="left",
    )
    master["snapshot_date"] = snapshot_date

    # Etiquetas Syscol
    master["transfer_internal_flag"] = master["is_transfer_internal"].fillna(0).astype(int)
    master["retirado_real_flag"] = master["is_retirado_real"].fillna(0).astype(int)

    # status_master: igual Syscol (no se pisa con DESISTE)
    master["status_master"] = master["status_syscol"]

    # ---------- DESISTE (último staging) ----------
    desiste_path = None
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
        if "rut_norm" in des.columns:
            des["rut_norm"] = des["rut_norm"].fillna("").astype(str).str.strip()
            des["rut_key"] = _rut_key(des["rut_norm"])
            desiste_keys = set(des.loc[des["rut_key"] != "", "rut_key"].unique().tolist())
            desiste_total = len(desiste_keys)
        elif "rut_key" in des.columns:
            des["rut_key"] = _rut_key(des["rut_key"])
            desiste_keys = set(des.loc[des["rut_key"] != "", "rut_key"].unique().tolist())
            desiste_total = len(desiste_keys)
        else:
            log.warning("⚠️ DESISTE staging no tiene rut_norm ni rut_key. Se ignora en métricas.")
            desiste_keys = set()
            desiste_total = 0
    else:
        log.info("ℹ️ No hay staging DESISTE. (OK si estás en POST_RETIRO)")

    # ---------- Métricas y controles ----------
    matricula_rows = int(master["rut_key"].nunique())

    intersection_count = int(len(desiste_keys.intersection(set(master["rut_key"].unique().tolist()))))

    total_control_pre = ""
    if phase == "PRE_RETIRO":
        total_control_pre = str(matricula_rows + desiste_total)

    metrics = pd.DataFrame([{
        "snapshot_date": snapshot_date.date().isoformat(),
        "phase": phase,

        "snapshot_file": snap_path.name,
        "desiste_file": desiste_path.name if desiste_path else "",

        "ruts_unicos_matricula": matricula_rows,
        "desiste_total": int(desiste_total),
        "total_esperado_pre_marzo": total_control_pre,

        "desiste_intersection_warn": intersection_count,

        "retirados_syscol": int((master["status_syscol"] == "RETIRADO").sum()),
        "retirados_reales_syscol": int(master["retirado_real_flag"].sum()),
        "transferencias_internas_syscol": int(master["transfer_internal_flag"].sum()),
    }])

    if intersection_count > 0:
        log.warning(
            f"⚠️ ALERTA: Hay {intersection_count} RUT en común entre matrícula y DESISTE. "
            f"En Syscol normalmente deberían ser universos separados."
        )

    # ---------- Export ----------
    stamp = snapshot_date.strftime("%Y%m%d")
    out_master = out_dir / f"enrollment_master__{stamp}.parquet"
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