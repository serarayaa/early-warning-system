"""
SIGMA — Pipeline de datos históricos 2022-2025
src/staging/build_historico.py

Procesa los CSVs históricos de Syscol y genera tablas gold
con columna 'anio' para análisis de tendencias multi-año.

Módulos soportados: matricula, atrasos
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

log = logging.getLogger("sigma.historico")

ANIOS = [2022, 2023, 2024, 2025]


# ── Helpers ───────────────────────────────────────────────────────────

def _read_csv(path: Path) -> pd.DataFrame:
    for enc in ["latin-1", "utf-8-sig", "utf-8", "cp1252"]:
        try:
            df = pd.read_csv(path, sep=";", encoding=enc,
                             dtype=str, on_bad_lines="skip")
            if len(df.columns) >= 3:
                return df
        except Exception:
            continue
    raise ValueError(f"No se pudo leer: {path}")


def _normalize_rut(s: str) -> str:
    s = str(s).strip()
    s = re.sub(r"[^0-9kK\-]", "", s).upper()
    return s


def _derive_specialty(course_code: str) -> str:
    c = str(course_code).strip().upper()
    m = re.search(r"\d+EM([A-Z])", c)
    if not m:
        return "COMUN"
    letra = m.group(1)
    if letra in "ABCD":   return "TELECOM"
    if letra in "EF":     return "ELECTRONICA"
    if letra in "GH":     return "MECANICA"
    return "COMUN"


# ── Matrícula histórica ───────────────────────────────────────────────

def procesar_matricula_anio(csv_path: Path, anio: int) -> pd.DataFrame:
    df = _read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]

    out = pd.DataFrame()
    out["anio"] = anio

    # RUT
    col_rut = next((c for c in df.columns if "número rut" in c.lower() or "numero rut" in c.lower()), None)
    out["rut_norm"] = (df[col_rut].apply(_normalize_rut) if col_rut else "")

    # Nombre
    col_nom = next((c for c in df.columns if c.strip().lower() == "nombre"), None)
    out["nombre"] = df[col_nom].fillna("").str.strip().str.upper() if col_nom else ""

    # Curso
    col_curso = next((c for c in df.columns if "código curso" in c.lower() or "codigo curso" in c.lower()), None)
    out["course_code"] = df[col_curso].fillna("").str.strip().str.upper() if col_curso else ""
    out["specialty"]   = out["course_code"].apply(_derive_specialty)
    m = out["course_code"].str.extract(r"^(\d)")
    out["level"] = pd.to_numeric(m[0], errors="coerce").astype("Int64")

    # Estado
    col_estado = next((c for c in df.columns if "estado" in c.lower()), None)
    out["estado"] = df[col_estado].fillna("").str.strip() if col_estado else ""
    out["activo"] = out["estado"].str.lower().str.contains("matriculado", na=False)

    # Retiro
    col_ret = next((c for c in df.columns if "fecha retiro" in c.lower()), None)
    out["fecha_retiro"] = pd.to_datetime(
        df[col_ret], dayfirst=True, errors="coerce"
    ) if col_ret else pd.NaT

    # Sexo
    col_sx = next((c for c in df.columns if c.strip().lower() == "sexo"), None)
    out["sexo"] = df[col_sx].fillna("").str.strip().str.upper() if col_sx else ""

    # Nacionalidad (no en 2025)
    col_nac = next((c for c in df.columns if "nacionalidad" in c.lower()), None)
    out["nacionalidad"] = df[col_nac].fillna("").str.strip() if col_nac else ""

    # Repitente
    col_rep = next((c for c in df.columns if "repitente" in c.lower()), None)
    if col_rep:
        out["is_repeat"] = df[col_rep].fillna("").str.strip().str.upper().isin(
            ["-", "SÍ", "SI", "S", "TRUE", "1"]
        )
        # Syscol: '-' = sí repite en algunos formatos, verificar
        out["is_repeat"] = df[col_rep].fillna("").str.strip().str.upper().isin(
            ["-"]  # en Syscol '-' en Repitente = SÍ
        )
    else:
        out["is_repeat"] = False

    # Edad
    col_edad = next((c for c in df.columns if c.strip().lower() == "edad"), None)
    out["edad"] = pd.to_numeric(df[col_edad], errors="coerce") if col_edad else pd.NA

    # Comuna
    col_com = next((c for c in df.columns if c.strip().lower() == "comuna"), None)
    out["comuna"] = df[col_com].fillna("").str.strip().str.upper() if col_com else ""

    out = out[out["rut_norm"].str.len() > 3].copy()
    out["anio"] = anio  # reasignar después de filtros
    log.info(f"  Matrícula {anio}: {len(out)} alumnos")
    return out


# ── Atrasos históricos ────────────────────────────────────────────────

def procesar_atrasos_anio(csv_path: Path, anio: int) -> pd.DataFrame:
    df = _read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]

    out = pd.DataFrame()
    out["anio"]    = anio
    out["id_atraso"] = df.get("idAtraso", pd.Series(range(len(df)))).fillna("").astype(str)

    # Fecha y hora
    col_fecha = "AtraFecha"
    if col_fecha in df.columns:
        dt = pd.to_datetime(df[col_fecha], dayfirst=True, errors="coerce")
        out["fecha"] = dt.dt.date
        out["hora"]  = dt.dt.strftime("%H:%M:%S")
        out["mes"]   = dt.dt.month
        out["dia_semana"] = dt.dt.day_name()
    else:
        out["fecha"] = pd.NaT
        out["hora"]  = ""
        out["mes"]   = 0
        out["dia_semana"] = ""

    # RUT — histórico tiene RUT real en AluRut
    out["rut_norm"] = df.get("AluRut", pd.Series([""] * len(df))).apply(_normalize_rut)

    # Nombre
    out["nombre"] = df.get("AluNombre", pd.Series([""] * len(df))).fillna("").str.strip().str.upper()

    # Curso
    out["curso"] = df.get("CurNombreCorto", pd.Series([""] * len(df))).fillna("").str.strip().str.upper()
    out["specialty"] = out["curso"].apply(_derive_specialty)

    # Período
    col_per = "Per0" if "Per0" in df.columns else ("Per1" if "Per1" in df.columns else None)
    out["periodo"] = df[col_per].fillna("").astype(str).str.strip() if col_per else ""
    out["periodo"] = out["periodo"].replace("-", "")

    # Tipo de atraso
    out["tipo_atraso"] = df.get("TipoNombre", pd.Series([""] * len(df))).fillna("").str.strip()

    # Justificado
    col_just = "Justifica"
    if col_just in df.columns:
        out["justificado"] = df[col_just].fillna("").astype(str).str.strip().str.upper().isin(
            ["SI", "SÍ", "S", "TRUE", "1", "YES"]
        )
    else:
        out["justificado"] = False

    # Hora en minutos para análisis
    def _hora_min(h):
        try:
            parts = str(h).split(":")
            return int(parts[0]) * 60 + int(parts[1])
        except Exception:
            return None

    out["hora_min"] = out["hora"].apply(_hora_min)
    out["bloque_10min"] = out["hora_min"].apply(
        lambda m: f"{(m//10*10)//60:02d}:{(m//10*10)%60:02d}" if m else ""
    )

    out = out[out["fecha"].notna()].copy()
    # Filtrar solo el año correcto (algunos CSVs tienen fechas del año siguiente)
    out["fecha"] = pd.to_datetime(out["fecha"], errors="coerce")
    out = out[out["fecha"].dt.year == anio].copy()
    out["fecha"] = out["fecha"].dt.date
    out["anio"]  = anio  # reasignar después de filtros

    log.info(f"  Atrasos {anio}: {len(out)} eventos")
    return out




# ── Especialidad desde curso ──────────────────────────────────────────
def _specialty_from_curso(curso: str) -> str:
    import re
    m = re.search(r"\d+EM([A-Z])", str(curso).upper())
    if not m:
        return "COMUN"
    l = m.group(1)
    if l in "ABCD": return "TELECOM"
    if l in "EF":   return "ELECTRONICA"
    if l in "GH":   return "MECANICA"
    return "COMUN"


# ── Asistencia histórica ──────────────────────────────────────────────

def procesar_asistencia_anio(csv_path: Path, anio: int) -> pd.DataFrame:
    """
    Genera resumen mensual + diario de asistencia para un año.
    Retorna filas: anio, mes, fecha, presentes, ausentes, pct_asistencia.
    """
    df = _read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]
    df = df[df['Fecha'].notna()].copy()

    df['fecha_dt'] = pd.to_datetime(df['Fecha'], dayfirst=True, errors='coerce')
    df = df[df['fecha_dt'].notna() & (df['fecha_dt'].dt.year == anio)].copy()

    if df.empty:
        return pd.DataFrame()

    df['Presente'] = pd.to_numeric(df.get('Presente', 0), errors='coerce').fillna(0).astype(int)
    df['Ausente']  = pd.to_numeric(df.get('Ausente',  0), errors='coerce').fillna(0).astype(int)

    col_curso = next((c for c in df.columns if 'curNombreCorto' in c or c == 'CurNombreCorto'), None)
    df['specialty'] = df[col_curso].apply(_specialty_from_curso) if col_curso else 'COMUN'

    # Resumen diario por especialidad
    daily = df.groupby(['fecha_dt','specialty'], as_index=False).agg(
        presentes=('Presente','sum'),
        ausentes =('Ausente', 'sum'),
    )
    daily['anio']           = anio
    daily['mes']            = daily['fecha_dt'].dt.month
    daily['fecha']          = daily['fecha_dt'].dt.date
    daily['pct_asistencia'] = (daily['presentes'] / (daily['presentes'] + daily['ausentes']).replace(0, float('nan')) * 100).round(1)
    daily = daily[['anio','mes','fecha','specialty','presentes','ausentes','pct_asistencia']]

    log.info(f"  Asistencia {anio}: {len(daily):,} filas diarias ({df['fecha_dt'].dt.date.nunique()} días)")
    return daily


# ── Observaciones históricas ──────────────────────────────────────────

def procesar_observaciones_anio(csv_path: Path, anio: int) -> pd.DataFrame:
    """Genera resumen mensual de observaciones por tipo."""
    df = _read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]

    df['fecha_dt'] = pd.to_datetime(df.get('Fecha', pd.Series()), dayfirst=True, errors='coerce')
    df = df[df['fecha_dt'].notna() & (df['fecha_dt'].dt.year == anio)].copy()

    if df.empty:
        return pd.DataFrame()

    col_curso = next((c for c in df.columns if c in ['NCCurso','CurNombreCorto']), None)
    df['specialty'] = df[col_curso].apply(_specialty_from_curso) if col_curso else 'COMUN'
    df['tipo'] = df.get('TipoCodigo', pd.Series(['OBS']*len(df))).fillna('OBS').str.strip().str.upper()
    df['mes']  = df['fecha_dt'].dt.month
    df['anio'] = anio

    out = df.groupby(['anio','mes','specialty','tipo'], as_index=False).size().rename(columns={'size':'cantidad'})
    log.info(f"  Observaciones {anio}: {len(df):,} registros")
    return out

# ── Pipeline principal ────────────────────────────────────────────────

def run(
    hist_dir: Path | str,
    gold_dir: Path | str = "data/gold/historico",
    anios: list[int] | None = None,
) -> dict:
    """
    Procesa todos los años históricos y genera tablas consolidadas.

    hist_dir: carpeta raíz con subcarpetas 2022/, 2023/, 2024/, 2025/
    gold_dir: donde guardar los resultados
    """
    hist_dir = Path(hist_dir)
    gold_dir = Path(gold_dir)
    gold_dir.mkdir(parents=True, exist_ok=True)

    if anios is None:
        anios = ANIOS

    frames_mat = []
    frames_atr = []
    frames_asi = []
    frames_obs = []

    for anio in anios:
        anio_dir = hist_dir / str(anio)
        if not anio_dir.exists():
            log.warning(f"No existe carpeta para {anio}: {anio_dir}")
            continue

        log.info(f"\n── Procesando {anio} ──")

        # Matrícula
        for f in list(anio_dir.glob("matriculados_*.csv")):
            try: frames_mat.append(procesar_matricula_anio(f, anio)); break
            except Exception as e: log.error(f"  Error matrícula {anio}: {e}")

        # Atrasos
        for f in list(anio_dir.glob("atrasos_*.csv")):
            try: frames_atr.append(procesar_atrasos_anio(f, anio)); break
            except Exception as e: log.error(f"  Error atrasos {anio}: {e}")

        # Asistencia
        for f in list(anio_dir.glob("asistencia*.csv")):
            try: frames_asi.append(procesar_asistencia_anio(f, anio)); break
            except Exception as e: log.error(f"  Error asistencia {anio}: {e}")

        # Observaciones
        for f in list(anio_dir.glob("observaciones_*.csv")):
            try: frames_obs.append(procesar_observaciones_anio(f, anio)); break
            except Exception as e: log.error(f"  Error observaciones {anio}: {e}")

    # Consolidar
    df_mat_hist = pd.concat(frames_mat, ignore_index=True) if frames_mat else pd.DataFrame()
    df_atr_hist = pd.concat(frames_atr, ignore_index=True) if frames_atr else pd.DataFrame()
    df_asi_hist = pd.concat(frames_asi, ignore_index=True) if frames_asi else pd.DataFrame()
    df_obs_hist = pd.concat(frames_obs, ignore_index=True) if frames_obs else pd.DataFrame()

    def _save(df, name):
        if not df.empty:
            df.to_csv(gold_dir / name, index=False, encoding="utf-8-sig")
            log.info(f"✅ {name}: {len(df):,} filas")

    _save(df_mat_hist, "hist_matricula.csv")
    _save(df_atr_hist, "hist_atrasos.csv")
    _save(df_asi_hist, "hist_asistencia.csv")
    _save(df_obs_hist, "hist_observaciones.csv")

    # Resúmenes anuales
    if not df_mat_hist.empty:
        resumen_mat = df_mat_hist.groupby("anio", as_index=False).agg(
            total      = ("rut_norm",     "count"),
            activos    = ("activo",        "sum"),
            retirados  = ("fecha_retiro",  lambda x: x.notna().sum()),
            extranjeros= ("nacionalidad",  lambda x: (~x.isin(["", "CHILENA", "CHILENO", "CHILE"])).sum()),
        )
        _save(resumen_mat, "hist_matricula_resumen.csv")

    if not df_atr_hist.empty:
        resumen_atr = df_atr_hist.groupby("anio", as_index=False).agg(
            eventos        = ("id_atraso",    "count"),
            alumnos_unicos = ("rut_norm",     "nunique"),
            justificados   = ("justificado",  "sum"),
            pico_hora      = ("bloque_10min", lambda x: x.mode().iloc[0] if len(x) > 0 else "—"),
        )
        resumen_atr["pct_justificados"] = (resumen_atr["justificados"] / resumen_atr["eventos"] * 100).round(1)
        _save(resumen_atr, "hist_atrasos_resumen.csv")

    if not df_asi_hist.empty:
        resumen_asi = df_asi_hist.groupby(["anio", "mes"], as_index=False).agg(
            presentes=("presentes", "sum"),
            ausentes =("ausentes",  "sum"),
        )
        resumen_asi["pct_asistencia"] = (
            resumen_asi["presentes"] / (resumen_asi["presentes"] + resumen_asi["ausentes"]) * 100
        ).round(1)
        _save(resumen_asi, "hist_asistencia_mensual.csv")

    if not df_obs_hist.empty:
        _save(df_obs_hist, "hist_observaciones_mensual.csv")

    return {
        "matricula":     df_mat_hist,
        "atrasos":       df_atr_hist,
        "asistencia":    df_asi_hist,
        "observaciones": df_obs_hist,
    }