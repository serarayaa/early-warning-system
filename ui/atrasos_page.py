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
from ui.executive_pdf import generate_executive_pdf, render_pdf_preview, show_pretty_table
from ui.schema_feedback import mostrar_validacion_esquema

MIME_CSV = "text/csv"


def _kpi(col, val, label, color="#2563eb"):
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

    df_eventos = None
    df_alumnos = None
    df_cursos = None
    df_serie = None
    corte_lbl = "-"

    if (atrasos_gold / "atrasos_eventos.csv").exists() and atrasos_file is None:
        try:
            df_eventos = pd.read_csv(atrasos_gold / "atrasos_eventos.csv")
            df_alumnos = pd.read_csv(atrasos_gold / "atrasos_alumnos.csv")
            df_cursos = pd.read_csv(atrasos_gold / "atrasos_cursos.csv")
            df_serie = pd.read_csv(atrasos_gold / "atrasos_serie.csv")
            df_serie["fecha"] = pd.to_datetime(df_serie["fecha"])
            meta = pd.read_csv(atrasos_gold / "atrasos_meta.csv")
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
                    r = run_atrasos(tmp_path, atrasos_gold)
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

                df_eventos = r["eventos"]
                df_alumnos = r["alumnos"]
                df_cursos = r["cursos"]
                df_serie = r["serie"]
                corte_lbl = str(r["corte"])

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

    total_atrasos = len(df_eventos)
    alumnos_unicos = int(df_eventos["rut_norm"].nunique()) if "rut_norm" in df_eventos.columns else 0
    cursos_afectados = int(df_eventos["curso"].nunique()) if "curso" in df_eventos.columns else 0
    justificados = int(df_eventos["justificado"].sum()) if "justificado" in df_eventos.columns else 0
    pct_justificados = round((justificados / total_atrasos) * 100, 1) if total_atrasos else 0.0
    reincidentes = int((df_alumnos["n_atrasos"] >= 3).sum()) if "n_atrasos" in df_alumnos.columns else 0
    criticos = int((df_alumnos["alerta"] == "CRITICO").sum()) if "alerta" in df_alumnos.columns else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    _kpi(c1, f"{total_atrasos:,}", "Atrasos", "#2563eb")
    _kpi(c2, f"{alumnos_unicos:,}", "Alumnos", "#16a34a")
    _kpi(c3, f"{cursos_afectados:,}", "Cursos", "#6b7280")
    _kpi(c4, f"{pct_justificados}%", "Justificados", "#d97706")
    _kpi(c5, f"{reincidentes:,}", "Reincidentes (>=3)", "#7c3aed")
    _kpi(c6, f"{criticos:,}", "Criticos (>=8)", "#dc2626")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Visualizaciones</div>', unsafe_allow_html=True)
    g1, g2 = st.columns(2)

    with g1:
        if df_serie is not None and not df_serie.empty:
            fig_serie = go.Figure()
            fig_serie.add_trace(
                go.Scatter(
                    x=pd.to_datetime(df_serie["fecha"]),
                    y=df_serie["atrasos_dia"],
                    mode="lines+markers",
                    line={"color": "#2563eb", "width": 2.5},
                    marker={"size": 7, "color": "#2563eb"},
                    hovertemplate="<b>%{x|%d/%m}</b>: %{y} atrasos<extra></extra>",
                )
            )
            fig_serie.update_layout(
                paper_bgcolor="#0d1220",
                plot_bgcolor="#0d1220",
                font={"color": "#e2e8f0"},
                height=280,
                title={"text": f"Serie diaria de atrasos (corte {corte_lbl})", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                xaxis={"gridcolor": "#1a2035", "tickfont": {"color": "#a0aec0"}},
                yaxis={"gridcolor": "#1a2035", "tickfont": {"color": "#a0aec0"}},
                margin={"l": 16, "r": 16, "t": 40, "b": 16},
                showlegend=False,
            )
            st.plotly_chart(fig_serie, use_container_width=True, config={"displayModeBar": False})

    with g2:
        if df_cursos is not None and not df_cursos.empty:
            top_cursos = df_cursos.sort_values("total_atrasos", ascending=False).head(12)
            fig_bar = go.Figure(
                go.Bar(
                    x=top_cursos["curso"],
                    y=top_cursos["total_atrasos"],
                    marker_color="#d97706",
                    text=top_cursos["total_atrasos"],
                    textposition="outside",
                    hovertemplate="<b>%{x}</b>: %{y} atrasos<extra></extra>",
                )
            )
            fig_bar.update_layout(
                paper_bgcolor="#0d1220",
                plot_bgcolor="#0d1220",
                font={"color": "#e2e8f0"},
                height=280,
                title={"text": "Top cursos con mas atrasos", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                xaxis={"gridcolor": "#1a2035", "tickfont": {"color": "#a0aec0"}},
                yaxis={"gridcolor": "#1a2035", "tickfont": {"color": "#a0aec0"}},
                margin={"l": 16, "r": 16, "t": 40, "b": 16},
                showlegend=False,
            )
            st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Alumnos con mayor recurrencia</div>', unsafe_allow_html=True)
    if df_alumnos is not None and not df_alumnos.empty:
        cols = ["rut_norm", "nombre", "curso", "n_atrasos", "dias_con_atraso", "pct_justificados", "alerta"]
        cols = [c for c in cols if c in df_alumnos.columns]
        show_pretty_table(
            df_alumnos.sort_values(["n_atrasos", "dias_con_atraso"], ascending=[False, False]).head(30)[cols],
            max_rows=30,
            height=360,
        )

    with st.expander("Ver detalle de eventos de atraso", expanded=False):
        show_pretty_table(df_eventos, max_rows=200, height=420)

    st.markdown('<div class="section-title">Reportes y DATA entregable</div>', unsafe_allow_html=True)
    resumen = pd.DataFrame(
        [
            {
                "corte": corte_lbl,
                "eventos": total_atrasos,
                "alumnos_unicos": alumnos_unicos,
                "cursos_afectados": cursos_afectados,
                "pct_justificados": pct_justificados,
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
        "cursos_afectados": cursos_afectados,
        "pct_justificados": pct_justificados,
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

    pdf_bytes = generate_executive_pdf(
        module_name="Atrasos",
        corte=str(corte_lbl),
        kpis=pdf_kpis,
        tables=[
            ("Resumen ejecutivo", resumen),
            ("Top alumnos con mayor recurrencia", top_alumnos_pdf),
            ("Top cursos con mayor atrasos", top_cursos_pdf),
            ("Serie diaria de atrasos", serie_pdf),
        ],
    )

    st.markdown('<div class="section-title">PDF Ejecutivo del módulo</div>', unsafe_allow_html=True)
    st.download_button(
        "Descargar PDF Ejecutivo Atrasos",
        data=pdf_bytes,
        file_name=f"atrasos_ejecutivo__{safe_stamp}.pdf",
        mime="application/pdf",
        use_container_width=True,
        key="dl_atrasos_pdf_ejecutivo",
    )
    with st.expander("Ver PDF Ejecutivo en pantalla", expanded=False):
        render_pdf_preview(pdf_bytes, height=700)