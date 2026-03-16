from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger
from src.utils.transforms import pick_one_per_rut, rut_key

log = get_logger("EWS.enrollment_status")


@dataclass(frozen=True)
class StatusOutputs:
    latest_excel:      Optional[Path]
    transfers_parquet: Optional[Path]
    transfers_excel:   Optional[Path]


_TS_RE = re.compile(r"matricula_snapshot_(\d{8})_(\d{6})", re.IGNORECASE)


# ---------------------------------------------------------------------
# Helpers locales (lógica propia de status)
# ---------------------------------------------------------------------

def _latest_by_mtime(folder: Path, pattern: str) -> Path:
    files = list(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos: {folder}/{pattern}")
    return max(files, key=lambda p: p.stat().st_mtime)


def _parse_diff_pair(diff_path: Path) -> Tuple[str, str]:
    m = re.match(r"enrollment_diff__(.+?)__to__(.+?)\.parquet$", diff_path.name)
    if not m:
        raise ValueError(f"No pude parsear prev/curr desde diff: {diff_path.name}")
    return m.group(1).strip(), m.group(2).strip()


def _ensure_parquet_stem(name: str) -> str:
    return name[:-8] if name.lower().endswith(".parquet") else name


def _stamp_from_snapshot_name(snapshot_stem: str) -> str:
    m = _TS_RE.search(snapshot_stem)
    return f"{m.group(1)}{m.group(2)}" if m else pd.Timestamp.today().strftime("%Y%m%d")


def _load_prev_curr_from_latest_diff() -> Tuple[pd.DataFrame, pd.DataFrame, str, str, str]:
    curated_dir    = PATHS.curated / "enrollment"
    stg_matr_dir   = PATHS.staging  / "matricula"

    diff_path  = _latest_by_mtime(curated_dir, "enrollment_diff__*.parquet")
    prev_name, curr_name = _parse_diff_pair(diff_path)
    prev_stem  = _ensure_parquet_stem(prev_name)
    curr_stem  = _ensure_parquet_stem(curr_name)

    prev_path  = (stg_matr_dir / f"{prev_stem}.parquet").resolve()
    curr_path  = (stg_matr_dir / f"{curr_stem}.parquet").resolve()

    if not prev_path.exists():
        raise FileNotFoundError(f"No existe staging previo: {prev_path}")
    if not curr_path.exists():
        raise FileNotFoundError(f"No existe staging actual: {curr_path}")

    stamp = _stamp_from_snapshot_name(curr_stem)
    return pd.read_parquet(prev_path), pd.read_parquet(curr_path), prev_stem, curr_stem, stamp


def _best_name_series(df: pd.DataFrame) -> pd.Series:
    for col in ["nombre", "nombre_raw"]:
        if col in df.columns:
            return df[col].fillna("").astype(str).str.strip()
    return pd.Series([""] * len(df), index=df.index)


def _build_transfers_pre(
    df_prev: pd.DataFrame, df_curr: pd.DataFrame, prev_stem: str, curr_stem: str
) -> pd.DataFrame:
    """
    PRE-18mar: transferencia directa — mismo rut, cambia course_code entre snapshots.
    """
    prev_pick = pick_one_per_rut(df_prev)
    curr_pick = pick_one_per_rut(df_curr)

    # pick_one_per_rut puede haber eliminado rut_key si no estaba; lo regeneramos
    for df_ in [prev_pick, curr_pick]:
        if "rut_key" not in df_.columns:
            df_["rut_key"] = rut_key(df_["rut_norm"])

    for need in ["rut_norm", "rut_key", "course_code"]:
        if need not in prev_pick.columns or need not in curr_pick.columns:
            raise KeyError(f"Falta columna '{need}' en staging matrícula (prev o curr).")

    prev_slim   = prev_pick[["rut_norm", "rut_key", "course_code"]].rename(columns={"course_code": "course_from"})
    curr_slim   = curr_pick[["rut_norm", "rut_key", "course_code"]].rename(columns={"course_code": "course_to"})
    curr_names  = pd.DataFrame({"rut_key": curr_pick["rut_key"], "nombre": _best_name_series(curr_pick)})
    prev_names  = pd.DataFrame({"rut_key": prev_pick["rut_key"], "nombre_prev": _best_name_series(prev_pick)})

    merged = (
        prev_slim
        .merge(curr_slim,  on="rut_key", how="inner", suffixes=("_prev", "_curr"))
        .merge(curr_names, on="rut_key", how="left")
        .merge(prev_names, on="rut_key", how="left")
    )

    for col in ["course_from", "course_to", "nombre", "nombre_prev"]:
        merged[col] = merged[col].fillna("").astype(str).str.strip()

    merged.loc[merged["nombre"] == "", "nombre"] = merged["nombre_prev"]

    merged["rut_norm_out"] = merged["rut_norm_curr"].fillna("").astype(str).str.strip()
    merged.loc[merged["rut_norm_out"] == "", "rut_norm_out"] = merged["rut_norm_prev"].fillna("").astype(str).str.strip()

    out = merged[
        (merged["course_from"] != "")
        & (merged["course_to"]   != "")
        & (merged["course_from"] != merged["course_to"])
    ].copy()

    out["transfer_type"]  = "PRE_DIRECT"
    out["snapshot_prev"]  = prev_stem
    out["snapshot_curr"]  = curr_stem

    return (
        out[["rut_norm_out", "rut_key", "nombre", "course_from", "course_to", "transfer_type", "snapshot_prev", "snapshot_curr"]]
        .rename(columns={"rut_norm_out": "rut_norm"})
        .sort_values(["course_from", "course_to", "nombre", "rut_key"])
    )


def _build_transfers_post(df_curr: pd.DataFrame, curr_stem: str) -> pd.DataFrame:
    """
    POST-18mar: Syscol duplica fila → una queda retirada, otra activa en el MISMO snapshot.
    """
    _EMPTY = pd.DataFrame(columns=["rut_norm", "rut_key", "nombre", "course_from", "course_to", "transfer_type", "snapshot_prev", "snapshot_curr"])

    df = df_curr.copy()
    if "rut_norm" not in df.columns or "course_code" not in df.columns:
        raise KeyError("Staging curr debe tener rut_norm y course_code para detectar POST transfer.")

    df["rut_norm"] = df["rut_norm"].fillna("").astype(str).str.strip()
    df["rut_key"]  = rut_key(df["rut_norm"])
    df = df[df["rut_key"] != ""].copy()

    if "fecha_retiro" not in df.columns:
        return _EMPTY

    df["fecha_retiro"] = pd.to_datetime(df["fecha_retiro"], errors="coerce", dayfirst=True)
    df["_activo"]      = df["fecha_retiro"].isna()

    dup_keys = df.groupby("rut_key").size()
    dup_keys = dup_keys[dup_keys >= 2].index
    d = df[df["rut_key"].isin(dup_keys)].copy()
    if d.empty:
        return _EMPTY

    act = (
        d[d["_activo"]]
        .sort_values("rut_key")
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

    name_src = act if "nombre" in act.columns else ret if "nombre" in ret.columns else None
    if name_src is not None:
        out = out.merge(name_src[["rut_key", "nombre"]], on="rut_key", how="left")
    else:
        out["nombre"] = ""

    rut_src = act if "rut_norm" in act.columns else ret if "rut_norm" in ret.columns else None
    if rut_src is not None:
        out = out.merge(rut_src[["rut_key", "rut_norm"]], on="rut_key", how="left")
    else:
        out["rut_norm"] = ""

    for col in ["course_from", "course_to", "nombre", "rut_norm"]:
        out[col] = out[col].fillna("").astype(str).str.strip()

    out = out[
        (out["course_from"] != "")
        & (out["course_to"]   != "")
        & (out["course_from"] != out["course_to"])
    ].copy()

    out["transfer_type"] = "POST_DUP_RETIRO"
    out["snapshot_prev"] = ""
    out["snapshot_curr"] = curr_stem

    return (
        out[["rut_norm", "rut_key", "nombre", "course_from", "course_to", "transfer_type", "snapshot_prev", "snapshot_curr"]]
        .sort_values(["course_from", "course_to", "nombre", "rut_key"])
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def enrollment_status(export_excel: bool = True) -> StatusOutputs:
    curated_dir = PATHS.curated / "enrollment"
    gold_dir    = PATHS.gold    / "enrollment"
    gold_dir.mkdir(parents=True, exist_ok=True)

    # 0) Snapshot curado del día
    curated_snap = _latest_by_mtime(curated_dir, "enrollment_snapshot__*.parquet")
    df_snap      = pd.read_parquet(curated_snap)
    if "rut_norm" in df_snap.columns:
        ruts_unicos_curr = int(
            df_snap["rut_norm"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique()
        )
        log.info(f"📌 RUT únicos en snapshot ACTUAL (curated): {ruts_unicos_curr}")
        log.info(f"📌 Curated usado por status: {curated_snap.name}")

    # 1) Diff
    diff_path = _latest_by_mtime(curated_dir, "enrollment_diff__*.parquet")
    df_diff   = pd.read_parquet(diff_path)

    if "rut_norm" in df_diff.columns:
        ruts_diff = int(df_diff["rut_norm"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique())
        log.info(f"🧾 RUT únicos en DIFF: {ruts_diff}")

    log.info("ℹ️ Vigencia/retiros/transferencias Syscol se calculan en gold/enrollment_current.py")

    if "change_type" in df_diff.columns:
        log.info(f"🧾 Cambios vs snapshot anterior: {df_diff['change_type'].value_counts(dropna=False).to_dict()}")
        if "course_from" in df_diff.columns and "course_to" in df_diff.columns:
            hint = int(((df_diff["change_type"] == "UPDATED") & (df_diff["course_from"] != df_diff["course_to"])).sum())
            log.info(f"🔁 Hint transfer PRE por diff: {hint}")

    latest_excel: Optional[Path] = (gold_dir / "enrollment_status_latest.xlsx").resolve() if export_excel else None

    # 2) Transferencias
    transfers_parquet: Optional[Path] = None
    transfers_excel:   Optional[Path] = None

    try:
        df_prev, df_curr, prev_stem, curr_stem, stamp = _load_prev_curr_from_latest_diff()

        transfers_pre  = _build_transfers_pre(df_prev, df_curr, prev_stem, curr_stem)
        transfers_post = _build_transfers_post(df_curr, curr_stem)
        transfers_all  = pd.concat([transfers_pre, transfers_post], ignore_index=True)

        out_pre_pq  = (gold_dir / f"enrollment_transfers_pre__{stamp}.parquet").resolve()
        out_post_pq = (gold_dir / f"enrollment_transfers_post__{stamp}.parquet").resolve()
        out_all_pq  = (gold_dir / f"enrollment_transfers_all__{stamp}.parquet").resolve()

        transfers_pre.to_parquet(out_pre_pq,   index=False)
        transfers_post.to_parquet(out_post_pq, index=False)
        transfers_all.to_parquet(out_all_pq,   index=False)

        log.info(f"✅ Transfer PRE  -> {out_pre_pq.name}  (rows={len(transfers_pre)})")
        log.info(f"✅ Transfer POST -> {out_post_pq.name} (rows={len(transfers_post)})")
        log.info(f"✅ Transfer ALL  -> {out_all_pq.name}  (rows={len(transfers_all)})")
        transfers_parquet = out_all_pq

        if export_excel:
            out_pre_x  = (gold_dir / f"enrollment_transfers_pre__{stamp}.xlsx").resolve()
            out_post_x = (gold_dir / f"enrollment_transfers_post__{stamp}.xlsx").resolve()
            out_all_x  = (gold_dir / f"enrollment_transfers_all__{stamp}.xlsx").resolve()

            for df_, path, sheet in [
                (transfers_pre,  out_pre_x,  "transfer_pre"),
                (transfers_post, out_post_x, "transfer_post"),
                (transfers_all,  out_all_x,  "transfer_all"),
            ]:
                with pd.ExcelWriter(path, engine="openpyxl") as w:
                    df_.to_excel(w, index=False, sheet_name=sheet)

            log.info(f"✅ Transfer Excel PRE/POST/ALL generados")
            transfers_excel = out_all_x

            if latest_excel:
                with pd.ExcelWriter(latest_excel, engine="openpyxl") as w:
                    df_diff.to_excel(w,         index=False, sheet_name="diff_latest")
                    transfers_pre.to_excel(w,   index=False, sheet_name="transfer_pre")
                    transfers_post.to_excel(w,  index=False, sheet_name="transfer_post")
                    transfers_all.to_excel(w,   index=False, sheet_name="transfer_all")
                log.info("🧩 status_latest.xlsx actualizado")

    except Exception as e:
        log.warning(f"⚠️ No pude generar transferencias (PRE/POST): {e}")

    # 3) Status XLSX si no se escribió arriba
    if export_excel and latest_excel and not latest_excel.exists():
        with pd.ExcelWriter(latest_excel, engine="openpyxl") as w:
            df_diff.to_excel(w, index=False, sheet_name="diff_latest")
        log.info(f"✅ Excel generado: {latest_excel}")

    return StatusOutputs(
        latest_excel=latest_excel,
        transfers_parquet=transfers_parquet,
        transfers_excel=transfers_excel,
    )