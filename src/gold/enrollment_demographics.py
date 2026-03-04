from __future__ import annotations

import re
from pathlib import Path
import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger

log = get_logger("EWS.enrollment_demographics")


def _latest_file(folder: Path, pattern: str) -> Path:
    files = sorted(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos con patrón: {folder}/{pattern}")
    return files[-1]


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((part / total) * 100.0, 2)


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


def _norm_text(series: pd.Series) -> pd.Series:
    x = series.fillna("").astype(str).str.strip().str.upper()
    x = x.str.replace(r"\s+", " ", regex=True)
    return x


def _norm_sexo(series: pd.Series) -> pd.Series:
    x = _norm_text(series)
    # equivalencias típicas
    x = x.replace({
        "MASCULINO": "M",
        "FEMENINO": "F",
        "HOMBRE": "M",
        "MUJER": "F",
    })
    # si viene "M " o "F "
    x = x.str.extract(r"^(M|F)$", expand=False).fillna(x)
    return x


def _norm_nacionalidad(series: pd.Series) -> pd.Series:
    """
    Normaliza nacionalidad para evitar falsos 'extranjeros'.
    Unifica CHILE/CHILENO/CHILENA/... -> CHILENA
    """
    x = _norm_text(series)

    chile_like = (
        x.isin([
            "CHILE", "CHILENO", "CHILENA", "CHILEN@", "CHILENA/O", "CHILENO/A",
            "CHILENA(O)", "CHILENO(A)", "CHILENA (CL)", "CHILENO (CL)"
        ])
        | x.str.contains(r"\bCHILEN", regex=True)
    )
    x = x.mask(chile_like, "CHILENA")
    return x


def _top_counts(series: pd.Series, top_n: int, total_for_pct: int, colname: str) -> pd.DataFrame:
    s = _norm_text(series)
    s = s[s != ""]
    out = s.value_counts().head(top_n).reset_index()
    out.columns = [colname, "count"]
    out["pct"] = out["count"].apply(lambda v: _pct(int(v), int(total_for_pct)))
    return out


def _parse_int(series: pd.Series) -> pd.Series:
    s = series.fillna("").astype(str).str.strip()
    s = s.replace({"": pd.NA, "None": pd.NA, "nan": pd.NA})
    return pd.to_numeric(s, errors="coerce").astype("Int64")


def _pick_one_per_rut(df: pd.DataFrame) -> pd.DataFrame:
    """
    Dedupe por rut_key para que KPIs no se inflen cuando Syscol duplique (POST).
    Si existe fecha_retiro, prioriza activo (NaT), si no, deja la fila “más activa”.
    """
    df = df.copy()
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


def enrollment_demographics(snapshot_date: str, export_excel: bool = False, top_n: int = 10) -> None:
    """
    KPIs demográficos del snapshot (robusto a duplicados):
    - todo se calcula sobre 1 fila por RUT (rut_key)
    """
    snapshot_date = pd.to_datetime(snapshot_date)

    base = PATHS.curated / "enrollment"
    out_dir = PATHS.gold / "enrollment"
    out_dir.mkdir(parents=True, exist_ok=True)

    latest_snap = _latest_file(base, "enrollment_snapshot__*.parquet")
    log.info(f"Usando snapshot: {latest_snap.name}")

    df_raw = pd.read_parquet(latest_snap)
    df = _coalesce_duplicates(df_raw)

    # columnas esperadas
    for c in ["rut_norm", "comuna", "sexo", "nacionalidad", "edad", "is_repeat", "course_code", "specialty", "fecha_retiro"]:
        if c not in df.columns:
            df[c] = pd.NA

    # Dedup por RUT
    d = _pick_one_per_rut(df)

    total_ruts = int(d["rut_key"].nunique())

    # sexo (por RUT)
    sexo = _norm_sexo(d["sexo"])
    n_m = int((sexo == "M").sum())
    n_f = int((sexo == "F").sum())
    n_other = int(((sexo != "M") & (sexo != "F")).sum())

    # comuna (por RUT)
    comuna = _norm_text(d["comuna"])
    comuna_nonempty = comuna[comuna != ""]
    n_renca_total = int((comuna == "RENCA").sum())
    n_renca_nonempty = int((comuna_nonempty == "RENCA").sum())

    pct_renca_total = _pct(n_renca_total, total_ruts)
    pct_renca_nonempty = _pct(n_renca_nonempty, int(len(comuna_nonempty))) if len(comuna_nonempty) else 0.0

    top_comunas = _top_counts(comuna, top_n=top_n, total_for_pct=int(len(comuna_nonempty)), colname="comuna")

    # nacionalidad (por RUT)
    nac = _norm_nacionalidad(d["nacionalidad"])
    nac_nonempty = nac[nac != ""]
    n_extranjeros = int((nac_nonempty != "CHILENA").sum())
    extranjeros_pct = _pct(n_extranjeros, int(len(nac_nonempty))) if len(nac_nonempty) else 0.0

    top_nacs = _top_counts(nac, top_n=top_n, total_for_pct=int(len(nac_nonempty)), colname="nacionalidad")

    # edad (por RUT)
    edad = _parse_int(d["edad"])
    edad = edad.mask(edad <= 0)
    edad_valid = edad.dropna()
    edad_avg = float(round(edad_valid.astype(float).mean(), 2)) if len(edad_valid) else float("nan")
    edad_min = int(edad_valid.min()) if len(edad_valid) else None
    edad_max = int(edad_valid.max()) if len(edad_valid) else None

    # repitentes (por RUT)
    rep = d["is_repeat"].fillna(False).astype(bool)
    n_rep = int(rep.sum())
    rep_pct = _pct(n_rep, total_ruts)

    # tops (por RUT)
    course = _norm_text(d["course_code"])
    course_nonempty = course[course != ""]
    top_courses = _top_counts(course, top_n=top_n, total_for_pct=int(len(course_nonempty)), colname="course_code")

    spec = _norm_text(d["specialty"])
    spec_nonempty = spec[spec != ""]
    top_specs = _top_counts(spec, top_n=top_n, total_for_pct=int(len(spec_nonempty)), colname="specialty")

    kpis = pd.DataFrame([{
        "snapshot_date": snapshot_date.date().isoformat(),
        "snapshot_file": latest_snap.name,
        "ruts_unicos": total_ruts,
        "sexo_m": n_m,
        "sexo_f": n_f,
        "sexo_otro_o_vacio": n_other,
        "pct_renca_sobre_total_ruts": pct_renca_total,
        "pct_renca_sobre_comuna_no_vacia": pct_renca_nonempty,
        "extranjeros_pct_sobre_nacionalidad_no_vacia": extranjeros_pct,
        "edad_promedio": edad_avg,
        "edad_min": edad_min,
        "edad_max": edad_max,
        "repitentes": n_rep,
        "repitentes_pct": rep_pct,
    }])

    stamp = snapshot_date.strftime("%Y%m%d")
    out_kpis = out_dir / f"enrollment_demographics__{stamp}.parquet"
    out_comuna = out_dir / f"enrollment_by_comuna__{stamp}.parquet"
    out_nac = out_dir / f"enrollment_by_nacionalidad__{stamp}.parquet"
    out_course = out_dir / f"enrollment_by_course__{stamp}.parquet"
    out_spec = out_dir / f"enrollment_by_specialty__{stamp}.parquet"

    kpis.to_parquet(out_kpis, index=False)
    top_comunas.to_parquet(out_comuna, index=False)
    top_nacs.to_parquet(out_nac, index=False)
    top_courses.to_parquet(out_course, index=False)
    top_specs.to_parquet(out_spec, index=False)

    log.info(f"OK -> {out_kpis.name}")
    log.info(f"OK -> {out_comuna.name}")
    log.info(f"OK -> {out_nac.name}")
    log.info(f"OK -> {out_course.name}")
    log.info(f"OK -> {out_spec.name}")
    log.info(kpis.to_string(index=False))

    if export_excel:
        out_xlsx = out_dir / f"enrollment_demographics__{stamp}.xlsx"
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
            kpis.to_excel(w, index=False, sheet_name="KPIS")
            top_comunas.to_excel(w, index=False, sheet_name="TOP_COMUNAS")
            top_nacs.to_excel(w, index=False, sheet_name="TOP_NACIONALIDADES")
            top_courses.to_excel(w, index=False, sheet_name="TOP_CURSOS")
            top_specs.to_excel(w, index=False, sheet_name="TOP_ESPECIALIDADES")
        log.info(f"OK -> {out_xlsx.name}")


if __name__ == "__main__":
    enrollment_demographics(snapshot_date="2026-03-02", export_excel=False, top_n=10)