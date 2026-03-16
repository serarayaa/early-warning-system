# ui/asistencia_page.py
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.validation.column_mapper import renombrar_dataframe_a_canonico
from src.validation.schema_registry import SCHEMA_ASISTENCIA
from src.validation.schema_validator import validar_columnas
from ui.schema_feedback import mostrar_validacion_esquema


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


def render_asistencia_page():
    # ══════════════════════════════════════════════
    # MÓDULO — ASISTENCIA
    # ══════════════════════════════════════════════
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
            df_asist_alumnos = pd.read_csv(asist_gold / "asistencia_alumnos.csv")
            df_asist_cursos = pd.read_csv(asist_gold / "asistencia_cursos.csv")
            df_asist_serie = pd.read_csv(asist_gold / "asistencia_serie.csv")
            df_asist_serie["fecha"] = pd.to_datetime(df_asist_serie["fecha"])

            meta_a = pd.read_csv(asist_gold / "asistencia_meta.csv")
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
            preview_df = pd.read_csv(asist_file, nrows=5)
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
                sys.path.insert(0, "src/staging")
                from build_stg_asistencia import run as run_asist

                asist_file.seek(0)
                df_raw = pd.read_csv(asist_file)

                df_norm, resultado_mapeo = renombrar_dataframe_a_canonico(
                    df_raw,
                    SCHEMA_ASISTENCIA,
                )

                renombradas = {
                    k: v for k, v in resultado_mapeo["mapeadas"].items()
                    if k != v
                }

                if renombradas:
                    filas = [{"Columna original": k, "Renombrada como": v} for k, v in renombradas.items()]
                    st.markdown("**Renombrado automático aplicado**")
                    st.dataframe(filas, use_container_width=True, hide_index=True)

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".csv",
                    mode="w",
                    encoding="utf-8-sig",
                    newline="",
                ) as tmp:
                    df_norm.to_csv(tmp.name, index=False)
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
        st.markdown(
            '<div class="section-title" style="margin-top:12px">Indicadores generales</div>',
            unsafe_allow_html=True,
        )

        total_a = len(df_asist_alumnos)
        bajo85 = int(df_asist_alumnos["alerta"].isin(["LEGAL", "CRITICO"]).sum())
        bajo75 = int((df_asist_alumnos["alerta"] == "CRITICO").sum())
        tend_baja = int((df_asist_alumnos["tendencia"] == "BAJA").sum())
        pct_global = round(df_asist_alumnos["pct_asistencia"].mean(), 1)
        pct_hoy = (
            float(df_asist_serie.iloc[-1]["pct_dia"])
            if df_asist_serie is not None and not df_asist_serie.empty
            else 0
        )

        fecha_ult = (
            df_asist_serie.iloc[-1]["fecha"].strftime("%d/%m")
            if df_asist_serie is not None and not df_asist_serie.empty
            else "-"
        )

        ka1, ka2, ka3, ka4, ka5, ka6 = st.columns(6)
        _kpi_a(ka1, f"{pct_global}%", "Asistencia global", "#2563eb")
        _kpi_a(ka2, f"{pct_hoy}%", f"Último día ({fecha_ult})", "#16a34a")
        _kpi_a(ka3, total_a, "Alumnos", "#6b7280")
        _kpi_a(ka4, bajo85, "Bajo 85% (legal)", "#d97706")
        _kpi_a(ka5, bajo75, "Bajo 75% (crítico)", "#dc2626")
        _kpi_a(ka6, tend_baja, "Tendencia a la baja", "#7c3aed")
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown('<div class="section-title">Visualizaciones</div>', unsafe_allow_html=True)
        ga1, ga2 = st.columns(2)

        with ga1:
            fig_serie = go.Figure()
            fig_serie.add_trace(
                go.Scatter(
                    x=df_asist_serie["fecha"],
                    y=df_asist_serie["pct_dia"],
                    mode="lines+markers+text",
                    line=dict(color="#2563eb", width=2.5),
                    marker=dict(size=8, color="#2563eb"),
                    text=[f"{v}%" for v in df_asist_serie["pct_dia"]],
                    textposition="top center",
                    textfont=dict(size=9, color="#e2e8f0"),
                    name="% Asistencia",
                    hovertemplate="<b>%{x|%d/%m}</b>: %{y:.1f}%<extra></extra>",
                )
            )
            fig_serie.add_hline(y=85, line_dash="dot", line_color="#d97706")
            fig_serie.add_hline(y=75, line_dash="dot", line_color="#dc2626")
            fig_serie.update_layout(
                paper_bgcolor="#0d1220",
                plot_bgcolor="#0d1220",
                font=dict(color="#e2e8f0"),
                height=280,
                title=dict(
                    text="Asistencia diaria del establecimiento",
                    font=dict(size=12, color="#63b3ed"),
                    x=0,
                ),
                xaxis=dict(gridcolor="#1a2035", tickfont=dict(color="#a0aec0")),
                yaxis=dict(gridcolor="#1a2035", tickfont=dict(color="#a0aec0"), range=[70, 102]),
                margin=dict(l=16, r=16, t=40, b=16),
                showlegend=False,
            )
            st.plotly_chart(fig_serie, use_container_width=True, config={"displayModeBar": False})

        with ga2:
            dfc_ord = df_asist_cursos.sort_values("pct_promedio", ascending=True)
            bar_colors = [
                "#dc2626" if v < 85 else ("#d97706" if v < 90 else ("#16a34a" if v >= 97 else "#2563eb"))
                for v in dfc_ord["pct_promedio"]
            ]

            fig_cur = go.Figure(
                go.Bar(
                    x=dfc_ord["pct_promedio"],
                    y=dfc_ord["curso"],
                    orientation="h",
                    marker_color=bar_colors,
                    text=[f"{v}%" for v in dfc_ord["pct_promedio"]],
                    textposition="outside",
                    textfont=dict(color="#e2e8f0", size=9),
                    hovertemplate="<b>%{y}</b>: %{x:.1f}%<extra></extra>",
                )
            )
            fig_cur.add_vline(x=85, line_dash="dot", line_color="#d97706")
            fig_cur.update_layout(
                paper_bgcolor="#0d1220",
                plot_bgcolor="#0d1220",
                font=dict(color="#e2e8f0"),
                height=560,
                title=dict(
                    text="Asistencia promedio por curso",
                    font=dict(size=12, color="#63b3ed"),
                    x=0,
                ),
                xaxis=dict(gridcolor="#1a2035", tickfont=dict(color="#a0aec0"), range=[60, 105]),
                yaxis=dict(tickfont=dict(color="#e2e8f0", size=10), gridcolor="rgba(0,0,0,0)"),
                margin=dict(l=16, r=60, t=40, b=16),
                showlegend=False,
            )
            st.plotly_chart(fig_cur, use_container_width=True, config={"displayModeBar": False})

        st.markdown(
            '<div class="section-title" style="margin-top:4px">Alertas de asistencia</div>',
            unsafe_allow_html=True,
        )

        alert_tabs = st.tabs([
            f"🔴 Críticos <75% ({bajo75})",
            f"🟡 Bajo 85% ({bajo85 - bajo75})",
            f"📉 Tendencia a la baja ({tend_baja})",
            f"📊 Cursos destacados",
        ])

        col_show = ["nombre", "curso", "dias_presentes", "dias_ausentes", "pct_asistencia", "tendencia"]
        col_lbl = {
            "nombre": "Nombre",
            "curso": "Curso",
            "dias_presentes": "Presentes",
            "dias_ausentes": "Ausentes",
            "pct_asistencia": "% Asistencia",
            "tendencia": "Tendencia",
        }

        with alert_tabs[0]:
            criticos = df_asist_alumnos[df_asist_alumnos["alerta"] == "CRITICO"].sort_values("pct_asistencia")
            if criticos.empty:
                st.success("Sin alumnos bajo 75%")
            else:
                st.markdown(f"**{len(criticos)} alumnos** con asistencia crítica (bajo 75%).")
                st.dataframe(
                    criticos[[c for c in col_show if c in criticos.columns]].rename(columns=col_lbl),
                    use_container_width=True,
                    hide_index=True,
                )

        with alert_tabs[1]:
            legal = df_asist_alumnos[df_asist_alumnos["alerta"] == "LEGAL"].sort_values("pct_asistencia")
            if legal.empty:
                st.success("Sin alumnos entre 75% y 85%")
            else:
                st.markdown(f"**{len(legal)} alumnos** en zona de advertencia legal.")
                st.dataframe(
                    legal[[c for c in col_show if c in legal.columns]].rename(columns=col_lbl),
                    use_container_width=True,
                    hide_index=True,
                )

        with alert_tabs[2]:
            baja_df = df_asist_alumnos[df_asist_alumnos["tendencia"] == "BAJA"].sort_values("delta")
            if baja_df.empty:
                st.success("Sin alumnos con tendencia a la baja")
            else:
                cols_tend = ["nombre", "curso", "pct_asistencia", "pct_ultimos_3", "delta"]
                lbl_tend = {
                    "nombre": "Nombre",
                    "curso": "Curso",
                    "pct_asistencia": "% Acumulado",
                    "pct_ultimos_3": "% Últimos 3 días",
                    "delta": "Δ Cambio",
                }
                st.dataframe(
                    baja_df[[c for c in cols_tend if c in baja_df.columns]].rename(columns=lbl_tend),
                    use_container_width=True,
                    hide_index=True,
                )

        with alert_tabs[3]:
            st.markdown("**Cursos con mejor asistencia** 🟢")
            altos = df_asist_cursos[df_asist_cursos["alerta_curso"] == "ALTO"].sort_values("pct_promedio", ascending=False)
            if altos.empty:
                st.info("Sin cursos sobre 97%")
            else:
                st.dataframe(
                    altos[["curso", "n_alumnos", "pct_promedio", "bajo_85", "bajo_75"]].rename(
                        columns={
                            "curso": "Curso",
                            "n_alumnos": "Alumnos",
                            "pct_promedio": "% Promedio",
                            "bajo_85": "Bajo 85%",
                            "bajo_75": "Bajo 75%",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            st.markdown("**Cursos con asistencia baja** 🔴")
            bajos = df_asist_cursos[df_asist_cursos["alerta_curso"] == "BAJO"].sort_values("pct_promedio")
            if bajos.empty:
                st.info("Sin cursos bajo 90%")
            else:
                st.dataframe(
                    bajos[["curso", "n_alumnos", "pct_promedio", "bajo_85", "bajo_75", "tendencia_baja"]].rename(
                        columns={
                            "curso": "Curso",
                            "n_alumnos": "Alumnos",
                            "pct_promedio": "% Promedio",
                            "bajo_85": "Bajo 85%",
                            "bajo_75": "Bajo 75%",
                            "tendencia_baja": "Tend. Baja",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        with st.expander("📋 Ver nómina completa de asistencia", expanded=False):
            orden_alerta = {"CRITICO": 0, "LEGAL": 1, "OK": 2}
            df_nom = df_asist_alumnos.copy()
            df_nom["_ord"] = df_nom["alerta"].map(orden_alerta).fillna(2)
            df_nom = df_nom.sort_values(["_ord", "pct_asistencia"])

            st.dataframe(
                df_nom[[c for c in col_show if c in df_nom.columns]].rename(columns=col_lbl),
                use_container_width=True,
                hide_index=True,
            )

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