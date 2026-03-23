from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger

log = get_logger("EWS.enrollment_current")


_TS_RE = re.compile(r"enrollment_snapshot__matricula_snapshot_(\d{8})_(\d{6})", re.IGNORECASE)


def _latest_file(folder: Path, pattern: str) -> Path:
    files = list(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos con patrón: {folder}/{pattern}")

    def key(p: Path):
        m = _TS_RE.search(p.stem)
        if m:
            return (0, m.group(1), m.group(2), 0.0)  # orden por ts del nombre
        return (1, "99999999", "999999", p.stat().st_mtime)  # fallback mtime

    files.sort(key=key)
    return files[-1]


def _normalize_rut(s: pd.Series) -> pd.Series:
    """
    Entrada típica: '12345678-9' o '12.345.678-9'
    Salida para clave: '123456789' (cuerpo + dv) en mayúscula.
    """
    s = s.fillna("").astype(str).str.strip()
    s = s.str.replace(r"[^0-9kK]", "", regex=True).str.upper()
    return s


def _parse_date(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
    dt = dt.mask(dt == pd.Timestamp("1900-01-01"))
    return dt


def _coalesce_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Si el parquet trae columnas duplicadas tipo: X, X.1, X.2,
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


def _pick_one_row_per_rut(df: pd.DataFrame, snapshot_date: pd.Timestamp) -> pd.DataFrame:
    """
    Elige 1 fila representativa por RUT al corte.

    Regla:
      - Si RUT está ACTIVO al corte:
          preferir fecha_retiro NaT (vigente real),
          si no, la fecha_retiro más lejana (pero > corte).
      - Si RUT NO está activo:
          elegir el retiro más reciente (max fecha_retiro <= corte).
    """
    d = df.copy()

    # Flags al corte (ya vienen listos, pero por si acaso)
    d["retiro_efectivo_al_corte"] = d["fecha_retiro"].notna() & (d["fecha_retiro"] <= snapshot_date)
    d["activo_al_corte"] = d["fecha_retiro"].isna() | (d["fecha_retiro"] > snapshot_date)

    # Ranking para elegir
    # - activos primero
    # - dentro de activos: preferir NaT (vigente real)
    # - luego fecha_retiro descendente (más lejos = sigue activo)
    d["_is_nat"] = d["fecha_retiro"].isna().astype(int)

    # Para evitar NaT al ordenar desc: llenamos NaT con fecha muy antigua en la columna auxiliar
    d["_fecha_sort"] = d["fecha_retiro"].fillna(pd.Timestamp("1900-01-01"))

    # Primero escogemos activos con ranking
    active = d[d["activo_al_corte"]].copy()
    active = active.sort_values(
        ["rut", "_is_nat", "_fecha_sort"],
        ascending=[True, False, False],
    ).drop_duplicates("rut", keep="first")

    # Los que no quedaron activos: escoger el retiro más reciente
    retired_pool = d[~d["rut"].isin(active["rut"])].copy()
    retired_pool = retired_pool.sort_values(
        ["rut", "_fecha_sort"],
        ascending=[True, False],
    ).drop_duplicates("rut", keep="first")

    out = pd.concat([active, retired_pool], ignore_index=True)
    out = out.drop(columns=["_is_nat", "_fecha_sort"], errors="ignore")
    return out


# ✅ OJO: esta función DEBE existir con este nombre exacto
def enrollment_current(snapshot_date: str, export_excel: bool = False) -> None:
    """
    Genera tabla GOLD con estado real al corte:
    - matriculados actuales (vigentes)
    - retirados reales
    - transferencias internas Syscol (retiro + activo, mismo rut_norm)

    Asume el MODELO ESTÁNDAR en curated snapshot:
      rut_norm, rut_raw, course_code, fecha_retiro, etc.
    """
    snapshot_date = pd.to_datetime(snapshot_date)

    base = PATHS.curated / "enrollment"
    out_dir = PATHS.gold / "enrollment"
    out_dir.mkdir(parents=True, exist_ok=True)

    latest_snap = _latest_file(base, "enrollment_snapshot__*.parquet")
    log.info(f"Usando snapshot: {latest_snap.name}")

    df_raw = pd.read_parquet(latest_snap)
    df = _coalesce_duplicates(df_raw)

    col_rut_norm = "rut_norm"
    col_retiro = "fecha_retiro"

    if col_rut_norm not in df.columns:
        raise KeyError(f"No encuentro columna '{col_rut_norm}' en snapshot curated.")
    if col_retiro not in df.columns:
        df[col_retiro] = pd.NA

    df["rut"] = _normalize_rut(df[col_rut_norm])
    df = df[df["rut"] != ""].copy()  # ✅ no considerar ruts vacíos

    df["fecha_retiro"] = _parse_date(df[col_retiro])

    # Flags al corte
    df["retiro_efectivo_al_corte"] = df["fecha_retiro"].notna() & (df["fecha_retiro"] <= snapshot_date)
    df["activo_al_corte"] = df["fecha_retiro"].isna() | (df["fecha_retiro"] > snapshot_date)

    # Agregación por rut
    agg = df.groupby("rut", dropna=False).agg(
        has_active=("activo_al_corte", "max"),
        has_retiro=("retiro_efectivo_al_corte", "max"),
        n_registros=("rut", "size"),
    ).reset_index()

    agg["is_transfer_internal"] = (agg["has_active"] & agg["has_retiro"]).astype(int)

    agg["status"] = "RETIRADO"
    agg.loc[agg["has_active"], "status"] = "MATRICULADO"

    agg["is_retirado_real"] = ((agg["status"] == "RETIRADO") & (agg["is_transfer_internal"] == 0)).astype(int)

    # ✅ Elegir 1 fila por rut (robusto)
    cur = _pick_one_row_per_rut(df, snapshot_date)
    cur = cur.merge(
        agg[["rut", "status", "is_transfer_internal", "is_retirado_real", "n_registros"]],
        on="rut",
        how="left",
    )
    cur["snapshot_date"] = snapshot_date

    metrics = pd.DataFrame([{
        "snapshot_date": snapshot_date.date().isoformat(),
        "ruts_unicos": int(agg["rut"].nunique()),
        "matriculados_actuales": int((agg["status"] == "MATRICULADO").sum()),
        "retirados_reales": int((agg["is_retirado_real"] == 1).sum()),
        "transferencias_internas": int((agg["is_transfer_internal"] == 1).sum()),
    }])

    stamp = snapshot_date.strftime("%Y%m%d")
    out_cur = out_dir / f"enrollment_current__{stamp}.parquet"
    out_met = out_dir / f"enrollment_metrics__{stamp}.parquet"

    # ── Agregar direccion desde staging si existe ────────────────────
    stg_dir = PATHS.staging / "matricula"
    stg_files = sorted(stg_dir.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    if stg_files:
        try:
            df_stg = pd.read_parquet(stg_files[-1])
            if "direccion" in df_stg.columns and "rut_norm" in df_stg.columns:
                dir_map = df_stg.drop_duplicates("rut_norm").set_index("rut_norm")["direccion"]
                if "rut_norm" in cur.columns:
                    cur["direccion"] = cur["rut_norm"].map(dir_map).fillna("")
                    log.info(f"✅ Columna 'direccion' agregada desde staging ({cur['direccion'].ne('').sum()} registros)")
            if "dir_calidad" in df_stg.columns and "rut_norm" in df_stg.columns:
                dq_map = df_stg.drop_duplicates("rut_norm").set_index("rut_norm")["dir_calidad"]
                if "rut_norm" in cur.columns:
                    cur["dir_calidad"] = cur["rut_norm"].map(dq_map).fillna("")
        except Exception as e:
            log.warning(f"No se pudo agregar direccion desde staging: {e}")

    cur.to_parquet(out_cur, index=False)
    metrics.to_parquet(out_met, index=False)

    log.info(f"OK -> {out_cur.name}")
    log.info(f"OK -> {out_met.name}")
    log.info(metrics.to_string(index=False))

    if export_excel:
        out_xlsx = out_dir / f"enrollment_current__{stamp}.xlsx"
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
            cur.to_excel(w, index=False, sheet_name="enrollment_current")
            metrics.to_excel(w, index=False, sheet_name="metrics")
        log.info(f"OK -> {out_xlsx.name}")


if __name__ == "__main__":
    enrollment_current(snapshot_date="2026-03-02", export_excel=False)