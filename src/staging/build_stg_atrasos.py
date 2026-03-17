from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from src.utils.transforms import normalize_rut

log = logging.getLogger("sigma.atrasos")


def _to_bool_justifica(series: pd.Series) -> pd.Series:
    s = series.fillna(0).astype(str).str.strip().str.upper()
    return s.isin({"1", "SI", "S", "TRUE", "YES", "Y"})


def _pick_periodo(df: pd.DataFrame) -> pd.Series:
    if "Per0" in df.columns:
        p0 = df["Per0"].fillna("").astype(str).str.strip()
    else:
        p0 = pd.Series([""] * len(df), index=df.index)

    if "Per1" in df.columns:
        p1 = df["Per1"].fillna("").astype(str).str.strip()
    else:
        p1 = pd.Series([""] * len(df), index=df.index)

    p0 = p0.mask(p0 == "-", "")
    p1 = p1.mask(p1 == "-", "")
    return p0.mask(p0 == "", p1)


def _alerta_por_atrasos(n: int) -> str:
    if n >= 8:
        return "CRITICO"
    if n >= 4:
        return "ALTO"
    if n >= 2:
        return "MEDIO"
    return "BAJO"


def run(
    csv_path: str | Path,
    gold_dir: str | Path = "data/gold/atrasos",
    corte: date | None = None,
) -> dict[str, pd.DataFrame | int | date]:
    gold_dir = Path(gold_dir)
    gold_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path, sep=";", encoding="latin-1", dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    required = ["AtraFecha", "CurNombreCorto", "AluRut", "AluNombre"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas obligatorias en atrasos: {missing}")

    df["fecha_hora"] = pd.to_datetime(df["AtraFecha"], errors="coerce", dayfirst=True)
    df = df[df["fecha_hora"].notna()].copy()

    if corte is None:
        corte = df["fecha_hora"].dt.date.max()

    df = df[df["fecha_hora"].dt.date <= corte].copy()

    df["fecha"] = df["fecha_hora"].dt.date
    df["rut_norm"] = df["AluRut"].map(normalize_rut)
    df["curso"] = df["CurNombreCorto"].fillna("").astype(str).str.strip().str.upper()
    df["nombre"] = df["AluNombre"].fillna("").astype(str).str.strip().str.upper()
    df["tipo_atraso"] = df.get("TipoNombre", "").fillna("").astype(str).str.strip()
    df["hora"] = df.get("Hora", "").fillna("").astype(str).str.strip()
    df["justificado"] = _to_bool_justifica(df.get("Justifica", pd.Series([0] * len(df), index=df.index)))
    df["periodo"] = _pick_periodo(df)

    eventos = df[
        [
            "idAtraso",
            "fecha_hora",
            "fecha",
            "curso",
            "rut_norm",
            "nombre",
            "tipo_atraso",
            "periodo",
            "hora",
            "justificado",
        ]
    ].rename(columns={"idAtraso": "id_atraso"})

    eventos = eventos[eventos["rut_norm"] != ""].copy()

    alumnos = (
        eventos.groupby(["rut_norm", "nombre", "curso"], as_index=False)
        .agg(
            n_atrasos=("id_atraso", "count"),
            n_justificados=("justificado", "sum"),
            dias_con_atraso=("fecha", "nunique"),
            primer_atraso=("fecha_hora", "min"),
            ultimo_atraso=("fecha_hora", "max"),
        )
    )
    alumnos["pct_justificados"] = (
        (alumnos["n_justificados"] / alumnos["n_atrasos"]).fillna(0) * 100
    ).round(1)
    alumnos["alerta"] = alumnos["n_atrasos"].apply(_alerta_por_atrasos)

    cursos = (
        eventos.groupby("curso", as_index=False)
        .agg(
            total_atrasos=("id_atraso", "count"),
            alumnos_unicos=("rut_norm", "nunique"),
            justificados=("justificado", "sum"),
        )
    )
    cursos["pct_justificados"] = ((cursos["justificados"] / cursos["total_atrasos"]).fillna(0) * 100).round(1)
    cursos["promedio_atrasos_por_alumno"] = (
        (cursos["total_atrasos"] / cursos["alumnos_unicos"]).replace([pd.NA], 0).fillna(0)
    ).round(2)

    serie = (
        eventos.groupby("fecha", as_index=False)
        .agg(
            atrasos_dia=("id_atraso", "count"),
            alumnos_unicos=("rut_norm", "nunique"),
            justificados_dia=("justificado", "sum"),
        )
        .sort_values("fecha")
    )
    serie["pct_justificados_dia"] = (
        (serie["justificados_dia"] / serie["atrasos_dia"]).fillna(0) * 100
    ).round(1)

    eventos.to_csv(gold_dir / "atrasos_eventos.csv", index=False)
    alumnos.to_csv(gold_dir / "atrasos_alumnos.csv", index=False)
    cursos.to_csv(gold_dir / "atrasos_cursos.csv", index=False)
    serie.to_csv(gold_dir / "atrasos_serie.csv", index=False)

    meta = pd.DataFrame([
        {
            "corte": str(corte),
            "n_dias": int(serie["fecha"].nunique()) if not serie.empty else 0,
            "eventos": int(len(eventos)),
            "alumnos": int(eventos["rut_norm"].nunique()) if not eventos.empty else 0,
            "generado": pd.Timestamp.now().isoformat(),
            "csv_path": str(csv_path),
        }
    ])
    meta.to_csv(gold_dir / "atrasos_meta.csv", index=False)

    log.info(
        "Atrasos procesado | eventos=%s alumnos=%s cursos=%s",
        len(eventos),
        eventos["rut_norm"].nunique() if not eventos.empty else 0,
        cursos["curso"].nunique() if not cursos.empty else 0,
    )

    return {
        "eventos": eventos,
        "alumnos": alumnos,
        "cursos": cursos,
        "serie": serie,
        "n_dias": int(serie["fecha"].nunique()) if not serie.empty else 0,
        "corte": corte,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="SIGMA - Pipeline Atrasos")
    parser.add_argument("csv", help="Ruta al CSV de atrasos")
    parser.add_argument("--gold", default="data/gold/atrasos", help="Directorio de salida gold")
    parser.add_argument("--corte", default=None, help="Fecha de corte YYYY-MM-DD")
    args = parser.parse_args()

    corte = date.fromisoformat(args.corte) if args.corte else None
    r = run(args.csv, args.gold, corte)
    print(f"Atrasos OK | corte={r['corte']} | eventos={len(r['eventos'])} | alumnos={len(r['alumnos'])}")