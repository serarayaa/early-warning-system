from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger

log = get_logger("EWS.enrollment_history")


# -----------------------------
# Utils
# -----------------------------
def _latest_file(folder: Path, pattern: str) -> Path:
    files = sorted(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos con patrón: {folder}/{pattern}")
    return files[-1]


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


def _rut_key(series: pd.Series) -> pd.Series:
    s = series.fillna("").astype(str).str.strip().str.upper()
    return s.str.replace(r"[^0-9K]", "", regex=True)


def _pick_one_per_rut(df: pd.DataFrame) -> pd.DataFrame:
    """
    Dedupe por rut_key (robusto para POST: retiro+activo duplicado).
    Prioriza activo si existe fecha_retiro.
    """
    df = df.copy()
    if "rut_norm" not in df.columns:
        df["rut_norm"] = pd.NA

    df["rut_norm"] = df["rut_norm"].fillna("").astype(str).str.strip()
    df["rut_key"] = _rut_key(df["rut_norm"])
    df = df[df["rut_key"] != ""].copy()

    if "fecha_retiro" in df.columns:
        dt = pd.to_datetime(df["fecha_retiro"], errors="coerce", dayfirst=True)
        df["_activo"] = dt.isna().astype(int)
        df["_fecha_sort"] = dt.fillna(pd.Timestamp("1900-01-01"))
        df = df.sort_values(["rut_key", "_activo", "_fecha_sort"], ascending=[True, False, False])
        df = df.drop_duplicates("rut_key", keep="first").drop(columns=["_activo", "_fecha_sort"])
        return df

    return df.sort_values(["rut_key"], ascending=True).drop_duplicates("rut_key", keep="first")


def _calc_age(snapshot_date: pd.Timestamp, birth: pd.Series) -> pd.Series:
    birth_dt = pd.to_datetime(birth, errors="coerce", dayfirst=True)
    delta_days = (snapshot_date - birth_dt).dt.days
    age = (delta_days / 365.25).astype("float")
    # edades negativas (nacimiento futuro) las dejamos igual para que caigan como anomalía
    return age


def _write_txt_table(df: pd.DataFrame, out_txt: Path, title: str) -> None:
    lines: list[str] = []
    lines.append(title)
    lines.append("=" * len(title))
    lines.append("")
    if df.empty:
        lines.append("(sin registros)")
    else:
        lines.append(df.to_string(index=False))
    out_txt.write_text("\n".join(lines), encoding="utf-8")


# -----------------------------
# History: Demographics KPI
# -----------------------------
def update_demographics_history(snapshot_date: str) -> Path:
    snapshot_date = pd.to_datetime(snapshot_date)
    stamp = snapshot_date.strftime("%Y%m%d")

    out_dir = PATHS.gold / "enrollment"
    out_dir.mkdir(parents=True, exist_ok=True)

    kpi_path = out_dir / f"enrollment_demographics__{stamp}.parquet"
    if not kpi_path.exists():
        raise FileNotFoundError(
            f"No existe {kpi_path.name}. Primero ejecuta: gold-enrollment-demographics --snapshot-date {snapshot_date.date()}"
        )

    kpi = pd.read_parquet(kpi_path).copy()
    hist_path = out_dir / "enrollment_demographics_history.parquet"

    if hist_path.exists():
        hist = pd.read_parquet(hist_path)
        combined = pd.concat([hist, kpi], ignore_index=True)
    else:
        combined = kpi

    combined["snapshot_date"] = combined["snapshot_date"].astype(str)
    combined = (
        combined.sort_values("snapshot_date")
        .drop_duplicates(subset=["snapshot_date"], keep="last")
        .reset_index(drop=True)
    )

    combined.to_parquet(hist_path, index=False)
    log.info(f"✅ History actualizado: {hist_path.name} (rows={len(combined)})")
    return hist_path


# -----------------------------
# Anomalías edad/nacimiento
# -----------------------------
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
    stamp = snapshot_date.strftime("%Y%m%d")

    curated_dir = PATHS.curated / "enrollment"
    out_dir = PATHS.gold / "enrollment"
    out_dir.mkdir(parents=True, exist_ok=True)

    snap_path = _latest_file(curated_dir, "enrollment_snapshot__*.parquet")
    df_raw = pd.read_parquet(snap_path).copy()
    df0 = _coalesce_duplicates(df_raw)

    # columnas esperadas
    for c in ["rut_norm", "nombre", "course_code", "edad", "nacimiento", "nacimiento_raw", "fecha_retiro"]:
        if c not in df0.columns:
            df0[c] = pd.NA

    # dedupe por rut (para no inflar en POST)
    df = _pick_one_per_rut(df0)

    # parse nacimiento si no es datetime
    if not pd.api.types.is_datetime64_any_dtype(df["nacimiento"]):
        df["nacimiento"] = pd.to_datetime(df["nacimiento"], errors="coerce", dayfirst=True)

    df["edad_calc"] = _calc_age(snapshot_date, df["nacimiento"]).round(2)
    edad_rep = pd.to_numeric(df["edad"], errors="coerce")

    # Reglas
    is_birth_missing = df["nacimiento"].isna()
    is_birth_future = df["nacimiento"].notna() & (df["nacimiento"] > snapshot_date)

    is_age_outside = df["edad_calc"].notna() & ((df["edad_calc"] < min_age) | (df["edad_calc"] > max_age))
    is_diff_large = df["edad_calc"].notna() & edad_rep.notna() & ((df["edad_calc"] - edad_rep).abs() > diff_threshold)
    is_rep_weird = edad_rep.notna() & (edad_rep <= 2)

    df["issue"] = ""
    df["sub_issue"] = ""

    # 1) nacimiento vacío / inválido
    df.loc[is_birth_missing, "issue"] = "NACIMIENTO_VACIO_O_INVALIDO"
    df.loc[is_birth_missing, "sub_issue"] = "MISSING_OR_INVALID"

    # 2) nacimiento futuro
    df.loc[~is_birth_missing & is_birth_future, "issue"] = "EDAD_CALC_FUERA_RANGO"
    df.loc[~is_birth_missing & is_birth_future, "sub_issue"] = "BIRTH_IN_FUTURE"

    # 3) edad calc fuera de rango (si no cayó antes)
    can_age = (df["issue"] == "") & (~is_birth_missing) & (~is_birth_future) & df["edad_calc"].notna()
    too_young = can_age & (df["edad_calc"] < min_age)
    too_old = can_age & (df["edad_calc"] > max_age)

    df.loc[too_young | too_old, "issue"] = "EDAD_CALC_FUERA_RANGO"
    df.loc[too_young, "sub_issue"] = "TOO_YOUNG"
    df.loc[too_old, "sub_issue"] = "TOO_OLD"

    # 4) diferencia grande edad rep vs calc
    can_diff = (df["issue"] == "") & (~is_birth_missing) & df["edad_calc"].notna() & edad_rep.notna()
    df.loc[can_diff & is_diff_large, "issue"] = "DIFERENCIA_EDAD_REP_VS_CALC"
    df.loc[can_diff & is_diff_large, "sub_issue"] = f"DIFF_GT_{str(diff_threshold).replace('.', '_')}"

    # 5) edad reportada rara
    can_rep = (df["issue"] == "") & (~is_birth_missing) & edad_rep.notna()
    df.loc[can_rep & is_rep_weird, "issue"] = "EDAD_REPORTADA_RARA"
    df.loc[can_rep & is_rep_weird, "sub_issue"] = "REP_LE_2"

    # columnas útiles
    df["edad_sugerida"] = df["edad_calc"].round(0)
    df["diff_edad"] = (df["edad_calc"] - edad_rep).round(2)

    anomalies = df[df["issue"] != ""].copy()
    anomalies = anomalies[
        [
            "rut_norm",
            "nombre",
            "course_code",
            "nacimiento_raw",
            "nacimiento",
            "edad",
            "edad_calc",
            "edad_sugerida",
            "diff_edad",
            "issue",
            "sub_issue",
        ]
    ].sort_values(["issue", "sub_issue", "course_code", "nombre"], na_position="last")

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
        txt_df = anomalies[["nombre", "course_code", "nacimiento_raw", "edad", "edad_calc", "issue", "sub_issue"]].copy()
        out_txt = out_dir / f"enrollment_age_anomalies__{stamp}.txt"
        title = f"ANOMALIAS EDAD/NACIMIENTO - CORTE {snapshot_date.date().isoformat()} - {snap_path.name}"
        _write_txt_table(txt_df, out_txt, title)
        log.info(f"✅ TXT: {out_txt.name}")

    return AgeAnomalyOutputs(parquet=out_pq, excel=out_xlsx, txt=out_txt)


# -----------------------------
# Orquestador
# -----------------------------
def enrollment_history(snapshot_date: str, export_excel: bool = False) -> dict[str, str]:
    hist = update_demographics_history(snapshot_date=snapshot_date)
    anomalies = build_age_anomalies(
        snapshot_date=snapshot_date,
        export_excel=export_excel,
        export_txt=True,
        # puedes ajustar esto si quieres:
        min_age=10,
        max_age=25,
        diff_threshold=1.5,
    )

    return {
        "demographics_history": str(hist),
        "age_anomalies_parquet": str(anomalies.parquet),
        "age_anomalies_excel": str(anomalies.excel) if anomalies.excel else "",
        "age_anomalies_txt": str(anomalies.txt) if anomalies.txt else "",
    }


if __name__ == "__main__":
    print(enrollment_history(snapshot_date="2026-03-04", export_excel=False))