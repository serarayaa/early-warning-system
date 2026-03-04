# src/gold/enrollment_status.py
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger

log = get_logger("EWS.enrollment_status")


@dataclass(frozen=True)
class StatusOutputs:
    latest_excel: Optional[Path]
    transfers_parquet: Optional[Path]
    transfers_excel: Optional[Path]


_TS_RE = re.compile(r"matricula_snapshot_(\d{8})_(\d{6})", re.IGNORECASE)


def _latest_by_mtime(folder: Path, pattern: str) -> Path:
    files = list(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos: {folder}/{pattern}")
    return max(files, key=lambda p: p.stat().st_mtime)


def _parse_diff_pair(diff_path: Path) -> Tuple[str, str]:
    """
    Espera: enrollment_diff__<prev>__to__<curr>.parquet
    Retorna: (prev_snapshot_name, curr_snapshot_name) SIN extensión.
    """
    m = re.match(r"enrollment_diff__(.+?)__to__(.+?)\.parquet$", diff_path.name)
    if not m:
        raise ValueError(f"No pude parsear prev/curr desde diff: {diff_path.name}")
    prev_name = m.group(1).strip()
    curr_name = m.group(2).strip()
    return prev_name, curr_name


def _ensure_parquet_stem(name: str) -> str:
    return name[:-8] if name.lower().endswith(".parquet") else name


def _stamp_from_snapshot_name(snapshot_stem: str) -> str:
    """
    Intenta sacar YYYYMMDDHHMMSS desde matricula_snapshot_YYYYMMDD_HHMMSS.
    Si no puede, usa YYYYMMDD actual.
    """
    m = _TS_RE.search(snapshot_stem)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return pd.Timestamp.today().strftime("%Y%m%d")


def _rut_key(series: pd.Series) -> pd.Series:
    """
    Key estándar: solo dígitos + K, sin guion ni puntos.
    """
    s = series.fillna("").astype(str).str.strip().str.upper()
    return s.str.replace(r"[^0-9K]", "", regex=True)


def _pick_representative_per_rut(df: pd.DataFrame) -> pd.DataFrame:
    """
    Elegimos 1 fila representativa por rut_key en cada snapshot.
    - prioriza registro activo (fecha_retiro NaT)
    - si hay múltiples activos, toma el primero ordenado por rut_key
    - si no hay activo, toma el retiro más reciente
    """
    df = df.copy()

    if "rut_norm" not in df.columns:
        raise KeyError("Falta columna rut_norm en snapshot.")

    df["rut_norm"] = df["rut_norm"].fillna("").astype(str).str.strip()
    df["rut_key"] = _rut_key(df["rut_norm"])
    df = df[df["rut_key"] != ""].copy()

    if "fecha_retiro" in df.columns:
        df["fecha_retiro"] = pd.to_datetime(df["fecha_retiro"], errors="coerce", dayfirst=True)
        df["_activo"] = df["fecha_retiro"].isna().astype(int)
        # Activos primero, luego por fecha_retiro desc (si existe)
        df["_fecha_sort"] = df["fecha_retiro"].fillna(pd.Timestamp("1900-01-01"))
        df = df.sort_values(["rut_key", "_activo", "_fecha_sort"], ascending=[True, False, False])
        return df.drop_duplicates("rut_key", keep="first").drop(columns=["_activo", "_fecha_sort"])

    df = df.sort_values(["rut_key"], ascending=True)
    return df.drop_duplicates("rut_key", keep="first")


def _load_prev_curr_from_latest_diff() -> Tuple[pd.DataFrame, pd.DataFrame, str, str, str]:
    """
    Lee el último diff y carga los staging prev/curr correspondientes.
    Retorna: (df_prev, df_curr, prev_stem, curr_stem, stamp)
    """
    curated_dir = PATHS.curated / "enrollment"
    stg_matr_dir = PATHS.staging / "matricula"

    diff_path = _latest_by_mtime(curated_dir, "enrollment_diff__*.parquet")
    prev_name, curr_name = _parse_diff_pair(diff_path)

    prev_stem = _ensure_parquet_stem(prev_name)
    curr_stem = _ensure_parquet_stem(curr_name)

    prev_path = (stg_matr_dir / f"{prev_stem}.parquet").resolve()
    curr_path = (stg_matr_dir / f"{curr_stem}.parquet").resolve()

    if not prev_path.exists():
        raise FileNotFoundError(f"No existe staging previo: {prev_path}")
    if not curr_path.exists():
        raise FileNotFoundError(f"No existe staging actual: {curr_path}")

    df_prev = pd.read_parquet(prev_path)
    df_curr = pd.read_parquet(curr_path)

    stamp = _stamp_from_snapshot_name(curr_stem)
    return df_prev, df_curr, prev_stem, curr_stem, stamp


def _best_name_series(df: pd.DataFrame) -> pd.Series:
    if "nombre" in df.columns:
        return df["nombre"].fillna("").astype(str).str.strip()
    if "nombre_raw" in df.columns:
        return df["nombre_raw"].fillna("").astype(str).str.strip()
    return pd.Series([""] * len(df), index=df.index)


def _build_transfers_pre(df_prev: pd.DataFrame, df_curr: pd.DataFrame, prev_stem: str, curr_stem: str) -> pd.DataFrame:
    """
    PRE-18mar: transferencia directa (mismo rut, cambia course_code entre snapshots).
    """
    prev_pick = _pick_representative_per_rut(df_prev)
    curr_pick = _pick_representative_per_rut(df_curr)

    for need in ["rut_norm", "rut_key", "course_code"]:
        if need not in prev_pick.columns or need not in curr_pick.columns:
            raise KeyError(f"Falta columna '{need}' en staging matrícula (prev o curr).")

    prev_slim = prev_pick[["rut_norm", "rut_key", "course_code"]].rename(columns={"course_code": "course_from"})
    curr_slim = curr_pick[["rut_norm", "rut_key", "course_code"]].rename(columns={"course_code": "course_to"})

    # nombre: preferir curr; si vacío, fallback a prev
    curr_names = pd.DataFrame({"rut_key": curr_pick["rut_key"], "nombre": _best_name_series(curr_pick)})
    prev_names = pd.DataFrame({"rut_key": prev_pick["rut_key"], "nombre_prev": _best_name_series(prev_pick)})

    merged = (
        prev_slim.merge(curr_slim, on="rut_key", how="inner", suffixes=("_prev", "_curr"))
        .merge(curr_names, on="rut_key", how="left")
        .merge(prev_names, on="rut_key", how="left")
    )

    merged["course_from"] = merged["course_from"].fillna("").astype(str).str.strip()
    merged["course_to"] = merged["course_to"].fillna("").astype(str).str.strip()

    merged["nombre"] = merged["nombre"].fillna("").astype(str).str.strip()
    merged["nombre_prev"] = merged["nombre_prev"].fillna("").astype(str).str.strip()
    merged.loc[merged["nombre"] == "", "nombre"] = merged["nombre_prev"]

    # rut a exportar: priorizar formato del curr, si no, prev
    merged["rut_norm_out"] = merged["rut_norm_curr"].fillna("").astype(str).str.strip()
    merged.loc[merged["rut_norm_out"] == "", "rut_norm_out"] = merged["rut_norm_prev"].fillna("").astype(str).str.strip()

    out = merged[
        (merged["course_from"] != "")
        & (merged["course_to"] != "")
        & (merged["course_from"] != merged["course_to"])
    ].copy()

    out["transfer_type"] = "PRE_DIRECT"
    out["snapshot_prev"] = prev_stem
    out["snapshot_curr"] = curr_stem

    cols = ["rut_norm_out", "rut_key", "nombre", "course_from", "course_to", "transfer_type", "snapshot_prev", "snapshot_curr"]
    out = out[cols].rename(columns={"rut_norm_out": "rut_norm"})
    out = out.sort_values(["course_from", "course_to", "nombre", "rut_key"], ascending=True)
    return out


def _build_transfers_post(df_curr: pd.DataFrame, curr_stem: str) -> pd.DataFrame:
    """
    POST-18mar: Syscol duplica + una fila queda retirada y otra activa, en el MISMO snapshot.
    Detectamos por rut_key con:
      - n_registros >= 2
      - existe activo (fecha_retiro NaT) y retirado (fecha_retiro notna)
      - course_code distinto entre activo vs retirado
    """
    df = df_curr.copy()

    if "rut_norm" not in df.columns or "course_code" not in df.columns:
        raise KeyError("Staging curr debe tener rut_norm y course_code para detectar POST transfer.")

    df["rut_norm"] = df["rut_norm"].fillna("").astype(str).str.strip()
    df["rut_key"] = _rut_key(df["rut_norm"])
    df = df[df["rut_key"] != ""].copy()

    if "fecha_retiro" not in df.columns:
        return pd.DataFrame(columns=["rut_norm", "rut_key", "nombre", "course_from", "course_to", "transfer_type", "snapshot_prev", "snapshot_curr"])

    df["fecha_retiro"] = pd.to_datetime(df["fecha_retiro"], errors="coerce", dayfirst=True)
    df["_activo"] = df["fecha_retiro"].isna()

    dup = df.groupby("rut_key").size()
    dup_keys = dup[dup >= 2].index
    d = df[df["rut_key"].isin(dup_keys)].copy()
    if d.empty:
        return pd.DataFrame(columns=["rut_norm", "rut_key", "nombre", "course_from", "course_to", "transfer_type", "snapshot_prev", "snapshot_curr"])

    # Tomar 1 activo y 1 retirado por rut_key
    act = (
        d[d["_activo"]]
        .sort_values(["rut_key"], ascending=True)
        .drop_duplicates("rut_key", keep="first")
        .rename(columns={"course_code": "course_to"})
    )
    ret = (
        d[~d["_activo"]]
        .sort_values(["rut_key", "fecha_retiro"], ascending=[True, False])
        .drop_duplicates("rut_key", keep="first")
        .rename(columns={"course_code": "course_from"})
    )

    out = ret[["rut_key", "course_from"]].merge(act[["rut_key", "course_to"]], on="rut_key", how="inner")

    # nombre: preferir el del activo
    if "nombre" in act.columns:
        out = out.merge(act[["rut_key", "nombre"]], on="rut_key", how="left")
    elif "nombre" in ret.columns:
        out = out.merge(ret[["rut_key", "nombre"]], on="rut_key", how="left")
    else:
        out["nombre"] = ""

    # rut_norm: exportar el del activo si existe
    if "rut_norm" in act.columns:
        out = out.merge(act[["rut_key", "rut_norm"]], on="rut_key", how="left")
    elif "rut_norm" in ret.columns:
        out = out.merge(ret[["rut_key", "rut_norm"]], on="rut_key", how="left")
    else:
        out["rut_norm"] = ""

    out["course_from"] = out["course_from"].fillna("").astype(str).str.strip()
    out["course_to"] = out["course_to"].fillna("").astype(str).str.strip()
    out["nombre"] = out["nombre"].fillna("").astype(str).str.strip()
    out["rut_norm"] = out["rut_norm"].fillna("").astype(str).str.strip()

    out = out[
        (out["course_from"] != "")
        & (out["course_to"] != "")
        & (out["course_from"] != out["course_to"])
    ].copy()

    out["transfer_type"] = "POST_DUP_RETIRO"
    out["snapshot_prev"] = ""
    out["snapshot_curr"] = curr_stem

    cols = ["rut_norm", "rut_key", "nombre", "course_from", "course_to", "transfer_type", "snapshot_prev", "snapshot_curr"]
    out = out[cols].sort_values(["course_from", "course_to", "nombre", "rut_key"], ascending=True)
    return out


def enrollment_status(export_excel: bool = True) -> StatusOutputs:
    """
    Reporte auditoría (diff) + reporte robusto de transferencias:
      - PRE_DIRECT: cambio de course_code entre snapshots (misma persona)
      - POST_DUP_RETIRO: duplicado en mismo snapshot (retiro+activo) con course distinto
    """
    curated_dir = PATHS.curated / "enrollment"
    gold_dir = PATHS.gold / "enrollment"
    gold_dir.mkdir(parents=True, exist_ok=True)

    # ==========================
    # 0) CURATED SNAPSHOT LATEST (FUENTE VERDAD del día)
    # ==========================
    curated_snap = _latest_by_mtime(curated_dir, "enrollment_snapshot__*.parquet")
    df_snap = pd.read_parquet(curated_snap)

    if "rut_norm" in df_snap.columns:
        ruts_unicos_curr = int(
            df_snap["rut_norm"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique()
        )
        log.info(f"📌 RUT únicos en snapshot ACTUAL (curated): {ruts_unicos_curr}")
        log.info(f"📌 Curated usado por status: {curated_snap.name}")
    else:
        log.info("📌 (Curated snapshot no trae rut_norm)")

    # ==========================
    # 1) STATUS (diff)
    # ==========================
    diff_path = _latest_by_mtime(curated_dir, "enrollment_diff__*.parquet")
    df_diff = pd.read_parquet(diff_path)

    if "rut_norm" in df_diff.columns:
        ruts_unicos_diff = int(df_diff["rut_norm"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique())
        log.info(f"🧾 RUT únicos involucrados en DIFF: {ruts_unicos_diff}")
    else:
        log.info("🧾 (Diff no trae rut_norm)")

    log.info("ℹ️ Nota: vigencia/retiros/transferencias Syscol se calculan en gold/enrollment_current.py")

    change_col = "change_type" if "change_type" in df_diff.columns else None
    if change_col:
        resumen = df_diff[change_col].value_counts(dropna=False).to_dict()
        log.info(f"🧾 Cambios vs snapshot anterior: {resumen}")
    else:
        log.info("🧾 (Diff no trae change_type)")

    if change_col and "course_from" in df_diff.columns and "course_to" in df_diff.columns:
        hint = int(((df_diff[change_col] == "UPDATED") & (df_diff["course_from"] != df_diff["course_to"])).sum())
        log.info(f"🔁 Hint transfer PRE por diff (UPDATED con cambio curso): {hint}")

    latest_excel: Optional[Path] = (gold_dir / "enrollment_status_latest.xlsx").resolve() if export_excel else None

    # ==========================
    # 2) TRANSFERENCIAS (PRE + POST)
    # ==========================
    transfers_parquet: Optional[Path] = None
    transfers_excel: Optional[Path] = None

    try:
        df_prev, df_curr, prev_stem, curr_stem, stamp = _load_prev_curr_from_latest_diff()

        transfers_pre = _build_transfers_pre(df_prev, df_curr, prev_stem, curr_stem)
        transfers_post = _build_transfers_post(df_curr, curr_stem)
        transfers_all = pd.concat([transfers_pre, transfers_post], ignore_index=True)

        out_pre_pq = (gold_dir / f"enrollment_transfers_pre__{stamp}.parquet").resolve()
        out_post_pq = (gold_dir / f"enrollment_transfers_post__{stamp}.parquet").resolve()
        out_all_pq = (gold_dir / f"enrollment_transfers_all__{stamp}.parquet").resolve()

        transfers_pre.to_parquet(out_pre_pq, index=False)
        transfers_post.to_parquet(out_post_pq, index=False)
        transfers_all.to_parquet(out_all_pq, index=False)

        log.info(f"✅ Transfer PRE -> {out_pre_pq.name} (rows={len(transfers_pre)})")
        log.info(f"✅ Transfer POST -> {out_post_pq.name} (rows={len(transfers_post)})")
        log.info(f"✅ Transfer ALL -> {out_all_pq.name} (rows={len(transfers_all)})")

        transfers_parquet = out_all_pq

        if export_excel:
            out_pre_x = (gold_dir / f"enrollment_transfers_pre__{stamp}.xlsx").resolve()
            out_post_x = (gold_dir / f"enrollment_transfers_post__{stamp}.xlsx").resolve()
            out_all_x = (gold_dir / f"enrollment_transfers_all__{stamp}.xlsx").resolve()

            with pd.ExcelWriter(out_pre_x, engine="openpyxl") as w:
                transfers_pre.to_excel(w, index=False, sheet_name="transfer_pre")
            with pd.ExcelWriter(out_post_x, engine="openpyxl") as w:
                transfers_post.to_excel(w, index=False, sheet_name="transfer_post")
            with pd.ExcelWriter(out_all_x, engine="openpyxl") as w:
                transfers_all.to_excel(w, index=False, sheet_name="transfer_all")

            log.info(f"✅ Transfer PRE Excel -> {out_pre_x.name}")
            log.info(f"✅ Transfer POST Excel -> {out_post_x.name}")
            log.info(f"✅ Transfer ALL Excel -> {out_all_x.name}")

            transfers_excel = out_all_x

            if latest_excel:
                with pd.ExcelWriter(latest_excel, engine="openpyxl") as w:
                    df_diff.to_excel(w, index=False, sheet_name="diff_latest")
                    transfers_pre.to_excel(w, index=False, sheet_name="transfer_pre")
                    transfers_post.to_excel(w, index=False, sheet_name="transfer_post")
                    transfers_all.to_excel(w, index=False, sheet_name="transfer_all")
                log.info("🧩 status_latest.xlsx actualizado con hojas de transferencias")

    except Exception as e:
        log.warning(f"⚠️ No pude generar transferencias (PRE/POST): {e}")

    # ==========================
    # 3) STATUS XLSX (si no lo escribimos arriba)
    # ==========================
    if export_excel and latest_excel and not latest_excel.exists():
        with pd.ExcelWriter(latest_excel, engine="openpyxl") as w:
            df_diff.to_excel(w, index=False, sheet_name="diff_latest")
        log.info(f"✅ Excel generado: {latest_excel}")

    return StatusOutputs(
        latest_excel=latest_excel,
        transfers_parquet=transfers_parquet,
        transfers_excel=transfers_excel,
    )