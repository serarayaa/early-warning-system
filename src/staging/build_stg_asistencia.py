"""
SIGMA — Pipeline de Asistencia
Ingesta del CSV de Syscol → gold/asistencia/
Corte: siempre hoy - 1 día hábil
"""
from __future__ import annotations
import argparse
import logging
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import numpy as np

log = logging.getLogger("sigma.asistencia")

HOLIDAYS: set[date] = set()          # Agregar feriados si se necesita
UMBRAL_CRITICO  = 75.0
UMBRAL_LEGAL    = 85.0
UMBRAL_CURSO_BAJO = 90.0             # Curso bajo este promedio = alerta
UMBRAL_CURSO_ALTO = 97.0             # Curso sobre este promedio = destacado


def _ultimo_dia_habil(hoy: date | None = None) -> date:
    """Retorna el último día hábil antes de hoy (lun-vie, no feriado)."""
    d = hoy or date.today()
    d -= timedelta(days=1)
    while d.weekday() >= 5 or d in HOLIDAYS:
        d -= timedelta(days=1)
    return d


def _norm_rut(series: pd.Series) -> pd.Series:
    """Normaliza RUT: quita puntos, deja guión, uppercase."""
    return (series.astype(str)
            .str.replace(".", "", regex=False)
            .str.replace(" ", "", regex=False)
            .str.upper()
            .str.strip())


def load_csv(path: str | Path) -> pd.DataFrame:
    """Carga y limpia el CSV de Syscol."""
    df = pd.read_csv(path, encoding="latin-1", sep=";")
    # Fila 0 es resumen global (sin Fecha)
    df = df.dropna(subset=["Fecha"]).copy()

    # Parsear fecha
    df["fecha"] = pd.to_datetime(df["Fecha"], format="%d/%m/%Y", errors="coerce")
    df = df.dropna(subset=["fecha"])

    # Normalizar columnas
    df["rut_norm"]     = _norm_rut(df["Rut"])
    df["curso"]        = df["CurNombreCorto"].astype(str).str.upper().str.strip()
    df["nombre"]       = df["Nombre"].astype(str).str.strip()
    df["presente"]     = df["Presente"].astype(int)
    df["ausente"]      = df["Ausente"].astype(int)

    return df[["fecha", "rut_norm", "curso", "nombre", "presente", "ausente"]]


def calcular_asistencia(df: pd.DataFrame, corte: date) -> dict[str, pd.DataFrame]:
    """
    Calcula métricas de asistencia hasta la fecha de corte.
    Retorna dict con DataFrames: alumnos, cursos, tendencia.
    """
    # Filtrar hasta corte
    df = df[df["fecha"].dt.date <= corte].copy()
    fechas_unicas = sorted(df["fecha"].unique())
    n_dias = len(fechas_unicas)

    # ── 1. Resumen por alumno ─────────────────────────────────────────
    alumnos = (
        df.groupby(["rut_norm", "curso", "nombre"])
        .agg(
            dias_presentes=("presente", "sum"),
            dias_ausentes=("ausente",  "sum"),
            dias_totales=("fecha",     "count"),
        )
        .reset_index()
    )
    alumnos["pct_asistencia"] = (
        alumnos["dias_presentes"] / alumnos["dias_totales"] * 100
    ).round(1)

    # Alertas
    alumnos["alerta"] = "OK"
    alumnos.loc[alumnos["pct_asistencia"] < UMBRAL_LEGAL,   "alerta"] = "LEGAL"    # <85%
    alumnos.loc[alumnos["pct_asistencia"] < UMBRAL_CRITICO, "alerta"] = "CRITICO"  # <75%

    # ── 2. Tendencia: últimos 3 días vs promedio acumulado ────────────
    if len(fechas_unicas) >= 4:
        ultimas_3 = fechas_unicas[-3:]
        df_ult = df[df["fecha"].isin(ultimas_3)]
        df_ant = df[~df["fecha"].isin(ultimas_3)]

        pct_ult = (df_ult.groupby("rut_norm")["presente"].mean() * 100).round(1)
        pct_ant = (df_ant.groupby("rut_norm")["presente"].mean() * 100).round(1)

        tendencia = pd.DataFrame({
            "pct_ultimos_3": pct_ult,
            "pct_anterior":  pct_ant,
        }).reset_index()
        tendencia["delta"] = tendencia["pct_ultimos_3"] - tendencia["pct_anterior"]
        tendencia["tendencia"] = tendencia["delta"].apply(
            lambda d: "BAJA" if d < -15 else ("ALTA" if d > 10 else "ESTABLE")
        )
        alumnos = alumnos.merge(tendencia[["rut_norm","pct_ultimos_3","delta","tendencia"]],
                                on="rut_norm", how="left")
        alumnos["tendencia"] = alumnos["tendencia"].fillna("ESTABLE")
    else:
        alumnos["pct_ultimos_3"] = np.nan
        alumnos["delta"]         = np.nan
        alumnos["tendencia"]     = "ESTABLE"

    # ── 3. Resumen por curso ──────────────────────────────────────────
    cursos = (
        alumnos.groupby("curso")
        .agg(
            n_alumnos        =("rut_norm",       "count"),
            pct_promedio     =("pct_asistencia", "mean"),
            bajo_85          =("alerta", lambda x: (x.isin(["LEGAL","CRITICO"])).sum()),
            bajo_75          =("alerta", lambda x: (x == "CRITICO").sum()),
            tendencia_baja   =("tendencia", lambda x: (x == "BAJA").sum()),
        )
        .reset_index()
    )
    cursos["pct_promedio"] = cursos["pct_promedio"].round(1)

    cursos["alerta_curso"] = "OK"
    cursos.loc[cursos["pct_promedio"] < UMBRAL_CURSO_BAJO,  "alerta_curso"] = "BAJO"
    cursos.loc[cursos["pct_promedio"] >= UMBRAL_CURSO_ALTO, "alerta_curso"] = "ALTO"

    # ── 4. Serie diaria global ────────────────────────────────────────
    serie = (
        df.groupby("fecha")
        .agg(
            pct_dia=("presente", lambda x: round(x.mean() * 100, 1)),
            n_ausentes=("ausente", "sum"),
        )
        .reset_index()
        .sort_values("fecha")
    )

    return {
        "alumnos":  alumnos,
        "cursos":   cursos,
        "serie":    serie,
        "n_dias":   n_dias,
        "corte":    corte,
    }


def run(csv_path: str | Path,
        gold_dir: str | Path = "data/gold/asistencia",
        corte: date | None = None) -> dict:
    """
    Pipeline completo. Carga CSV, calcula, guarda parquets.
    Retorna el dict de resultados para uso directo desde app.py.
    """
    gold_dir = Path(gold_dir)
    gold_dir.mkdir(parents=True, exist_ok=True)

    corte = corte or _ultimo_dia_habil()
    log.info(f"Procesando asistencia hasta corte: {corte}")

    df_raw = load_csv(csv_path)
    resultados = calcular_asistencia(df_raw, corte)

    # Guardar CSVs (compatibilidad sin pyarrow)
    resultados["alumnos"].to_csv(gold_dir / "asistencia_alumnos.csv", index=False)
    resultados["cursos"].to_csv(gold_dir  / "asistencia_cursos.csv",  index=False)
    resultados["serie"].to_csv(gold_dir   / "asistencia_serie.csv",   index=False)

    # Metadatos
    meta = pd.DataFrame([{
        "corte":    str(corte),
        "n_dias":   resultados["n_dias"],
        "generado": pd.Timestamp.now().isoformat(),
        "csv_path": str(csv_path),
    }])
    meta.to_csv(gold_dir / "asistencia_meta.csv", index=False)

    log.info(
        f"Asistencia guardada. "
        f"Alumnos: {len(resultados['alumnos'])} | "
        f"Bajo 85%: {(resultados['alumnos']['alerta'].isin(['LEGAL','CRITICO'])).sum()} | "
        f"Bajo 75%: {(resultados['alumnos']['alerta']=='CRITICO').sum()}"
    )
    return resultados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="SIGMA — Pipeline Asistencia")
    parser.add_argument("csv", help="Ruta al CSV de Syscol")
    parser.add_argument("--gold", default="data/gold/asistencia",
                        help="Directorio de salida gold")
    parser.add_argument("--corte", default=None,
                        help="Fecha de corte YYYY-MM-DD (default: hoy-1 día hábil)")
    args = parser.parse_args()

    corte = date.fromisoformat(args.corte) if args.corte else None
    resultados = run(args.csv, args.gold, corte)

    a = resultados["alumnos"]
    print(f"\n{'='*50}")
    print(f"  SIGMA Asistencia — Corte: {resultados['corte']}")
    print(f"  Días hábiles procesados: {resultados['n_dias']}")
    print(f"  Alumnos procesados:  {len(a):,}")
    print(f"  Bajo 85% (legal):    {(a['alerta'].isin(['LEGAL','CRITICO'])).sum():,}")
    print(f"  Bajo 75% (crítico):  {(a['alerta']=='CRITICO').sum():,}")
    print(f"  Tendencia a la baja: {(a['tendencia']=='BAJA').sum():,}")
    print(f"{'='*50}\n")