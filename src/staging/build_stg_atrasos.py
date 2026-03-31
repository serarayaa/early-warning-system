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


# Norma MINEDUC: atraso antes de las 9:30 → alumno queda PRESENTE
# Atraso después de las 9:30 → alumno queda AUSENTE el resto del día
CORTE_HORA_MINUTOS = 9 * 60 + 30  # 9:30 = 570 minutos

def _clasificar_atraso(hora_str: str) -> str:
    """Clasifica atraso como LEVE (queda presente) o GRAVE (queda ausente)."""
    try:
        h, m = str(hora_str).strip()[:5].split(":")
        minutos = int(h) * 60 + int(m)
        if minutos <= 0:
            return "LEVE"  # Sin hora válida → conservador
        return "LEVE" if minutos <= CORTE_HORA_MINUTOS else "GRAVE"
    except Exception:
        return "LEVE"


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
    df_matricula: pd.DataFrame | None = None,
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

    # ── Clasificar atraso según norma MINEDUC (9:30) ──────────────────
    eventos["clasificacion"] = eventos["hora"].apply(_clasificar_atraso)
    # Contar atrasos graves (generan ausencia) por separado
    n_graves_nuevos = int((eventos["clasificacion"] == "GRAVE").sum())
    if n_graves_nuevos > 0:
        log.info(f"  Atrasos GRAVES (>9:30, generan ausencia): {n_graves_nuevos}")

    # ── Acumular con gold existente + deduplicar por id_atraso ───────
    gold_eventos = gold_dir / "atrasos_eventos.csv"
    if gold_eventos.exists():
        try:
            df_existing = pd.read_csv(gold_eventos, encoding="utf-8", dtype=str)
            df_existing["fecha_hora"] = pd.to_datetime(df_existing["fecha_hora"], errors="coerce")
            df_existing["fecha"] = pd.to_datetime(df_existing["fecha"], errors="coerce").dt.date
            df_existing["justificado"] = df_existing["justificado"].map(
                {"True":True,"False":False,"1":True,"0":False}).fillna(False)
            # Combinar y deduplicar — id_atraso es la clave única de Syscol
            eventos = pd.concat([df_existing, eventos], ignore_index=True)
            antes = len(eventos)
            eventos = eventos.drop_duplicates(subset=["id_atraso"], keep="last")
            nuevos = antes - len(eventos)
            if nuevos < 0:  # hubo duplicados eliminados
                log.info(f"  Deduplicados {abs(nuevos)} eventos ya existentes en gold")
            log.info(f"  Total acumulado: {len(eventos)} eventos")
        except Exception as e:
            log.warning(f"  No se pudo cargar gold existente: {e} — usando solo CSV nuevo")

    alumnos = (
        eventos.groupby(["rut_norm", "nombre", "curso"], as_index=False)
        .agg(
            n_atrasos       = ("id_atraso",       "count"),
            n_justificados  = ("justificado",      "sum"),
            n_graves        = ("clasificacion",    lambda x: (x == "GRAVE").sum()),
            n_leves         = ("clasificacion",    lambda x: (x == "LEVE").sum()),
            dias_con_atraso = ("fecha",            "nunique"),
            primer_atraso   = ("fecha_hora",       "min"),
            ultimo_atraso   = ("fecha_hora",       "max"),
        )
    )
    alumnos["pct_justificados"] = (
        (alumnos["n_justificados"] / alumnos["n_atrasos"]).fillna(0) * 100
    ).round(1)
    # Alerta considera especialmente los atrasos GRAVES (generan ausencia)
    alumnos["alerta"] = alumnos.apply(
        lambda r: "CRITICO" if r["n_graves"] >= 3
        else ("ALTO"   if r["n_graves"] >= 1 or r["n_atrasos"] >= 6
        else ("MEDIO"  if r["n_atrasos"] >= 3
        else  "BAJO")),
        axis=1
    )

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

    # ── Análisis horario ──────────────────────────────────────────────
    # Parsear hora y filtrar registros sin hora válida (00:00 = sin dato)
    ev_hora = eventos.copy()
    ev_hora["hora_dt"] = pd.to_datetime(ev_hora["hora"], format="%H:%M:%S", errors="coerce")
    ev_hora["hora_min"] = ev_hora["hora_dt"].dt.hour * 60 + ev_hora["hora_dt"].dt.minute
    # Filtrar horas inválidas (00:00 o sin datos)
    ev_hora = ev_hora[(ev_hora["hora_min"] > 0) & ev_hora["hora_dt"].notna()]
    # Marcar corte MINEDUC
    ev_hora["es_grave"] = ev_hora["hora_min"] > CORTE_HORA_MINUTOS

    # Bloques de 10 minutos
    ev_hora["bloque"] = ev_hora["hora_min"].apply(
        lambda m: f"{(m//10*10)//60:02d}:{(m//10*10)%60:02d}"
    )

    # Tabla por bloque horario
    by_bloque = (
        ev_hora.groupby("bloque", as_index=False)
        .agg(
            atrasos     = ("id_atraso",  "count"),
            alumnos     = ("rut_norm",   "nunique"),
            justificados= ("justificado","sum"),
            graves      = ("es_grave",   "sum"),
        )
        .sort_values("bloque")
    )
    by_bloque["pct_justificados"] = (
        (by_bloque["justificados"] / by_bloque["atrasos"]).fillna(0) * 100
    ).round(1)
    by_bloque["pct_del_total"] = (
        by_bloque["atrasos"] / len(ev_hora) * 100
    ).round(1)
    by_bloque["pct_graves"] = (
        by_bloque["graves"] / by_bloque["atrasos"].replace(0,1) * 100
    ).round(1)
    by_bloque["es_post_corte"] = by_bloque["bloque"] > "09:30"

    # Tabla por día de la semana
    ev_hora["fecha_dt"] = pd.to_datetime(ev_hora["fecha"], errors="coerce")
    ev_hora["dia_semana_num"] = ev_hora["fecha_dt"].dt.dayofweek  # 0=Lunes
    ev_hora["dia_semana"]     = ev_hora["fecha_dt"].dt.day_name()
    dia_map = {
        "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
        "Thursday": "Jueves", "Friday": "Viernes",
        "Saturday": "Sábado", "Sunday": "Domingo"
    }
    ev_hora["dia_label"] = ev_hora["dia_semana"].map(dia_map).fillna(ev_hora["dia_semana"])

    by_dia = (
        ev_hora.groupby(["dia_semana_num", "dia_label"], as_index=False)
        .agg(
            atrasos      = ("id_atraso", "count"),
            alumnos      = ("rut_norm",  "nunique"),
            justificados = ("justificado","sum"),
        )
        .sort_values("dia_semana_num")
        .drop(columns=["dia_semana_num"])
    )
    by_dia["pct_del_total"] = (
        by_dia["atrasos"] / len(ev_hora) * 100
    ).round(1)

    # Tabla por período (bloque de clase)
    by_periodo = (
        eventos[eventos["periodo"].fillna("").astype(str).str.strip() != ""]
        .groupby("periodo", as_index=False)
        .agg(
            atrasos      = ("id_atraso", "count"),
            alumnos      = ("rut_norm",  "nunique"),
            justificados = ("justificado","sum"),
        )
        .sort_values("atrasos", ascending=False)
    )
    by_periodo["pct_del_total"] = (
        by_periodo["atrasos"] / total_eventos * 100
        if (total_eventos := len(eventos)) > 0 else 0
    ).round(1)

    # ── Cruce con matrícula para análisis por comuna ─────────────────
    by_comuna: pd.DataFrame = pd.DataFrame()
    if df_matricula is not None and not df_matricula.empty:
        def _norm_nombre(s):
            return str(s).strip().upper()

        df_mat = df_matricula.copy()
        df_mat["_nombre_key"] = df_mat["nombre"].apply(_norm_nombre) if "nombre" in df_mat.columns else ""
        alumnos_com = alumnos.copy()
        alumnos_com["_nombre_key"] = alumnos_com["nombre"].apply(_norm_nombre)

        cruce = alumnos_com.merge(
            df_mat[["_nombre_key","comuna","specialty","level"]].drop_duplicates("_nombre_key"),
            on="_nombre_key", how="left"
        )

        by_comuna = (
            cruce[cruce["comuna"].notna()]
            .groupby("comuna", as_index=False)
            .agg(
                alumnos       = ("rut_norm", "nunique"),
                total_atrasos = ("n_atrasos", "sum"),
                criticos      = ("alerta", lambda x: (x == "CRITICO").sum()),
                altos         = ("alerta", lambda x: (x == "ALTO").sum()),
                medios        = ("alerta", lambda x: (x == "MEDIO").sum()),
            )
            .sort_values("total_atrasos", ascending=False)
        )
        by_comuna["prom_por_alumno"] = (by_comuna["total_atrasos"] / by_comuna["alumnos"]).round(1)
        by_comuna["pct_del_total"]   = (by_comuna["total_atrasos"] / by_comuna["total_atrasos"].sum() * 100).round(1)
        by_comuna.to_csv(gold_dir / "atrasos_by_comuna.csv", index=False)

    eventos.to_csv(gold_dir / "atrasos_eventos.csv",  index=False)
    alumnos.to_csv(gold_dir / "atrasos_alumnos.csv",  index=False)
    cursos.to_csv( gold_dir / "atrasos_cursos.csv",   index=False)
    serie.to_csv(  gold_dir / "atrasos_serie.csv",    index=False)
    by_bloque.to_csv( gold_dir / "atrasos_by_bloque.csv",  index=False)
    by_dia.to_csv(    gold_dir / "atrasos_by_dia.csv",      index=False)
    by_periodo.to_csv(gold_dir / "atrasos_by_periodo.csv",  index=False)

    _n_graves = int((eventos["clasificacion"] == "GRAVE").sum()) if "clasificacion" in eventos.columns else 0
    meta = pd.DataFrame([
        {
            "corte":          str(corte),
            "n_dias":         int(serie["fecha"].nunique()) if not serie.empty else 0,
            "eventos":        int(len(eventos)),
            "alumnos":        int(eventos["rut_norm"].nunique()) if not eventos.empty else 0,
            "atrasos_graves": _n_graves,
            "atrasos_leves":  int(len(eventos)) - _n_graves,
            "corte_mineduc":  "09:30",
            "generado":       pd.Timestamp.now().isoformat(),
            "csv_path":       str(csv_path),
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
        "eventos":    eventos,
        "alumnos":    alumnos,
        "cursos":     cursos,
        "serie":      serie,
        "by_bloque":  by_bloque,
        "by_dia":     by_dia,
        "by_periodo": by_periodo,
        "by_comuna":  by_comuna,
        "n_dias":     int(serie["fecha"].nunique()) if not serie.empty else 0,
        "corte":      corte,
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