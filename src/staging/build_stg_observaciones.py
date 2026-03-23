"""
SIGMA — Pipeline Observaciones
src/staging/build_stg_observaciones.py

Procesa el CSV de observaciones exportado desde Syscol.
Columnas esperadas: idObservacion, Alumno, Fecha, AluNombreApellido,
                    NCCurso, TipoCodigo, Descripcion, Hora,
                    PerNombreApellido, NombreCompleto
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from src.utils.transforms import normalize_rut

log = logging.getLogger("sigma.observaciones")

# Umbrales de alerta por alumno
UMBRAL_CRITICO = 5   # >= 5 observaciones negativas → CRITICO
UMBRAL_ALTO    = 3   # >= 3                          → ALTO
UMBRAL_MEDIO   = 1   # >= 1                          → MEDIO


def _alerta_negativas(n: int) -> str:
    if n >= UMBRAL_CRITICO: return "CRITICO"
    if n >= UMBRAL_ALTO:    return "ALTO"
    if n >= UMBRAL_MEDIO:   return "MEDIO"
    return "BAJO"


def run(
    csv_path: str | Path,
    gold_dir: str | Path = "data/gold/observaciones",
    corte: date | None = None,
) -> dict:
    gold_dir = Path(gold_dir)
    gold_dir.mkdir(parents=True, exist_ok=True)

    # ── Lectura ───────────────────────────────────────────────────────
    df = pd.read_csv(csv_path, sep=";", encoding="latin-1", dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    required = ["idObservacion", "NCCurso", "TipoCodigo", "Fecha"]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en observaciones: {missing}")

    # ── Normalización ─────────────────────────────────────────────────
    df["fecha_dt"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors="coerce")
    df = df[df["fecha_dt"].notna()].copy()

    if corte is None:
        corte = df["fecha_dt"].dt.date.max()

    df = df[df["fecha_dt"].dt.date <= corte].copy()
    df["fecha"] = df["fecha_dt"].dt.date

    # Normalizar RUT si viene en columna Alumno
    if "Alumno" in df.columns:
        df["rut_norm"] = df["Alumno"].map(
            lambda v: normalize_rut(str(v)) if pd.notna(v) else ""
        )
    else:
        df["rut_norm"] = ""

    df["curso"]    = df["NCCurso"].fillna("").astype(str).str.strip().str.upper()
    df["tipo"]     = df["TipoCodigo"].fillna("").astype(str).str.strip().str.upper()
    df["nombre"]   = df.get("NombreCompleto", df.get("AluNombreApellido", pd.Series([""] * len(df), index=df.index))).fillna("").astype(str).str.strip().str.upper()
    df["docente"]  = df.get("PerNombreApellido", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str).str.strip()
    df["hora"]     = df.get("Hora", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str).str.strip()
    df["descripcion"] = df.get("Descripcion", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str).str.strip()

    # Extraer nivel del código de curso (ej: 1EMA → 1)
    df["nivel"] = df["curso"].str.extract(r"^(\d)").fillna("").astype(str)

    # Extraer especialidad del curso usando la letra de sección
    sec_map = {"A":"TELECOM","B":"TELECOM","C":"TELECOM","D":"TELECOM",
               "E":"ELECTRONICA","F":"ELECTRONICA","G":"MECANICA","H":"MECANICA"}
    df["seccion"]    = df["curso"].str.extract(r"\d+EM([A-Z])$").fillna("")
    df["specialty"]  = df["seccion"].map(sec_map).fillna("COMUN")

    # ── Tabla de eventos ──────────────────────────────────────────────
    eventos = df[[
        "idObservacion", "fecha", "hora", "curso", "nivel", "specialty",
        "rut_norm", "nombre", "tipo", "descripcion", "docente",
    ]].rename(columns={"idObservacion": "id_obs"}).copy()
    eventos = eventos[eventos["rut_norm"] != ""].copy()

    # ── Acumular con gold existente + deduplicar por id_obs ───────────
    gold_eventos = gold_dir / "obs_eventos.csv"
    if gold_eventos.exists():
        try:
            df_existing = pd.read_csv(gold_eventos, encoding="utf-8")
            df_existing["fecha"] = pd.to_datetime(df_existing["fecha"], errors="coerce").dt.date
            eventos = pd.concat([df_existing, eventos], ignore_index=True)
            antes = len(eventos)
            eventos = eventos.drop_duplicates(subset=["id_obs"], keep="last")
            log.info(f"  Acumulado: {len(eventos)} eventos ({antes - len(eventos)} duplicados eliminados)")
        except Exception as e:
            log.warning(f"  No se pudo cargar gold existente: {e}")

    # ── Tabla por alumno ──────────────────────────────────────────────
    alumnos = (
        eventos.groupby(["rut_norm", "nombre", "curso"], as_index=False)
        .agg(
            total_obs    = ("id_obs",  "count"),
            obs_negativas= ("tipo",    lambda x: (x == "NEG").sum()),
            obs_positivas= ("tipo",    lambda x: (x == "POS").sum()),
            obs_neutras  = ("tipo",    lambda x: (x == "OBS").sum()),
            n_docentes   = ("docente", "nunique"),
            primera_obs  = ("fecha",   "min"),
            ultima_obs   = ("fecha",   "max"),
        )
    )
    alumnos["alerta"] = alumnos["obs_negativas"].apply(_alerta_negativas)
    alumnos["pct_negativas"] = (
        alumnos["obs_negativas"] / alumnos["total_obs"] * 100
    ).round(1)

    # ── Tabla por curso ───────────────────────────────────────────────
    cursos = (
        eventos.groupby("curso", as_index=False)
        .agg(
            total_obs    = ("id_obs",  "count"),
            alumnos_unicos= ("rut_norm","nunique"),
            obs_negativas= ("tipo",    lambda x: (x == "NEG").sum()),
            obs_positivas= ("tipo",    lambda x: (x == "POS").sum()),
            obs_neutras  = ("tipo",    lambda x: (x == "OBS").sum()),
        )
    )
    cursos["pct_negativas"] = (
        cursos["obs_negativas"] / cursos["total_obs"] * 100
    ).round(1)
    cursos["promedio_por_alumno"] = (
        cursos["total_obs"] / cursos["alumnos_unicos"]
    ).round(2)
    cursos = cursos.sort_values("total_obs", ascending=False)

    # ── Tabla por docente ─────────────────────────────────────────────
    docentes = (
        eventos.groupby("docente", as_index=False)
        .agg(
            total_obs    = ("id_obs",  "count"),
            alumnos_unicos= ("rut_norm","nunique"),
            obs_negativas= ("tipo",    lambda x: (x == "NEG").sum()),
            obs_positivas= ("tipo",    lambda x: (x == "POS").sum()),
            obs_neutras  = ("tipo",    lambda x: (x == "OBS").sum()),
        )
    ).sort_values("total_obs", ascending=False)

    # ── Serie diaria ──────────────────────────────────────────────────
    serie = (
        eventos.groupby("fecha", as_index=False)
        .agg(
            total_dia    = ("id_obs",  "count"),
            alumnos_dia  = ("rut_norm","nunique"),
            negativas_dia= ("tipo",    lambda x: (x == "NEG").sum()),
        )
        .sort_values("fecha")
    )
    serie["pct_negativas_dia"] = (
        serie["negativas_dia"] / serie["total_dia"] * 100
    ).round(1)

    # ── Guardar gold ──────────────────────────────────────────────────
    eventos.to_csv(gold_dir / "obs_eventos.csv",  index=False, encoding="utf-8")
    alumnos.to_csv(gold_dir / "obs_alumnos.csv",  index=False, encoding="utf-8")
    cursos.to_csv( gold_dir / "obs_cursos.csv",   index=False, encoding="utf-8")
    docentes.to_csv(gold_dir / "obs_docentes.csv",index=False, encoding="utf-8")
    serie.to_csv(  gold_dir / "obs_serie.csv",    index=False, encoding="utf-8")

    meta = pd.DataFrame([{
        "corte":    str(corte),
        "eventos":  len(eventos),
        "alumnos":  eventos["rut_norm"].nunique(),
        "generado": pd.Timestamp.now().isoformat(),
        "csv_path": str(csv_path),
    }])
    meta.to_csv(gold_dir / "obs_meta.csv", index=False, encoding="utf-8")

    log.info("Observaciones OK | eventos=%s alumnos=%s cursos=%s",
             len(eventos), eventos["rut_norm"].nunique(), cursos["curso"].nunique())

    return {
        "eventos":  eventos,
        "alumnos":  alumnos,
        "cursos":   cursos,
        "docentes": docentes,
        "serie":    serie,
        "corte":    corte,
    }