from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger
from src.utils.transforms import (
    coalesce_duplicates,
    latest_snapshot_file,
    pick_one_per_rut,
)

log = get_logger("EWS.enrollment_history")


# ---------------------------------------------------------------------
# Helpers locales (lógica propia de history)
# ---------------------------------------------------------------------

def _calc_age(snapshot_date: pd.Timestamp, birth: pd.Series) -> pd.Series:
    birth_dt   = pd.to_datetime(birth, errors="coerce", dayfirst=True)
    delta_days = (snapshot_date - birth_dt).dt.days
    # Edades negativas (nacimiento futuro) se dejan para que caigan como anomalía
    return (delta_days / 365.25).astype("float")


def _write_txt_table(df: pd.DataFrame, out_txt: Path, title: str) -> None:
    lines = [title, "=" * len(title), ""]
    lines.append("(sin registros)" if df.empty else df.to_string(index=False))
    out_txt.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------
# History: Demographics KPI
# ---------------------------------------------------------------------

def update_demographics_history(snapshot_date: str) -> Path:
    snapshot_date = pd.to_datetime(snapshot_date)
    stamp         = snapshot_date.strftime("%Y%m%d")

    out_dir = PATHS.gold / "enrollment"
    out_dir.mkdir(parents=True, exist_ok=True)

    kpi_path = out_dir / f"enrollment_demographics__{stamp}.parquet"
    if not kpi_path.exists():
        raise FileNotFoundError(
            f"No existe {kpi_path.name}. "
            f"Primero ejecuta: gold-enrollment-demographics --snapshot-date {snapshot_date.date()}"
        )

    kpi  = pd.read_parquet(kpi_path).copy()
    hist_path = out_dir / "enrollment_demographics_history.parquet"

    combined = pd.concat([pd.read_parquet(hist_path), kpi], ignore_index=True) \
               if hist_path.exists() else kpi

    combined["snapshot_date"] = combined["snapshot_date"].astype(str)
    combined = (
        combined.sort_values("snapshot_date")
        .drop_duplicates(subset=["snapshot_date"], keep="last")
        .reset_index(drop=True)
    )

    combined.to_parquet(hist_path, index=False)
    log.info(f"✅ History actualizado: {hist_path.name} (rows={len(combined)})")
    return hist_path


# ---------------------------------------------------------------------
# Anomalías edad/nacimiento
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class AgeAnomalyOutputs:
    parquet: Path
    excel: Path | None
    txt: Path | None


def build_age_anomalies(
    snapshot_date: str,
    export_excel: bool = False,
    export_txt: bool = True,
    min_age: int = 10,
    max_age: int = 25,
    diff_threshold: float = 1.5,
) -> AgeAnomalyOutputs:
    snapshot_date = pd.to_datetime(snapshot_date)
    stamp         = snapshot_date.strftime("%Y%m%d")

    curated_dir = PATHS.curated / "enrollment"
    out_dir     = PATHS.gold / "enrollment"
    out_dir.mkdir(parents=True, exist_ok=True)

    snap_path = latest_snapshot_file(curated_dir, "enrollment_snapshot__*.parquet")
    df0       = coalesce_duplicates(pd.read_parquet(snap_path).copy())

    for c in ["rut_norm", "nombre", "course_code", "edad", "nacimiento", "nacimiento_raw", "fecha_retiro"]:
        if c not in df0.columns:
            df0[c] = pd.NA

    df = pick_one_per_rut(df0, snapshot_date=snapshot_date)

    if not pd.api.types.is_datetime64_any_dtype(df["nacimiento"]):
        df["nacimiento"] = pd.to_datetime(df["nacimiento"], errors="coerce", dayfirst=True)

    df["edad_calc"] = _calc_age(snapshot_date, df["nacimiento"]).round(2)
    edad_rep        = pd.to_numeric(df["edad"], errors="coerce")

    is_birth_missing = df["nacimiento"].isna()
    is_birth_future  = df["nacimiento"].notna() & (df["nacimiento"] > snapshot_date)
    is_age_outside   = df["edad_calc"].notna() & ((df["edad_calc"] < min_age) | (df["edad_calc"] > max_age))
    is_diff_large    = df["edad_calc"].notna() & edad_rep.notna() & ((df["edad_calc"] - edad_rep).abs() > diff_threshold)
    is_rep_weird     = edad_rep.notna() & (edad_rep <= 2)

    df["issue"]     = ""
    df["sub_issue"] = ""

    df.loc[is_birth_missing, "issue"]     = "NACIMIENTO_VACIO_O_INVALIDO"
    df.loc[is_birth_missing, "sub_issue"] = "MISSING_OR_INVALID"

    df.loc[~is_birth_missing & is_birth_future, "issue"]     = "EDAD_CALC_FUERA_RANGO"
    df.loc[~is_birth_missing & is_birth_future, "sub_issue"] = "BIRTH_IN_FUTURE"

    can_age  = (df["issue"] == "") & (~is_birth_missing) & (~is_birth_future) & df["edad_calc"].notna()
    too_young = can_age & (df["edad_calc"] < min_age)
    too_old   = can_age & (df["edad_calc"] > max_age)
    df.loc[too_young | too_old, "issue"]     = "EDAD_CALC_FUERA_RANGO"
    df.loc[too_young,           "sub_issue"] = "TOO_YOUNG"
    df.loc[too_old,             "sub_issue"] = "TOO_OLD"

    can_diff = (df["issue"] == "") & (~is_birth_missing) & df["edad_calc"].notna() & edad_rep.notna()
    df.loc[can_diff & is_diff_large, "issue"]     = "DIFERENCIA_EDAD_REP_VS_CALC"
    df.loc[can_diff & is_diff_large, "sub_issue"] = f"DIFF_GT_{str(diff_threshold).replace('.', '_')}"

    can_rep = (df["issue"] == "") & (~is_birth_missing) & edad_rep.notna()
    df.loc[can_rep & is_rep_weird, "issue"]     = "EDAD_REPORTADA_RARA"
    df.loc[can_rep & is_rep_weird, "sub_issue"] = "REP_LE_2"

    df["edad_sugerida"] = df["edad_calc"].round(0)
    df["diff_edad"]     = (df["edad_calc"] - edad_rep).round(2)

    anomalies = df[df["issue"] != ""].copy()
    anomalies = anomalies[[
        "rut_norm", "nombre", "course_code",
        "nacimiento_raw", "nacimiento", "edad",
        "edad_calc", "edad_sugerida", "diff_edad",
        "issue", "sub_issue",
    ]].sort_values(["issue", "sub_issue", "course_code", "nombre"], na_position="last")

    out_pq = out_dir / f"enrollment_age_anomalies__{stamp}.parquet"
    anomalies.to_parquet(out_pq, index=False)
    log.info(f"✅ Age anomalies: {out_pq.name} (rows={len(anomalies)})")

    out_xlsx = None
    if export_excel:
        out_xlsx = out_dir / f"enrollment_age_anomalies__{stamp}.xlsx"
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
            anomalies.to_excel(w, index=False, sheet_name="AGE_ANOMALIES")
        log.info(f"✅ Excel: {out_xlsx.name}")

    out_txt = None
    if export_txt:
        txt_df  = anomalies[["nombre", "course_code", "nacimiento_raw", "edad", "edad_calc", "issue", "sub_issue"]].copy()
        out_txt = out_dir / f"enrollment_age_anomalies__{stamp}.txt"
        _write_txt_table(txt_df, out_txt, f"ANOMALIAS EDAD/NACIMIENTO - CORTE {snapshot_date.date()} - {snap_path.name}")
        log.info(f"✅ TXT: {out_txt.name}")

    return AgeAnomalyOutputs(parquet=out_pq, excel=out_xlsx, txt=out_txt)


# ---------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------

def enrollment_history(snapshot_date: str, export_excel: bool = False) -> dict[str, str]:
    from src.config.settings import BUSINESS_RULES  # import aquí para evitar circular

    hist      = update_demographics_history(snapshot_date=snapshot_date)
    anomalies = build_age_anomalies(
        snapshot_date=snapshot_date,
        export_excel=export_excel,
        export_txt=True,
        min_age=BUSINESS_RULES.age_min,
        max_age=BUSINESS_RULES.age_max,
        diff_threshold=BUSINESS_RULES.age_diff_threshold,
    )
    return {
        "demographics_history":  str(hist),
        "age_anomalies_parquet": str(anomalies.parquet),
        "age_anomalies_excel":   str(anomalies.excel) if anomalies.excel else "",
        "age_anomalies_txt":     str(anomalies.txt)   if anomalies.txt   else "",
    }


if __name__ == "__main__":
    print(enrollment_history(snapshot_date="2026-03-04", export_excel=False))