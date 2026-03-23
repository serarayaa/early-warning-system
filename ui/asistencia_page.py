# ui/asistencia_page.py
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.validation.schema_registry import SCHEMA_ASISTENCIA
from src.validation.schema_validator import validar_columnas
from src.staging.build_stg_asistencia import run as run_asist
from ui.executive_pdf import generate_pdf_asistencia, render_pdf_preview, show_pretty_table
from ui.schema_feedback import mostrar_validacion_esquema

MIME_CSV = "text/csv"


def _ultimo_habil(d: date | None = None) -> date:
    d = d or date.today()
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _kpi_a(col, val, label, color="#2563eb"):
    col.markdown(
        f"""
        <div style="background:#0d1220;border-radius:8px;padding:14px 8px;text-align:center;
                    border:1px solid rgba(99,179,237,0.10); border-bottom:3px solid {color}">
            <div style="font-size:1.7rem;font-weight:700;color:{color}">{val}</div>
            <div style="font-size:0.68rem;color:#94a3b8;margin-top:2px;text-transform:uppercase">{label}</div>
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
    raise ValueError(f"No se pudo leer CSV de asistencia con encodings esperados: {last_err}")


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def render_asistencia_page():
    st.markdown(
        """
        <div class="sigma-header">
            <div>
                <div class="sigma-logo" style="font-size:1.5rem">SIGMA</div>
                <div class="sigma-tagline">Asistencia Diaria</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">Asistencia Diaria</div>', unsafe_allow_html=True)

    # ── Carga del CSV ──────────────────────────────────────────────────
    col_up, col_info = st.columns([2, 1])

    with col_up:
        asist_file = st.file_uploader(
            "Cargar CSV de Syscol (asistenciadiaria_*.csv)",
            type=["csv"],
            key="asist_uploader",
        )

    with col_info:
        corte_asist = _ultimo_habil()
        st.markdown(
            f"""
            <div class="sigma-alert info" style="margin-top:28px">
                📅 Corte automático: <b>{corte_asist.strftime('%d/%m/%Y')}</b><br>
                <small>Siempre el último día hábil anterior</small>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Variables base ─────────────────────────────────────────────────
    df_asist_alumnos = None
    df_asist_cursos = None
    df_asist_serie = None
    n_dias_asist = 0

    asist_gold = Path("data/gold/asistencia")
    resultado_validacion = None

    # ── Cargar desde gold si existe y no se subió archivo ─────────────
    if (asist_gold / "asistencia_alumnos.csv").exists() and asist_file is None:
        try:
            df_asist_alumnos = pd.read_csv(asist_gold / "asistencia_alumnos.csv", encoding="utf-8")
            df_asist_cursos = pd.read_csv(asist_gold / "asistencia_cursos.csv",  encoding="utf-8")
            df_asist_serie = pd.read_csv(asist_gold / "asistencia_serie.csv",   encoding="utf-8")
            df_asist_serie["fecha"] = pd.to_datetime(df_asist_serie["fecha"])

            meta_a = pd.read_csv(asist_gold / "asistencia_meta.csv",    encoding="utf-8")
            n_dias_asist = int(meta_a["n_dias"].iloc[0])
            corte_lbl = meta_a["corte"].iloc[0]

            st.markdown(
                f'<div class="sigma-alert info">Datos cargados desde gold — corte: <b>{corte_lbl}</b></div>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.markdown(
                f'<div class="sigma-alert danger">Error cargando datos guardados: {e}</div>',
                unsafe_allow_html=True,
            )

    # ── Validación visual del archivo subido ───────────────────────────
    if asist_file is not None:
        try:
            preview_df = _read_uploaded_csv(asist_file, nrows=5)
            resultado_validacion = validar_columnas(
                preview_df.columns.tolist(),
                SCHEMA_ASISTENCIA,
            )
            mostrar_validacion_esquema(resultado_validacion)
            asist_file.seek(0)
        except Exception as e:
            st.markdown(
                f'<div class="sigma-alert danger">No se pudo analizar la estructura del archivo: {e}</div>',
                unsafe_allow_html=True,
            )
            asist_file.seek(0)

    # ── Procesar archivo subido manualmente ────────────────────────────
    if asist_file is not None:
        try:
            if resultado_validacion is not None and not resultado_validacion["es_valido"]:
                st.error("El archivo no cumple con la estructura mínima esperada para Asistencia.")
            else:
                df_raw = _read_uploaded_csv(asist_file)

                # Se procesa con nombres originales de Syscol
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
                    r = run_asist(tmp_path, asist_gold, corte=corte_asist)
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

                df_asist_alumnos = r["alumnos"]
                df_asist_cursos = r["cursos"]
                df_asist_serie = r["serie"]
                n_dias_asist = r["n_dias"]

                st.markdown(
                    f'<div class="sigma-alert success">✅ Asistencia procesada — {n_dias_asist} días hábiles hasta {corte_asist.strftime("%d/%m/%Y")}</div>',
                    unsafe_allow_html=True,
                )

        except Exception as e:
            st.markdown(
                f'<div class="sigma-alert danger">Error procesando CSV: {e}</div>',
                unsafe_allow_html=True,
            )

    # ── Render principal ──────────────────────────────────────────────
    if df_asist_alumnos is not None and not df_asist_alumnos.empty:

        total_a   = len(df_asist_alumnos)
        bajo85    = int(df_asist_alumnos["alerta"].isin(["LEGAL","CRITICO"]).sum()) if "alerta" in df_asist_alumnos.columns else 0
        bajo75    = int((df_asist_alumnos["alerta"]=="CRITICO").sum()) if "alerta" in df_asist_alumnos.columns else 0
        tend_baja = int((df_asist_alumnos["tendencia"]=="BAJA").sum()) if "tendencia" in df_asist_alumnos.columns else 0
        pct_global = round(df_asist_alumnos["pct_asistencia"].mean(), 1) if "pct_asistencia" in df_asist_alumnos.columns else 0

        pct_hoy = (
            float(df_asist_serie.iloc[-1]["pct_dia"])
            if df_asist_serie is not None and not df_asist_serie.empty and "pct_dia" in df_asist_serie.columns
            else 0
        )
        fecha_ult = (
            df_asist_serie.iloc[-1]["fecha"].strftime("%d/%m")
            if df_asist_serie is not None and not df_asist_serie.empty and "fecha" in df_asist_serie.columns
            else "-"
        )
        prom_historico = (
            round(df_asist_serie["pct_dia"].mean(), 1)
            if df_asist_serie is not None and not df_asist_serie.empty and "pct_dia" in df_asist_serie.columns
            else 0
        )
        delta_hoy = round(pct_hoy - prom_historico, 1)

        # ── KPIs ─────────────────────────────────────────────────────
        st.markdown('<div class="section-title" style="margin-top:12px">Indicadores generales</div>', unsafe_allow_html=True)
        ka1, ka2, ka3, ka4, ka5, ka6 = st.columns(6)
        color_global = "#16a34a" if pct_global >= 90 else ("#d97706" if pct_global >= 85 else "#dc2626")
        color_hoy    = "#16a34a" if delta_hoy >= 0 else "#dc2626"
        _kpi_a(ka1, f"{pct_global}%",  "Asistencia global",      color_global)
        _kpi_a(ka2, f"{pct_hoy}%",     f"Último día ({fecha_ult})", color_hoy)
        _kpi_a(ka3, f"{'▲' if delta_hoy>=0 else '▼'}{abs(delta_hoy)}%", "vs promedio histórico", color_hoy)
        _kpi_a(ka4, bajo85, "Bajo 85% (legal)",      "#d97706")
        _kpi_a(ka5, bajo75, "Bajo 75% (crítico)",    "#dc2626")
        _kpi_a(ka6, tend_baja, "Tendencia a la baja","#7c3aed")
        st.markdown("<br>", unsafe_allow_html=True)

        # ── Sub-tabs ──────────────────────────────────────────────────
        tab_crit, tab_legal, tab_tend, tab_cursos, tab_viz, tab_rep = st.tabs([
            f"🔴 Críticos ({bajo75})",
            f"🟡 Legal ({bajo85 - bajo75})",
            f"📉 Tendencia ({tend_baja})",
            "📊 Por curso",
            "📈 Visualizaciones",
            "📄 Reportes",
        ])

        # ── SUB-TAB CRÍTICOS ─────────────────────────────────────────
        with tab_crit:
            st.markdown('<div class="section-title">Alumnos con asistencia crítica — bajo 75%</div>', unsafe_allow_html=True)
            if "alerta" in df_asist_alumnos.columns:
                df_crit = df_asist_alumnos[df_asist_alumnos["alerta"]=="CRITICO"].copy()
                if df_crit.empty:
                    st.markdown('<div class="sigma-alert success">✅ Sin alumnos en estado crítico.</div>', unsafe_allow_html=True)
                else:
                    st.markdown(
                        f'<div class="sigma-alert danger"><b>{len(df_crit)} alumnos</b> bajo 75% — '                        f'requieren contacto inmediato.</div>',
                        unsafe_allow_html=True,
                    )
                    cols_c = [c for c in ["nombre","curso","pct_asistencia","dias_presentes","dias_ausentes","tendencia"] if c in df_crit.columns]
                    df_show = df_crit.sort_values("pct_asistencia")[cols_c].reset_index(drop=True).rename(columns={
                        "nombre":"Nombre","curso":"Curso","pct_asistencia":"% Asistencia",
                        "dias_presentes":"Presentes","dias_ausentes":"Ausentes","tendencia":"Tendencia",
                    })
                    # Semáforo en columna Tendencia
                    if "Tendencia" in df_show.columns:
                        df_show["Tendencia"] = df_show["Tendencia"].map(
                            {"BAJA":"🔴 Baja","ESTABLE":"🟡 Estable","ALTA":"🟢 Alta"}
                        ).fillna("—")
                    if "% Asistencia" in df_show.columns:
                        df_show["% Asistencia"] = df_show["% Asistencia"].apply(lambda v: f"{v:.1f}%")
                    show_pretty_table(df_show, max_rows=100, height=450)

        # ── SUB-TAB LEGAL ────────────────────────────────────────────
        with tab_legal:
            st.markdown('<div class="section-title">Alumnos en zona legal — 75% a 85%</div>', unsafe_allow_html=True)
            if "alerta" in df_asist_alumnos.columns:
                df_leg = df_asist_alumnos[df_asist_alumnos["alerta"]=="LEGAL"].copy()
                if df_leg.empty:
                    st.markdown('<div class="sigma-alert success">✅ Sin alumnos en zona legal.</div>', unsafe_allow_html=True)
                else:
                    st.markdown(
                        f'<div class="sigma-alert"><b>{len(df_leg)} alumnos</b> entre 75% y 85% — '                        f'seguimiento semanal recomendado.</div>',
                        unsafe_allow_html=True,
                    )
                    cols_l = [c for c in ["nombre","curso","pct_asistencia","dias_presentes","dias_ausentes","tendencia"] if c in df_leg.columns]
                    df_show_l = df_leg.sort_values("pct_asistencia")[cols_l].reset_index(drop=True).rename(columns={
                        "nombre":"Nombre","curso":"Curso","pct_asistencia":"% Asistencia",
                        "dias_presentes":"Presentes","dias_ausentes":"Ausentes","tendencia":"Tendencia",
                    })
                    if "Tendencia" in df_show_l.columns:
                        df_show_l["Tendencia"] = df_show_l["Tendencia"].map(
                            {"BAJA":"🔴 Baja","ESTABLE":"🟡 Estable","ALTA":"🟢 Alta"}
                        ).fillna("—")
                    if "% Asistencia" in df_show_l.columns:
                        df_show_l["% Asistencia"] = df_show_l["% Asistencia"].apply(lambda v: f"{v:.1f}%")
                    show_pretty_table(df_show_l, max_rows=100, height=450)

        # ── SUB-TAB TENDENCIA ────────────────────────────────────────
        with tab_tend:
            st.markdown('<div class="section-title">Alumnos con tendencia decreciente</div>', unsafe_allow_html=True)
            if "tendencia" in df_asist_alumnos.columns:
                df_tend = df_asist_alumnos[df_asist_alumnos["tendencia"]=="BAJA"].copy()
                if df_tend.empty:
                    st.markdown('<div class="sigma-alert success">✅ Sin alumnos con tendencia a la baja.</div>', unsafe_allow_html=True)
                else:
                    st.markdown(
                        f'<div class="sigma-alert"><b>{len(df_tend)} alumnos</b> con asistencia cayendo — '                        f'riesgo de cruzar umbral próximamente.</div>',
                        unsafe_allow_html=True,
                    )
                    cols_t = [c for c in ["nombre","curso","pct_asistencia","pct_ultimos_3","delta","alerta"] if c in df_tend.columns]
                    df_show_t = df_tend.sort_values("pct_asistencia")[cols_t].reset_index(drop=True).rename(columns={
                        "nombre":"Nombre","curso":"Curso","pct_asistencia":"% Acumulado",
                        "pct_ultimos_3":"% Últimos 3d","delta":"Delta","alerta":"Alerta",
                    })
                    if "Alerta" in df_show_t.columns:
                        df_show_t["Alerta"] = df_show_t["Alerta"].map(
                            {"CRITICO":"🔴 Crítico","LEGAL":"🟡 Legal","NORMAL":"🟢 Normal"}
                        ).fillna("—")
                    for col in ["% Acumulado","% Últimos 3d"]:
                        if col in df_show_t.columns:
                            df_show_t[col] = df_show_t[col].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
                    show_pretty_table(df_show_t, max_rows=100, height=450)

        # ── SUB-TAB CURSOS ───────────────────────────────────────────
        with tab_cursos:
            st.markdown('<div class="section-title">Asistencia por curso — semáforo</div>', unsafe_allow_html=True)
            if df_asist_cursos is not None and not df_asist_cursos.empty and "pct_promedio" in df_asist_cursos.columns:
                df_c = df_asist_cursos.copy().sort_values("pct_promedio")
                def _semaforo(v):
                    if v < 75: return "🔴 Crítico"
                    if v < 85: return "🟡 Legal"
                    if v < 92: return "🟠 Normal"
                    return "🟢 Excelente"
                df_c["Estado"] = df_c["pct_promedio"].apply(_semaforo)
                cols_cur = [c for c in ["curso","n_alumnos","pct_promedio","Estado"] if c in df_c.columns]
                df_c_show = df_c[cols_cur].rename(columns={"curso":"Curso","n_alumnos":"Alumnos","pct_promedio":"% Asistencia"})
                if "% Asistencia" in df_c_show.columns:
                    df_c_show["% Asistencia"] = df_c_show["% Asistencia"].apply(lambda v: f"{v:.1f}%")
                c_left, c_right = st.columns([2,3])
                with c_left:
                    show_pretty_table(df_c_show, max_rows=50, height=500)
                with c_right:
                    dfc_ord = df_asist_cursos.sort_values("pct_promedio", ascending=True)
                    bar_colors = [
                        "#dc2626" if v < 75 else ("#d97706" if v < 85 else ("#f6ad55" if v < 92 else "#16a34a"))
                        for v in dfc_ord["pct_promedio"]
                    ]
                    fig_cur = go.Figure(go.Bar(
                        x=dfc_ord["pct_promedio"], y=dfc_ord["curso"], orientation="h",
                        marker_color=bar_colors,
                        text=[f"{v:.1f}%" for v in dfc_ord["pct_promedio"]],
                        textposition="outside", textfont={"color":"#e2e8f0","size":9},
                        hovertemplate="<b>%{y}</b>: %{x:.1f}%<extra></extra>",
                    ))
                    fig_cur.add_vline(x=85, line_dash="dot", line_color="#d97706",
                        annotation_text="85%", annotation_position="top right",
                        annotation_font={"color":"#d97706","size":9})
                    fig_cur.add_vline(x=75, line_dash="dot", line_color="#dc2626",
                        annotation_text="75%", annotation_position="bottom right",
                        annotation_font={"color":"#dc2626","size":9})
                    fig_cur.update_layout(
                        paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                        font={"color":"#e2e8f0"}, height=max(320, len(dfc_ord)*28),
                        margin={"l":10,"r":60,"t":40,"b":10},
                        title={"text":"Asistencia por curso","font":{"size":12,"color":"#63b3ed"},"x":0},
                        xaxis={"gridcolor":"#1a2035","range":[60,105]},
                        yaxis={"gridcolor":"rgba(0,0,0,0)","tickfont":{"size":10}},
                        showlegend=False,
                    )
                    st.plotly_chart(fig_cur, use_container_width=True, config={"displayModeBar":False})

        # ── SUB-TAB VISUALIZACIONES ──────────────────────────────────
        with tab_viz:
            st.markdown('<div class="section-title">Serie diaria</div>', unsafe_allow_html=True)
            if df_asist_serie is not None and not df_asist_serie.empty and {"fecha","pct_dia"}.issubset(df_asist_serie.columns):
                # Serie con banda de comparativa
                fig_serie = go.Figure()
                fig_serie.add_hrect(y0=75, y1=85, fillcolor="rgba(217,119,6,0.08)",
                    line_width=0, annotation_text="Zona legal", annotation_position="top left",
                    annotation_font={"color":"#d97706","size":9})
                fig_serie.add_hrect(y0=0, y1=75, fillcolor="rgba(220,38,38,0.08)",
                    line_width=0, annotation_text="Zona crítica", annotation_position="top left",
                    annotation_font={"color":"#dc2626","size":9})
                if prom_historico > 0:
                    fig_serie.add_hline(y=prom_historico, line_dash="dash",
                        line_color="rgba(99,179,237,0.4)",
                        annotation_text=f"Promedio {prom_historico}%",
                        annotation_font={"color":"#63b3ed","size":9})
                fig_serie.add_trace(go.Scatter(
                    x=df_asist_serie["fecha"], y=df_asist_serie["pct_dia"],
                    mode="lines+markers",
                    line={"color":"#2563eb","width":2.5},
                    marker={"size":7, "color":["#dc2626" if v<75 else ("#d97706" if v<85 else "#2563eb")
                            for v in df_asist_serie["pct_dia"]]},
                    name="% Asistencia",
                    hovertemplate="<b>%{x|%d/%m}</b>: %{y:.1f}%<extra></extra>",
                ))
                fig_serie.add_hline(y=85, line_dash="dot", line_color="#d97706", line_width=1)
                fig_serie.add_hline(y=75, line_dash="dot", line_color="#dc2626", line_width=1)
                fig_serie.update_layout(
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color":"#e2e8f0"}, height=320,
                    title={"text":"Asistencia diaria del establecimiento","font":{"size":12,"color":"#63b3ed"},"x":0},
                    xaxis={"gridcolor":"#1a2035"}, yaxis={"gridcolor":"#1a2035","range":[65,102]},
                    margin={"l":16,"r":16,"t":40,"b":16}, showlegend=False,
                )
                st.plotly_chart(fig_serie, use_container_width=True, config={"displayModeBar":False})

            # Distribución de riesgo (reemplaza st.bar_chart con Plotly estilizado)
            if "pct_asistencia" in df_asist_alumnos.columns:
                st.markdown('<div class="section-title">Distribución por nivel de riesgo</div>', unsafe_allow_html=True)
                def _nivel_riesgo(v):
                    if v < 75: return "🔴 Crítico (<75%)"
                    if v < 85: return "🟡 Legal (75-85%)"
                    if v < 92: return "🟠 Observación (85-92%)"
                    return "🟢 Normal (≥92%)"
                riesgo = df_asist_alumnos["pct_asistencia"].apply(_nivel_riesgo).value_counts().reset_index()
                riesgo.columns = ["Nivel","Alumnos"]
                orden = ["🔴 Crítico (<75%)","🟡 Legal (75-85%)","🟠 Observación (85-92%)","🟢 Normal (≥92%)"]
                riesgo["_ord"] = riesgo["Nivel"].map({v:i for i,v in enumerate(orden)})
                riesgo = riesgo.sort_values("_ord").drop(columns=["_ord"])
                colores_risk = {"🔴 Crítico (<75%)":"#dc2626","🟡 Legal (75-85%)":"#d97706",
                                "🟠 Observación (85-92%)":"#f6ad55","🟢 Normal (≥92%)":"#16a34a"}
                fig_risk = go.Figure(go.Bar(
                    x=riesgo["Nivel"], y=riesgo["Alumnos"],
                    marker_color=[colores_risk.get(n,"#6b7280") for n in riesgo["Nivel"]],
                    text=riesgo["Alumnos"], textposition="outside", textfont={"size":12,"color":"#e2e8f0"},
                    hovertemplate="<b>%{x}</b>: %{y} alumnos<extra></extra>",
                ))
                fig_risk.update_layout(
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color":"#e2e8f0"}, height=300,
                    margin={"l":10,"r":10,"t":40,"b":10},
                    title={"text":"Distribución de riesgo de asistencia","font":{"size":12,"color":"#63b3ed"},"x":0},
                    xaxis={"gridcolor":"rgba(0,0,0,0)"},
                    yaxis={"gridcolor":"#1a2035"},
                    showlegend=False,
                )
                st.plotly_chart(fig_risk, use_container_width=True, config={"displayModeBar":False})

            with st.expander("📋 Ver nómina completa de asistencia", expanded=False):
                show_pretty_table(df_asist_alumnos, max_rows=250, height=430)

        # ── SUB-TAB REPORTES ─────────────────────────────────────────
        with tab_rep:
            st.markdown('<div class="section-title">Reportes y DATA entregable</div>', unsafe_allow_html=True)
            resumen = pd.DataFrame([{
                "Corte": corte_asist.strftime("%Y-%m-%d"),
                "Días hábiles": n_dias_asist,
                "Alumnos": total_a,
                "Cursos": int(df_asist_cursos["curso"].nunique()) if "curso" in df_asist_cursos.columns else len(df_asist_cursos),
                "Asistencia global": f"{pct_global}%",
                "Bajo 85%": bajo85,
                "Bajo 75%": bajo75,
                "Tendencia baja": tend_baja,
            }])
            show_pretty_table(resumen, max_rows=5, height=110)

            d1, d2, d3, d4 = st.columns(4)
            d1.download_button("📥 Resumen", data=_to_csv_bytes(resumen),
                file_name=f"asistencia_resumen__{corte_asist.strftime('%Y%m%d')}.csv",
                mime=MIME_CSV, use_container_width=True, key="dl_asistencia_resumen")
            d2.download_button("📥 Alumnos", data=_to_csv_bytes(df_asist_alumnos),
                file_name=f"asistencia_alumnos__{corte_asist.strftime('%Y%m%d')}.csv",
                mime=MIME_CSV, use_container_width=True, key="dl_asistencia_alumnos")
            d3.download_button("📥 Cursos", data=_to_csv_bytes(df_asist_cursos),
                file_name=f"asistencia_cursos__{corte_asist.strftime('%Y%m%d')}.csv",
                mime=MIME_CSV, use_container_width=True, key="dl_asistencia_cursos")
            d4.download_button("📥 Serie diaria", data=_to_csv_bytes(df_asist_serie),
                file_name=f"asistencia_serie__{corte_asist.strftime('%Y%m%d')}.csv",
                mime=MIME_CSV, use_container_width=True, key="dl_asistencia_serie")

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📄 Generar PDF Ejecutivo Asistencia", use_container_width=True, key="btn_pdf_asistencia"):
                with st.spinner("Generando PDF ejecutivo..."):
                    pdf_bytes = generate_pdf_asistencia(
                        df_alumnos=df_asist_alumnos,
                        df_cursos=df_asist_cursos,
                        df_serie=df_asist_serie,
                        corte=corte_asist.strftime("%d/%m/%Y"),
                    )
                st.session_state["pdf_asistencia"] = pdf_bytes
            if "pdf_asistencia" in st.session_state:
                pdf_bytes = st.session_state["pdf_asistencia"]
                st.download_button("⬇️ Descargar PDF Ejecutivo Asistencia",
                    data=pdf_bytes, file_name=f"SIGMA_Asistencia_{corte_asist.strftime('%Y%m%d')}.pdf",
                    mime="application/pdf", use_container_width=True, key="dl_asistencia_pdf_ejecutivo")
                with st.expander("👁️ Ver PDF en pantalla", expanded=False):
                    render_pdf_preview(pdf_bytes, height=700)

    else:
        st.markdown(
            """
            <div class="sigma-alert info">
                <b>Cómo usar el módulo de asistencia:</b><br>
                1. Exporta el reporte <b>Asistencia Diaria</b> desde Syscol como CSV<br>
                2. Cárgalo con el botón de arriba<br>
                3. SIGMA procesará automáticamente hasta el <b>último día hábil anterior a hoy</b>
            </div>
            """,
            unsafe_allow_html=True,
        )