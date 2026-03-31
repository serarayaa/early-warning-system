from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.staging.build_stg_atrasos import run as run_atrasos
from src.validation.schema_registry import SCHEMA_ATRASOS
from src.validation.schema_validator import validar_columnas
from ui.executive_pdf import generate_pdf_atrasos, render_pdf_preview, show_pretty_table
from ui.schema_feedback import mostrar_validacion_esquema

MIME_CSV = "text/csv"


def _kpi(col, val, label, color="#2563eb", sub=None):
    _sub = f'<div style="font-size:0.62rem;color:#64748b;margin-top:2px">{sub}</div>' if sub else ""
    col.markdown(
        f"""
        <div style="background:#0d1220;border-radius:8px;padding:14px 8px;text-align:center;
                    border:1px solid rgba(99,179,237,0.10); border-bottom:3px solid {color}">
            <div style="font-size:1.7rem;font-weight:700;color:{color}">{val}</div>
            <div style="font-size:0.68rem;color:#94a3b8;margin-top:2px;text-transform:uppercase">{label}</div>
            {_sub}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _read_uploaded_csv(uploaded_file, nrows: int | None = None) -> pd.DataFrame:
    last_err: Exception | None = None
    for enc in ["utf-8", "utf-8-sig", "cp1252", "latin1"]:
        try:
            uploaded_file.seek(0)
            return pd.read_csv(
                uploaded_file,
                sep=";",
                nrows=nrows,
                encoding=enc,
                on_bad_lines="skip",
            )
        except Exception as e:
            last_err = e
    raise ValueError(f"No se pudo leer CSV de atrasos con encodings esperados: {last_err}")


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def render_atrasos_page():
    st.markdown(
        """
        <div class="sigma-header">
            <div>
                <div class="sigma-logo" style="font-size:1.5rem">SIGMA</div>
                <div class="sigma-tagline">Atrasos</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">Atrasos diarios</div>', unsafe_allow_html=True)

    atrasos_gold = Path("data/gold/atrasos")
    atrasos_file = st.file_uploader(
        "Cargar CSV de Syscol (atrasos_*.csv)",
        type=["csv"],
        key="atrasos_uploader",
    )

    resultado_validacion = None
    if atrasos_file is not None:
        try:
            preview_df = _read_uploaded_csv(atrasos_file, nrows=5)
            resultado_validacion = validar_columnas(preview_df.columns.tolist(), SCHEMA_ATRASOS)
            mostrar_validacion_esquema(resultado_validacion)
            atrasos_file.seek(0)
        except Exception as e:
            st.markdown(
                f'<div class="sigma-alert danger">No se pudo analizar la estructura del archivo: {e}</div>',
                unsafe_allow_html=True,
            )
            atrasos_file.seek(0)

    df_eventos    = None
    df_alumnos    = None
    df_cursos     = None
    df_serie      = None
    df_by_bloque  = None
    df_by_dia     = None
    df_by_periodo = None
    df_by_comuna  = None
    corte_lbl = "-"

    if (atrasos_gold / "atrasos_eventos.csv").exists() and atrasos_file is None:
        try:
            df_eventos = pd.read_csv(atrasos_gold / "atrasos_eventos.csv", encoding="utf-8")
            df_alumnos = pd.read_csv(atrasos_gold / "atrasos_alumnos.csv", encoding="utf-8")
            df_cursos     = pd.read_csv(atrasos_gold / "atrasos_cursos.csv",      encoding="utf-8")
            df_serie      = pd.read_csv(atrasos_gold / "atrasos_serie.csv",       encoding="utf-8")
            df_by_bloque  = pd.read_csv(atrasos_gold / "atrasos_by_bloque.csv",   encoding="utf-8") if (atrasos_gold / "atrasos_by_bloque.csv").exists() else None
            df_by_dia     = pd.read_csv(atrasos_gold / "atrasos_by_dia.csv",      encoding="utf-8") if (atrasos_gold / "atrasos_by_dia.csv").exists() else None
            df_by_periodo = pd.read_csv(atrasos_gold / "atrasos_by_periodo.csv",  encoding="utf-8") if (atrasos_gold / "atrasos_by_periodo.csv").exists() else None
            df_by_comuna  = pd.read_csv(atrasos_gold / "atrasos_by_comuna.csv",    encoding="utf-8") if (atrasos_gold / "atrasos_by_comuna.csv").exists() else None
            df_serie["fecha"] = pd.to_datetime(df_serie["fecha"])
            meta = pd.read_csv(atrasos_gold / "atrasos_meta.csv",    encoding="utf-8")
            corte_lbl = str(meta.iloc[0].get("corte", "-"))
            st.markdown(
                f'<div class="sigma-alert info">Datos de atrasos cargados desde gold - corte: <b>{corte_lbl}</b></div>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.markdown(
                f'<div class="sigma-alert danger">Error cargando datos guardados de atrasos: {e}</div>',
                unsafe_allow_html=True,
            )

    if atrasos_file is not None:
        try:
            if resultado_validacion is not None and not resultado_validacion["es_valido"]:
                st.error("El archivo no cumple con la estructura minima esperada para Atrasos.")
            else:
                df_raw = _read_uploaded_csv(atrasos_file)

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".csv",
                    mode="w",
                    encoding="utf-8-sig",
                    newline="",
                ) as tmp:
                    df_raw.to_csv(tmp.name, index=False, sep=";")
                    tmp_path = tmp.name

                try:
                    # Cargar matrícula para cruce de comunas
                    from ui.enrollment_data import load_parquet_safe
                    import glob as _glob
                    _enroll_gold = Path("data/gold/enrollment")
                    _enroll_files = sorted(_glob.glob(str(_enroll_gold / "enrollment_current__*.parquet")))
                    _df_mat = None
                    if _enroll_files:
                        _valid = [f for f in _enroll_files if "20261231" not in f]
                        if _valid:
                            _df_mat = load_parquet_safe(_valid[-1])
                    r = run_atrasos(tmp_path, atrasos_gold, df_matricula=_df_mat)
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

                df_eventos    = r["eventos"]
                df_alumnos    = r["alumnos"]
                df_cursos     = r["cursos"]
                df_serie      = r["serie"]
                df_by_bloque  = r.get("by_bloque")
                df_by_dia     = r.get("by_dia")
                df_by_periodo = r.get("by_periodo")
                df_by_comuna  = r.get("by_comuna")
                corte_lbl     = str(r["corte"])

                st.markdown(
                    f'<div class="sigma-alert success">Atrasos procesado - {len(df_eventos):,} eventos hasta {corte_lbl}</div>',
                    unsafe_allow_html=True,
                )
        except Exception as e:
            st.markdown(
                f'<div class="sigma-alert danger">Error procesando CSV de atrasos: {e}</div>',
                unsafe_allow_html=True,
            )

    if df_eventos is None or df_eventos.empty:
        st.markdown(
            """
            <div class="sigma-alert info">
                <b>Como usar el modulo de Atrasos:</b><br>
                1. Exporta el reporte de atrasos desde Syscol como CSV<br>
                2. Cargalo desde este modulo<br>
                3. SIGMA construira indicadores por alumno, curso y tendencia diaria
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown('<div class="section-title" style="margin-top:12px">Indicadores generales</div>', unsafe_allow_html=True)

    total_atrasos  = len(df_eventos)
    alumnos_unicos = int(df_eventos["rut_norm"].nunique()) if "rut_norm" in df_eventos.columns else 0
    cursos_afect   = int(df_eventos["curso"].nunique()) if "curso" in df_eventos.columns else 0
    justificados   = int(df_eventos["justificado"].sum()) if "justificado" in df_eventos.columns else 0
    pct_just       = round(justificados / total_atrasos * 100, 1) if total_atrasos else 0.0
    reincidentes   = int((df_alumnos["n_atrasos"] >= 3).sum()) if "n_atrasos" in df_alumnos.columns else 0
    criticos       = int((df_alumnos["alerta"] == "CRITICO").sum()) if "alerta" in df_alumnos.columns else 0
    prom_por_alumno = round(total_atrasos / alumnos_unicos, 1) if alumnos_unicos else 0

    # Clasificación MINEDUC: LEVE (≤9:30 → presente) vs GRAVE (>9:30 → ausente)
    n_graves = int((df_eventos["clasificacion"] == "GRAVE").sum()) if "clasificacion" in df_eventos.columns else 0
    n_leves  = total_atrasos - n_graves
    pct_graves = round(n_graves / total_atrasos * 100, 1) if total_atrasos else 0.0

    # Fila 1: KPIs generales
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    _kpi(c1, f"{total_atrasos:,}",     "Atrasos totales",       "#2563eb")
    _kpi(c2, f"{alumnos_unicos:,}",    "Alumnos involucrados",  "#16a34a")
    _kpi(c3, f"{pct_just}%",           "Justificados",          "#d97706")
    _kpi(c4, f"{reincidentes:,}",      "Reincidentes (≥3)",     "#7c3aed")
    _kpi(c5, f"{criticos:,}",          "Críticos (≥3 graves)",  "#dc2626")
    _kpi(c6, f"{prom_por_alumno}",     "Prom. atrasos/alumno",  "#6b7280")

    # Fila 2: KPIs norma MINEDUC
    st.markdown(
        '<div class="section-title" style="margin-top:8px">'
        'Clasificación norma MINEDUC — corte 9:30</div>',
        unsafe_allow_html=True)
    cm1, cm2, cm3, cm4 = st.columns(4)
    _kpi(cm1, f"{n_leves:,}",      "Leves (≤9:30, presente)", "#16a34a",
         sub=f"{100-pct_graves:.1f}% del total")
    _kpi(cm2, f"{n_graves:,}",     "Graves (>9:30, ausente)",  "#dc2626",
         sub=f"{pct_graves:.1f}% del total")
    # Alumnos con al menos 1 atraso grave
    alumnos_con_grave = int((df_alumnos["n_graves"] > 0).sum()) if "n_graves" in df_alumnos.columns else 0
    _kpi(cm3, f"{alumnos_con_grave:,}", "Alumnos con atraso grave", "#dc2626",
         sub="genera ausencia MINEDUC")
    # Alumnos con ≥3 atrasos graves (crítico real)
    alumnos_critico_grave = int((df_alumnos["n_graves"] >= 3).sum()) if "n_graves" in df_alumnos.columns else 0
    _kpi(cm4, f"{alumnos_critico_grave:,}", "Críticos graves (≥3)", "#991b1b",
         sub="impacto directo en asistencia")

    if n_graves > 0:
        st.markdown(
            f'<div class="sigma-alert warn">⚠️ <b>Norma MINEDUC:</b> Los {n_graves} atrasos graves '
            f'(después de las 9:30) generan ausencia automática ese día. '
            f'Los {alumnos_con_grave} alumnos afectados pueden tener su % de asistencia '
            f'reducido sin que aparezca explícitamente en el módulo de asistencia.</div>',
            unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Sub-tabs ──────────────────────────────────────────────────────
    tab_viz, tab_ranking, tab_tipos, tab_horario, tab_comunas, tab_alumno = st.tabs([
        "📈 Visualizaciones",
        "🏫 Ranking cursos",
        "🏷️ Tipos de atraso",
        "🕐 Análisis horario",
        "📍 Por comuna",
        "🔍 Buscar alumno",
    ])

    # ── VIZ ───────────────────────────────────────────────────────────
    with tab_viz:
        g1, g2 = st.columns(2)
        with g1:
            if df_serie is not None and not df_serie.empty and "fecha" in df_serie.columns:
                fig_serie = go.Figure()
                fig_serie.add_trace(go.Scatter(
                    x=df_serie["fecha"], y=df_serie["atrasos_dia"],
                    mode="lines+markers",
                    line={"color":"#2563eb","width":2.5},
                    marker={"size":7,"color":"#2563eb"},
                    hovertemplate="<b>%{x|%d/%m}</b>: %{y} atrasos<extra></extra>",
                ))
                prom_d = round(df_serie["atrasos_dia"].mean(), 1) if "atrasos_dia" in df_serie.columns else 0
                fig_serie.add_hline(y=prom_d, line_dash="dash", line_color="rgba(99,179,237,0.4)",
                    annotation_text=f"Prom {prom_d:.0f}", annotation_font={"color":"#63b3ed","size":9})
                fig_serie.update_layout(
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color":"#e2e8f0"}, height=300,
                    title={"text":f"Serie diaria de atrasos (corte {corte_lbl})","font":{"size":12,"color":"#63b3ed"},"x":0},
                    xaxis={"gridcolor":"#1a2035"}, yaxis={"gridcolor":"#1a2035"},
                    margin={"l":16,"r":16,"t":40,"b":16}, showlegend=False,
                )
                st.plotly_chart(fig_serie, use_container_width=True, config={"displayModeBar":False})
            else:
                st.info("Sin serie diaria disponible.")

        with g2:
            # Distribución por nivel de alerta — compatible pandas v1/v2
            if "alerta" in df_alumnos.columns:
                orden_alerta = ["CRITICO", "ALTO", "MEDIO", "BAJO"]
                colores_alert = {"CRITICO":"#dc2626","ALTO":"#d97706","MEDIO":"#7c3aed","BAJO":"#16a34a"}
                conteos = {nivel: int((df_alumnos["alerta"] == nivel).sum()) for nivel in orden_alerta}
                fig_alert = go.Figure(go.Bar(
                    x=orden_alerta,
                    y=[conteos[n] for n in orden_alerta],
                    marker_color=[colores_alert[n] for n in orden_alerta],
                    text=[conteos[n] for n in orden_alerta],
                    textposition="outside",
                    textfont={"size":12,"color":"#e2e8f0"},
                    hovertemplate="<b>%{x}</b>: %{y} alumnos<extra></extra>",
                ))
                fig_alert.update_layout(
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color":"#e2e8f0"}, height=300,
                    title={"text":"Distribución por nivel de alerta","font":{"size":12,"color":"#63b3ed"},"x":0},
                    xaxis={"gridcolor":"rgba(0,0,0,0)"},
                    yaxis={"gridcolor":"#1a2035"},
                    margin={"l":10,"r":10,"t":40,"b":10}, showlegend=False,
                )
                st.plotly_chart(fig_alert, use_container_width=True, config={"displayModeBar":False})

    # ── RANKING CURSOS ────────────────────────────────────────────────
    with tab_ranking:
        st.markdown('<div class="section-title">Ranking de cursos por atrasos — semáforo</div>', unsafe_allow_html=True)
        if df_cursos is not None and not df_cursos.empty and "total_atrasos" in df_cursos.columns:
            df_c = df_cursos.copy().sort_values("total_atrasos", ascending=False)
            max_atr = df_c["total_atrasos"].max() or 1

            def _sem_atrasos(v, mx):
                pct = v / mx
                if pct >= 0.7: return "🔴 Alto"
                if pct >= 0.4: return "🟡 Medio"
                return "🟢 Bajo"

            df_c["Estado"] = df_c["total_atrasos"].apply(lambda v: _sem_atrasos(v, max_atr))
            df_c_show = df_c.rename(columns={
                "curso":"Curso","total_atrasos":"Atrasos","alumnos_unicos":"Alumnos",
                "pct_justificados":"% Justif.","promedio_atrasos_por_alumno":"Prom/Alumno",
            })
            if "% Justif." in df_c_show.columns:
                df_c_show["% Justif."] = df_c_show["% Justif."].apply(lambda v: f"{v:.1f}%")
            if "Prom/Alumno" in df_c_show.columns:
                df_c_show["Prom/Alumno"] = df_c_show["Prom/Alumno"].apply(lambda v: f"{v:.1f}")

            col_left, col_right = st.columns([2, 3])
            with col_left:
                show_cols = [c for c in ["Curso","Atrasos","Alumnos","% Justif.","Prom/Alumno","Estado"] if c in df_c_show.columns]
                show_pretty_table(df_c_show[show_cols], max_rows=30, height=500)
            with col_right:
                top12 = df_cursos.sort_values("total_atrasos", ascending=False).head(12)
                colores_bar = [
                    _sem_atrasos(v, max_atr).split()[1] for v in top12["total_atrasos"]
                ]
                color_map_b = {"Alto":"#dc2626","Medio":"#d97706","Bajo":"#16a34a"}
                fig_bar = go.Figure(go.Bar(
                    x=top12["curso"], y=top12["total_atrasos"],
                    marker_color=[color_map_b.get(c,"#6b7280") for c in colores_bar],
                    text=top12["total_atrasos"], textposition="outside",
                    textfont={"size":11,"color":"#e2e8f0"},
                    hovertemplate="<b>%{x}</b>: %{y} atrasos<extra></extra>",
                ))
                fig_bar.update_layout(
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color":"#e2e8f0"}, height=360,
                    title={"text":"Top 12 cursos con más atrasos","font":{"size":12,"color":"#63b3ed"},"x":0},
                    xaxis={"gridcolor":"#1a2035","tickangle":-30},
                    yaxis={"gridcolor":"#1a2035"},
                    margin={"l":10,"r":10,"t":40,"b":50}, showlegend=False,
                )
                st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar":False})
        else:
            st.info("Sin datos de cursos disponibles.")

    # ── TIPOS DE ATRASO ───────────────────────────────────────────────
    with tab_tipos:
        st.markdown('<div class="section-title">Tipos de atraso más frecuentes</div>', unsafe_allow_html=True)
        if "tipo_atraso" in df_eventos.columns:
            df_tipos = (
                df_eventos[df_eventos["tipo_atraso"].astype(str).str.strip().ne("")]
                .groupby("tipo_atraso", as_index=False)
                .agg(Eventos=("tipo_atraso","count"),
                     Alumnos=("rut_norm","nunique") if "rut_norm" in df_eventos.columns else ("tipo_atraso","count"))
                .sort_values("Eventos", ascending=False)
                .head(15)
            )
            if not df_tipos.empty:
                df_tipos["% del total"] = df_tipos["Eventos"].apply(
                    lambda n: f"{round(n/total_atrasos*100,1)}%"
                )
                df_tipos = df_tipos.rename(columns={"tipo_atraso":"Tipo de Atraso"})
                t1, t2 = st.columns([2,3])
                with t1:
                    show_pretty_table(df_tipos, max_rows=15, height=400)
                with t2:
                    fig_tipos = go.Figure(go.Bar(
                        y=df_tipos["Tipo de Atraso"][::-1],
                        x=df_tipos["Eventos"][::-1],
                        orientation="h",
                        marker={"color":df_tipos["Eventos"][::-1],
                                "colorscale":[[0,"#1a2035"],[1,"#7c3aed"]]},
                        text=df_tipos["Eventos"][::-1], textposition="outside",
                        textfont={"size":11,"color":"#e2e8f0"},
                        hovertemplate="<b>%{y}</b>: %{x} eventos<extra></extra>",
                    ))
                    fig_tipos.update_layout(
                        paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                        font={"color":"#e2e8f0"}, height=400,
                        title={"text":"Frecuencia por tipo","font":{"size":12,"color":"#63b3ed"},"x":0},
                        xaxis={"gridcolor":"#1a2035"},
                        yaxis={"gridcolor":"rgba(0,0,0,0)","tickfont":{"size":10}},
                        margin={"l":10,"r":60,"t":40,"b":10}, showlegend=False,
                    )
                    st.plotly_chart(fig_tipos, use_container_width=True, config={"displayModeBar":False})
            else:
                st.info("No hay datos de tipos de atraso.")
        else:
            st.info("La columna 'tipo_atraso' no está disponible en los datos.")

    # ── ANÁLISIS HORARIO ──────────────────────────────────────────────
    with tab_horario:
        st.markdown('<div class="section-title">¿Cuándo se producen los atrasos?</div>', unsafe_allow_html=True)

        h1, h2 = st.columns(2)

        with h1:
            # Gráfico por bloque de 10 minutos
            if df_by_bloque is not None and not df_by_bloque.empty:
                df_b = df_by_bloque.copy()
                max_b = df_b["atrasos"].max() or 1
                colores_b = [
                    "#dc2626" if v/max_b >= 0.7 else ("#d97706" if v/max_b >= 0.4 else "#2563eb")
                    for v in df_b["atrasos"]
                ]
                fig_b = go.Figure(go.Bar(
                    x=df_b["bloque"], y=df_b["atrasos"],
                    marker_color=colores_b,
                    text=df_b["atrasos"], textposition="outside",
                    textfont={"size": 10, "color": "#e2e8f0"},
                    customdata=df_b["pct_del_total"],
                    hovertemplate="<b>%{x}</b><br>Atrasos: %{y}<br>% del total: %{customdata:.1f}%<extra></extra>",
                ))
                # Línea de promedio
                prom_b = df_b["atrasos"].mean()
                fig_b.add_hline(y=prom_b, line_dash="dash",
                    line_color="rgba(99,179,237,0.5)",
                    annotation_text=f"Prom {prom_b:.0f}",
                    annotation_font={"color":"#63b3ed","size":9})
                fig_b.update_layout(
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color":"#e2e8f0"}, height=340,
                    margin={"l":10,"r":10,"t":40,"b":50},
                    title={"text":"Atrasos por bloque de 10 minutos","font":{"size":12,"color":"#63b3ed"},"x":0},
                    xaxis={"gridcolor":"#1a2035","tickangle":-45,"title":"Hora de ingreso"},
                    yaxis={"gridcolor":"#1a2035"},
                    showlegend=False,
                )
                st.plotly_chart(fig_b, use_container_width=True, config={"displayModeBar":False})

                # Insight textual
                pico = df_b.loc[df_b["atrasos"].idxmax()]
                pct_8_9 = df_b[df_b["bloque"].str.startswith("08")]["atrasos"].sum()
                pct_8_9_pct = round(pct_8_9 / df_b["atrasos"].sum() * 100, 1)
                st.markdown(
                    f'<div class="sigma-alert info">'
                    f'El pico de atrasos ocurre entre las <b>{pico["bloque"]}</b> '
                    f'con <b>{int(pico["atrasos"])} registros</b> ({pico["pct_del_total"]:.1f}% del total). '
                    f'El bloque 08:00–09:00 concentra el <b>{pct_8_9_pct}%</b> de todos los atrasos.'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("Sin datos de bloques horarios. Vuelve a procesar el CSV de atrasos.")

        with h2:
            # Gráfico por día de la semana
            if df_by_dia is not None and not df_by_dia.empty:
                df_d = df_by_dia.copy()
                colores_dia = ["#2563eb","#7c3aed","#16a34a","#dc2626","#d97706"]
                fig_dia = go.Figure(go.Bar(
                    x=df_d["dia_label"], y=df_d["atrasos"],
                    marker_color=colores_dia[:len(df_d)],
                    text=df_d["atrasos"], textposition="outside",
                    textfont={"size":11,"color":"#e2e8f0"},
                    customdata=df_d["pct_del_total"],
                    hovertemplate="<b>%{x}</b><br>Atrasos: %{y}<br>% del total: %{customdata:.1f}%<extra></extra>",
                ))
                fig_dia.update_layout(
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color":"#e2e8f0"}, height=340,
                    margin={"l":10,"r":10,"t":40,"b":10},
                    title={"text":"Atrasos por día de la semana","font":{"size":12,"color":"#63b3ed"},"x":0},
                    xaxis={"gridcolor":"rgba(0,0,0,0)"},
                    yaxis={"gridcolor":"#1a2035"},
                    showlegend=False,
                )
                st.plotly_chart(fig_dia, use_container_width=True, config={"displayModeBar":False})

                # Insight día
                dia_max = df_d.loc[df_d["atrasos"].idxmax()]
                dia_min = df_d.loc[df_d["atrasos"].idxmin()]
                st.markdown(
                    f'<div class="sigma-alert info">'
                    f'<b>{dia_max["dia_label"]}</b> es el día con más atrasos '
                    f'({int(dia_max["atrasos"])}, {dia_max["pct_del_total"]:.1f}% del total). '
                    f'<b>{dia_min["dia_label"]}</b> es el día con menos '
                    f'({int(dia_min["atrasos"])}, {dia_min["pct_del_total"]:.1f}%).'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("Sin datos por día de semana.")

        # Fila 2: Período + tabla resumen bloques
        hp1, hp2 = st.columns(2)

        with hp1:
            if df_by_periodo is not None and not df_by_periodo.empty:
                st.markdown('<div class="section-title" style="margin-top:8px">Atrasos por período (bloque de clase)</div>', unsafe_allow_html=True)
                df_p = df_by_periodo.copy()
                df_p["periodo"] = "Período " + df_p["periodo"].astype(str)
                fig_per = go.Figure(go.Bar(
                    x=df_p["periodo"], y=df_p["atrasos"],
                    marker={"color": df_p["atrasos"],
                            "colorscale": [[0,"#1a2035"],[0.5,"#2563eb"],[1,"#dc2626"]]},
                    text=df_p["atrasos"], textposition="outside",
                    textfont={"size":11,"color":"#e2e8f0"},
                    hovertemplate="<b>%{x}</b>: %{y} atrasos<extra></extra>",
                ))
                fig_per.update_layout(
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color":"#e2e8f0"}, height=300,
                    margin={"l":10,"r":10,"t":10,"b":10},
                    xaxis={"gridcolor":"rgba(0,0,0,0)"},
                    yaxis={"gridcolor":"#1a2035"},
                    showlegend=False,
                )
                st.plotly_chart(fig_per, use_container_width=True, config={"displayModeBar":False})

        with hp2:
            if df_by_bloque is not None and not df_by_bloque.empty:
                st.markdown('<div class="section-title" style="margin-top:8px">Detalle por bloque</div>', unsafe_allow_html=True)
                df_b_show = df_by_bloque.rename(columns={
                    "bloque":         "Bloque",
                    "atrasos":        "Atrasos",
                    "alumnos":        "Alumnos únicos",
                    "justificados":   "Justificados",
                    "pct_justificados":"% Justif.",
                    "pct_del_total":  "% del total",
                }).copy()
                if "% Justif." in df_b_show.columns:
                    df_b_show["% Justif."] = df_b_show["% Justif."].apply(lambda v: f"{v:.1f}%")
                if "% del total" in df_b_show.columns:
                    df_b_show["% del total"] = df_b_show["% del total"].apply(lambda v: f"{v:.1f}%")
                show_pretty_table(df_b_show, max_rows=30, height=320)

    # ── POR COMUNA ────────────────────────────────────────────────────
    with tab_comunas:
        st.markdown('<div class="section-title">Procedencia de los alumnos con atrasos</div>', unsafe_allow_html=True)

        if df_by_comuna is None or df_by_comuna.empty:
            st.markdown(
                '<div class="sigma-alert info">'
                'Para ver el análisis por comuna, vuelve a cargar el CSV de atrasos. '
                'SIGMA cruza automáticamente con la matrícula para obtener la procedencia.'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            total_com = df_by_comuna["total_atrasos"].sum() or 1

            # KPIs rápidos
            k1, k2, k3, k4 = st.columns(4)
            com_max       = df_by_comuna.iloc[0]
            com_prom_max  = df_by_comuna.loc[df_by_comuna["prom_por_alumno"].idxmax()]
            n_comunas     = len(df_by_comuna)
            _kpi(k1, str(n_comunas),                   "Comunas de origen",            "#2563eb")
            _kpi(k2, f"{com_max['pct_del_total']:.1f}%", f"{com_max['comuna']} (mayor volumen)", "#dc2626")
            _kpi(k3, f"{com_prom_max['prom_por_alumno']}", f"{com_prom_max['comuna']} (mayor promedio)", "#d97706")
            _kpi(k4, f"{round(df_by_comuna['prom_por_alumno'].mean(),1)}", "Promedio general", "#6b7280")
            st.markdown("<br>", unsafe_allow_html=True)

            cl, cr = st.columns([2, 3])

            with cl:
                st.markdown('<div class="section-title">Detalle por comuna</div>', unsafe_allow_html=True)
                df_com_show = df_by_comuna.rename(columns={
                    "comuna":         "Comuna",
                    "alumnos":        "Alumnos",
                    "total_atrasos":  "Atrasos",
                    "prom_por_alumno":"Prom/Alumno",
                    "pct_del_total":  "% del total",
                    "criticos":       "Críticos",
                    "altos":          "Altos",
                }).copy()
                if "% del total" in df_com_show.columns:
                    df_com_show["% del total"] = df_com_show["% del total"].apply(lambda v: f"{v:.1f}%")
                show_cols_com = [c for c in ["Comuna","Alumnos","Atrasos","Prom/Alumno","% del total","Altos"] if c in df_com_show.columns]
                show_pretty_table(df_com_show[show_cols_com], max_rows=30, height=500)

            with cr:
                # Gráfico horizontal coloreado por promedio (mayor promedio = más rojo)
                df_c = df_by_comuna.copy().sort_values("total_atrasos", ascending=True)
                prom_max_v = df_c["prom_por_alumno"].max() or 1
                colores_com = [
                    "#dc2626" if v/prom_max_v >= 0.8 else
                    ("#d97706" if v/prom_max_v >= 0.6 else
                    ("#7c3aed" if v/prom_max_v >= 0.4 else "#2563eb"))
                    for v in df_c["prom_por_alumno"]
                ]
                fig_com = go.Figure()
                # Barra de total
                fig_com.add_trace(go.Bar(
                    name="Total atrasos",
                    y=df_c["comuna"], x=df_c["total_atrasos"],
                    orientation="h",
                    marker_color=colores_com,
                    text=df_c.apply(lambda r: f"{int(r['total_atrasos'])}  (prom: {r['prom_por_alumno']})", axis=1),
                    textposition="outside",
                    textfont={"size": 9, "color": "#e2e8f0"},
                    hovertemplate="<b>%{y}</b><br>Atrasos: %{x}<extra></extra>",
                ))
                fig_com.update_layout(
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color": "#e2e8f0"},
                    height=max(380, len(df_c) * 28),
                    margin={"l": 10, "r": 120, "t": 40, "b": 10},
                    title={"text": "Atrasos por comuna de procedencia (color = promedio por alumno)",
                           "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                    xaxis={"gridcolor": "#1a2035"},
                    yaxis={"gridcolor": "rgba(0,0,0,0)", "tickfont": {"size": 10}},
                    showlegend=False,
                )
                st.plotly_chart(fig_com, use_container_width=True, config={"displayModeBar": False})

            # Insight automático
            st.markdown("<br>", unsafe_allow_html=True)
            com_lejos = df_by_comuna[~df_by_comuna["comuna"].isin(["RENCA"])].nlargest(3, "prom_por_alumno")
            if not com_lejos.empty:
                detalle = ", ".join([
                    f"{r['comuna']} ({r['prom_por_alumno']} prom.)"
                    for _, r in com_lejos.iterrows()
                ])
                st.markdown(
                    f'<div class="sigma-alert info">'
                    f'Las comunas con mayor promedio de atrasos por alumno son <b>{detalle}</b>. '
                    f'Un promedio alto en comunas lejanas sugiere que el tiempo de traslado '
                    f'es un factor relevante en la puntualidad.'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── BUSCADOR DE ALUMNO ────────────────────────────────────────────
    with tab_alumno:
        st.markdown('<div class="section-title">Historial de atrasos por alumno</div>', unsafe_allow_html=True)
        busqueda = st.text_input("🔍 Buscar por nombre o RUT", placeholder="Ej: RODRIGUEZ o 12345678-9", key="atr_busqueda")

        if busqueda and len(busqueda) >= 3:
            busq = busqueda.strip().upper()
            mask = pd.Series([False] * len(df_alumnos), index=df_alumnos.index)
            if "nombre" in df_alumnos.columns:
                mask |= df_alumnos["nombre"].astype(str).str.upper().str.contains(busq, na=False)
            if "rut_norm" in df_alumnos.columns:
                mask |= df_alumnos["rut_norm"].astype(str).str.contains(busq, na=False)
            resultados = df_alumnos[mask]

            if resultados.empty:
                st.markdown('<div class="sigma-alert">No se encontraron alumnos con ese criterio.</div>', unsafe_allow_html=True)
            else:
                for _, alumno in resultados.iterrows():
                    nombre  = str(alumno.get("nombre","—"))
                    curso   = str(alumno.get("curso","—"))
                    rut     = str(alumno.get("rut_norm","—"))
                    n_atr   = int(alumno.get("n_atrasos", 0))
                    n_just  = int(alumno.get("n_justificados", 0))
                    dias_c  = int(alumno.get("dias_con_atraso", 0))
                    pct_j   = float(alumno.get("pct_justificados", 0))
                    alerta  = str(alumno.get("alerta", "—"))
                    color_a = {"CRITICO":"#dc2626","ALTO":"#d97706","MEDIO":"#7c3aed","BAJO":"#16a34a"}.get(alerta,"#6b7280")

                    with st.expander(f"📋 {nombre} — {curso}  |  {n_atr} atrasos  |  Alerta: {alerta}", expanded=True):
                        ic1, ic2, ic3, ic4 = st.columns(4)
                        _kpi(ic1, str(n_atr),     "Atrasos totales",  "#2563eb")
                        _kpi(ic2, str(n_just),     "Justificados",     "#16a34a")
                        _kpi(ic3, f"{pct_j:.1f}%", "% Justificado",    "#d97706")
                        _kpi(ic4, str(dias_c),     "Días con atraso",  "#7c3aed")

                        # Historial de eventos del alumno
                        if "rut_norm" in df_eventos.columns:
                            rut_key = str(alumno.get("rut_norm",""))
                            df_hist = df_eventos[df_eventos["rut_norm"].astype(str) == rut_key].copy()
                            if not df_hist.empty:
                                st.markdown(f"**{len(df_hist)} eventos registrados**")
                                cols_h = [c for c in ["fecha","periodo","tipo_atraso","justificado","hora"] if c in df_hist.columns]
                                df_hist_show = df_hist[cols_h].sort_values("fecha", ascending=False).reset_index(drop=True)
                                df_hist_show = df_hist_show.rename(columns={
                                    "fecha":"Fecha","periodo":"Período","tipo_atraso":"Tipo",
                                    "justificado":"Justificado","hora":"Hora",
                                })
                                if "Justificado" in df_hist_show.columns:
                                    df_hist_show["Justificado"] = df_hist_show["Justificado"].map(
                                        {True:"✓ Sí", False:"No", 1:"✓ Sí", 0:"No"}
                                    ).fillna("—")
                                show_pretty_table(df_hist_show, max_rows=50, height=300)
        elif busqueda and len(busqueda) < 3:
            st.caption("Ingresa al menos 3 caracteres para buscar.")
        else:
            st.markdown('<div class="sigma-alert info">Ingresa un nombre o RUT para ver el historial completo de atrasos del alumno.</div>', unsafe_allow_html=True)
            # Tabla general de alumnos con más atrasos
            st.markdown('<div class="section-title" style="margin-top:16px">Top alumnos por recurrencia</div>', unsafe_allow_html=True)
            cols_al = [c for c in ["nombre","curso","n_atrasos","n_justificados","dias_con_atraso","pct_justificados","alerta"] if c in df_alumnos.columns]
            df_al_show = df_alumnos[cols_al].sort_values("n_atrasos", ascending=False).head(30).reset_index(drop=True).rename(columns={
                "nombre":"Nombre","curso":"Curso","n_atrasos":"Atrasos","n_justificados":"Justificados",
                "dias_con_atraso":"Días c/Atraso","pct_justificados":"% Justif.","alerta":"Alerta",
            })
            if "Alerta" in df_al_show.columns:
                df_al_show["Alerta"] = df_al_show["Alerta"].map(
                    {"CRITICO":"🔴 Crítico","ALTO":"🟡 Alto","MEDIO":"🟠 Medio","BAJO":"🟢 Bajo"}
                ).fillna("—")
            if "% Justif." in df_al_show.columns:
                df_al_show["% Justif."] = df_al_show["% Justif."].apply(lambda v: f"{v:.1f}%")
            show_pretty_table(df_al_show, max_rows=30, height=460)

    st.markdown('<div class="section-title">Reportes y DATA entregable</div>', unsafe_allow_html=True)
    resumen = pd.DataFrame(
        [
            {
                "corte": corte_lbl,
                "eventos": total_atrasos,
                "alumnos_unicos": alumnos_unicos,
                "cursos_afectados": cursos_afect,
                "pct_justificados": pct_just,
                "reincidentes_3_o_mas": reincidentes,
                "criticos_8_o_mas": criticos,
            }
        ]
    )
    show_pretty_table(resumen, max_rows=5, height=110)

    d1, d2, d3, d4, d5 = st.columns(5)
    safe_stamp = str(corte_lbl).replace("-", "") if corte_lbl and corte_lbl != "-" else "sin_corte"
    d1.download_button(
        "Resumen",
        data=_to_csv_bytes(resumen),
        file_name=f"atrasos_resumen__{safe_stamp}.csv",
        mime=MIME_CSV,
        use_container_width=True,
        key="dl_atrasos_resumen",
    )
    d2.download_button(
        "Eventos",
        data=_to_csv_bytes(df_eventos),
        file_name=f"atrasos_eventos__{safe_stamp}.csv",
        mime=MIME_CSV,
        use_container_width=True,
        key="dl_atrasos_eventos",
    )
    d3.download_button(
        "Alumnos",
        data=_to_csv_bytes(df_alumnos),
        file_name=f"atrasos_alumnos__{safe_stamp}.csv",
        mime=MIME_CSV,
        use_container_width=True,
        key="dl_atrasos_alumnos",
    )
    d4.download_button(
        "Cursos",
        data=_to_csv_bytes(df_cursos),
        file_name=f"atrasos_cursos__{safe_stamp}.csv",
        mime=MIME_CSV,
        use_container_width=True,
        key="dl_atrasos_cursos",
    )
    d5.download_button(
        "Serie diaria",
        data=_to_csv_bytes(df_serie),
        file_name=f"atrasos_serie__{safe_stamp}.csv",
        mime=MIME_CSV,
        use_container_width=True,
        key="dl_atrasos_serie",
    )

    pdf_kpis = {
        "corte": corte_lbl,
        "eventos": total_atrasos,
        "alumnos_unicos": alumnos_unicos,
        "cursos_afectados": cursos_afect,
        "pct_justificados": pct_just,
        "reincidentes_3_o_mas": reincidentes,
        "criticos_8_o_mas": criticos,
    }

    top_alumnos_pdf = (
        df_alumnos.sort_values("n_atrasos", ascending=False).head(25)
        if "n_atrasos" in df_alumnos.columns
        else df_alumnos.head(25)
    )
    top_cursos_pdf = (
        df_cursos.sort_values("total_atrasos", ascending=False).head(25)
        if "total_atrasos" in df_cursos.columns
        else df_cursos.head(25)
    )
    serie_pdf = (
        df_serie.sort_values("fecha", ascending=True).tail(31)
        if "fecha" in df_serie.columns
        else df_serie.head(31)
    )

    st.markdown('<div class="section-title">PDF Ejecutivo del módulo</div>', unsafe_allow_html=True)

    if st.button("📄 Generar PDF Ejecutivo Atrasos", use_container_width=True, key="btn_pdf_atrasos"):
        with st.spinner("Generando PDF ejecutivo..."):
            pdf_bytes = generate_pdf_atrasos(
                df_alumnos=df_alumnos,
                df_cursos=df_cursos,
                corte=str(corte_lbl),
                df_eventos=df_eventos,
                df_serie=df_serie,
                df_by_bloque=df_by_bloque,
                df_by_dia=df_by_dia,
                df_by_periodo=df_by_periodo,
            )
        st.session_state["pdf_atrasos"] = pdf_bytes

    if "pdf_atrasos" in st.session_state:
        pdf_bytes = st.session_state["pdf_atrasos"]
        st.download_button(
            "⬇️ Descargar PDF Ejecutivo Atrasos",
            data=pdf_bytes,
            file_name=f"SIGMA_Atrasos_{safe_stamp}.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="dl_atrasos_pdf_ejecutivo",
        )
        with st.expander("👁️ Ver PDF en pantalla", expanded=False):
            render_pdf_preview(pdf_bytes, height=700)