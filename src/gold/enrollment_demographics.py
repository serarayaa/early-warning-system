from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config.settings import PATHS
from src.utils.logging_utils import get_logger
from src.utils.transforms import (
    coalesce_duplicates,
    latest_snapshot_file,
    normalize_text_series,
    parse_int,
    pick_one_per_rut,
    rut_key,
)

log = get_logger("EWS.enrollment_demographics")


# ---------------------------------------------------------------------
# Helpers locales (lógica propia de demografía)
# ---------------------------------------------------------------------

def _pct(part: int, total: int) -> float:
    return 0.0 if total <= 0 else round((part / total) * 100.0, 2)


def _norm_sexo(series: pd.Series) -> pd.Series:
    x = normalize_text_series(series)
    x = x.replace({"MASCULINO": "M", "FEMENINO": "F", "HOMBRE": "M", "MUJER": "F"})
    return x.str.extract(r"^(M|F)$", expand=False).fillna(x)


def _norm_nacionalidad(series: pd.Series) -> pd.Series:
    """
    Unifica variantes de 'chileno/a' → CHILENA para evitar
    contar chilenos como extranjeros por diferencias de texto.
    """
    x = normalize_text_series(series)
    chile_like = (
        x.isin([
            "CHILE", "CHILENO", "CHILENA", "CHILEN@", "CHILENA/O", "CHILENO/A",
            "CHILENA(O)", "CHILENO(A)", "CHILENA (CL)", "CHILENO (CL)",
        ])
        | x.str.contains(r"\bCHILEN", regex=True)
    )
    return x.mask(chile_like, "CHILENA")


def _top_counts(series: pd.Series, top_n: int, total_for_pct: int, colname: str) -> pd.DataFrame:
    s   = normalize_text_series(series)
    s   = s[s != ""]
    out = s.value_counts().head(top_n).reset_index()
    out.columns = [colname, "count"]
    out["pct"] = out["count"].apply(lambda v: _pct(int(v), int(total_for_pct)))
    return out


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def enrollment_demographics(snapshot_date: str, export_excel: bool = False, top_n: int = 10) -> None:
    """
    KPIs demográficos del snapshot (robusto a duplicados).
    Todo se calcula sobre 1 fila por RUT (rut_key).
    """
    snapshot_date = pd.to_datetime(snapshot_date)

    base    = PATHS.curated / "enrollment"
    out_dir = PATHS.gold / "enrollment"
    out_dir.mkdir(parents=True, exist_ok=True)

    latest_snap = latest_snapshot_file(base, "enrollment_snapshot__*.parquet")
    log.info(f"Usando snapshot: {latest_snap.name}")

    df = coalesce_duplicates(pd.read_parquet(latest_snap))

    for c in ["rut_norm", "comuna", "sexo", "nacionalidad", "edad", "is_repeat", "course_code", "specialty", "fecha_retiro"]:
        if c not in df.columns:
            df[c] = pd.NA

    # 1 fila por RUT
    d = pick_one_per_rut(df, snapshot_date=snapshot_date)
    d["rut_key"] = rut_key(d["rut_norm"])
    total_ruts   = int(d["rut_key"].nunique())

    # Sexo
    sexo    = _norm_sexo(d["sexo"])
    n_m     = int((sexo == "M").sum())
    n_f     = int((sexo == "F").sum())
    n_other = int(((sexo != "M") & (sexo != "F")).sum())

    # Comuna
    comuna          = normalize_text_series(d["comuna"])
    comuna_nonempty = comuna[comuna != ""]
    n_renca_total   = int((comuna == "RENCA").sum())
    n_renca_nonempty = int((comuna_nonempty == "RENCA").sum())
    pct_renca_total   = _pct(n_renca_total,   total_ruts)
    pct_renca_nonempty = _pct(n_renca_nonempty, len(comuna_nonempty)) if len(comuna_nonempty) else 0.0
    top_comunas = _top_counts(comuna, top_n=top_n, total_for_pct=len(comuna_nonempty), colname="comuna")

    # Nacionalidad
    nac             = _norm_nacionalidad(d["nacionalidad"])
    nac_nonempty    = nac[nac != ""]
    n_extranjeros   = int((nac_nonempty != "CHILENA").sum())
    extranjeros_pct = _pct(n_extranjeros, len(nac_nonempty)) if len(nac_nonempty) else 0.0
    top_nacs        = _top_counts(nac, top_n=top_n, total_for_pct=len(nac_nonempty), colname="nacionalidad")

    # Edad
    edad       = parse_int(d["edad"]).mask(parse_int(d["edad"]) <= 0)
    edad_valid = edad.dropna()
    edad_avg   = float(round(edad_valid.astype(float).mean(), 2)) if len(edad_valid) else float("nan")
    edad_min   = int(edad_valid.min()) if len(edad_valid) else None
    edad_max   = int(edad_valid.max()) if len(edad_valid) else None

    # Repitentes
    rep     = d["is_repeat"].fillna(False).astype(bool)
    n_rep   = int(rep.sum())
    rep_pct = _pct(n_rep, total_ruts)

    # Tops cursos y especialidades
    course          = normalize_text_series(d["course_code"])
    course_nonempty = course[course != ""]
    top_courses     = _top_counts(course, top_n=top_n, total_for_pct=len(course_nonempty), colname="course_code")

    spec          = normalize_text_series(d["specialty"])
    spec_nonempty = spec[spec != ""]
    top_specs     = _top_counts(spec, top_n=top_n, total_for_pct=len(spec_nonempty), colname="specialty")

    kpis = pd.DataFrame([{
        "snapshot_date":                              snapshot_date.date().isoformat(),
        "snapshot_file":                              latest_snap.name,
        "ruts_unicos":                                total_ruts,
        "sexo_m":                                     n_m,
        "sexo_f":                                     n_f,
        "sexo_otro_o_vacio":                          n_other,
        "pct_renca_sobre_total_ruts":                 pct_renca_total,
        "pct_renca_sobre_comuna_no_vacia":            pct_renca_nonempty,
        "extranjeros_pct_sobre_nacionalidad_no_vacia": extranjeros_pct,
        "edad_promedio":                              edad_avg,
        "edad_min":                                   edad_min,
        "edad_max":                                   edad_max,
        "repitentes":                                 n_rep,
        "repitentes_pct":                             rep_pct,
    }])

    stamp    = snapshot_date.strftime("%Y%m%d")
    out_kpis = out_dir / f"enrollment_demographics__{stamp}.parquet"
    out_comuna = out_dir / f"enrollment_by_comuna__{stamp}.parquet"
    out_nac  = out_dir / f"enrollment_by_nacionalidad__{stamp}.parquet"
    out_course = out_dir / f"enrollment_by_course__{stamp}.parquet"
    out_spec = out_dir / f"enrollment_by_specialty__{stamp}.parquet"

    kpis.to_parquet(out_kpis,   index=False)
    top_comunas.to_parquet(out_comuna, index=False)
    top_nacs.to_parquet(out_nac,    index=False)
    top_courses.to_parquet(out_course, index=False)
    top_specs.to_parquet(out_spec,  index=False)

    log.info(f"OK -> {out_kpis.name}")
    log.info(f"OK -> {out_comuna.name}")
    log.info(f"OK -> {out_nac.name}")
    log.info(f"OK -> {out_course.name}")
    log.info(f"OK -> {out_spec.name}")
    log.info(kpis.to_string(index=False))

    if export_excel:
        out_xlsx = out_dir / f"enrollment_demographics__{stamp}.xlsx"
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
            kpis.to_excel(w,        index=False, sheet_name="KPIS")
            top_comunas.to_excel(w, index=False, sheet_name="TOP_COMUNAS")
            top_nacs.to_excel(w,    index=False, sheet_name="TOP_NACIONALIDADES")
            top_courses.to_excel(w, index=False, sheet_name="TOP_CURSOS")
            top_specs.to_excel(w,   index=False, sheet_name="TOP_ESPECIALIDADES")
        log.info(f"OK -> {out_xlsx.name}")


if __name__ == "__main__":
    enrollment_demographics(snapshot_date="2026-03-02", export_excel=False, top_n=10)