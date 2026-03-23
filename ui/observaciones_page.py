"""
SIGMA — Módulo Observaciones
ui/observaciones_page.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.staging.build_stg_observaciones import run as run_obs
from src.validation.schema_registry import SCHEMA_OBSERVACIONES
from src.validation.schema_validator import validar_columnas
from ui.executive_pdf import generate_pdf_observaciones, render_pdf_preview, show_pretty_table
from ui.schema_feedback import mostrar_validacion_esquema

MIME_CSV = "text/csv"

COLORES_TIPO = {
    "NEG": "#dc2626",
    "POS": "#16a34a",
    "OBS": "#2563eb",
}
LABEL_TIPO = {
    "NEG": "🔴 Negativa",
    "POS": "🟢 Positiva",
    "OBS": "🔵 Neutra",
}
COLORES_ALERTA = {
    "CRITICO": "#dc2626",
    "ALTO":    "#d97706",
    "MEDIO":   "#7c3aed",
    "BAJO":    "#16a34a",
}


def _kpi(col, val, label, color="#2563eb"):
    col.markdown(
        f"""
        <div style="background:#0d1220;border-radius:8px;padding:14px 8px;text-align:center;
                    border:1px solid rgba(99,179,237,0.10);border-bottom:3px solid {color}">
            <div style="font-size:1.7rem;font-weight:700;color:{color}">{val}</div>
            <div style="font-size:0.68rem;color:#94a3b8;margin-top:2px;text-transform:uppercase">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def _read_csv(uploaded_file, nrows=None) -> pd.DataFrame:
    for enc in ["utf-8", "utf-8-sig", "cp1252", "latin-1"]:
        try:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, sep=";", encoding=enc,
                               nrows=nrows, on_bad_lines="skip")
        except Exception:
            pass
    raise ValueError("No se pudo leer el CSV de observaciones.")


def render_observaciones_page():
    st.markdown("""
    <div class="sigma-header">
        <div>
            <div class="sigma-logo" style="font-size:1.5rem">SIGMA</div>
            <div class="sigma-tagline">Observaciones de convivencia</div>
        </div>
    </div>""", unsafe_allow_html=True)

    obs_gold = Path("data/gold/observaciones")

    # ── Carga de archivo ──────────────────────────────────────────────
    obs_file = st.file_uploader(
        "Cargar CSV de Syscol (observaciones_*.csv)",
        type=["csv"],
        key="obs_uploader",
    )

    if obs_file is not None:
        try:
            preview = _read_csv(obs_file, nrows=5)
            resultado = validar_columnas(preview.columns.tolist(), SCHEMA_OBSERVACIONES)
            mostrar_validacion_esquema(resultado)
            obs_file.seek(0)
        except Exception as e:
            st.markdown(f'<div class="sigma-alert danger">Error al leer el archivo: {e}</div>',
                        unsafe_allow_html=True)
            obs_file.seek(0)

    # ── Cargar datos ──────────────────────────────────────────────────
    df_eventos = df_alumnos = df_cursos = df_docentes = df_serie = None
    corte_lbl = "-"

    if (obs_gold / "obs_eventos.csv").exists() and obs_file is None:
        try:
            df_eventos  = pd.read_csv(obs_gold / "obs_eventos.csv",  encoding="utf-8")
            df_alumnos  = pd.read_csv(obs_gold / "obs_alumnos.csv",  encoding="utf-8")
            df_cursos   = pd.read_csv(obs_gold / "obs_cursos.csv",   encoding="utf-8")
            df_docentes = pd.read_csv(obs_gold / "obs_docentes.csv", encoding="utf-8")
            df_serie    = pd.read_csv(obs_gold / "obs_serie.csv",    encoding="utf-8")
            meta        = pd.read_csv(obs_gold / "obs_meta.csv",     encoding="utf-8")
            corte_lbl   = str(meta.iloc[0].get("corte", "-"))
            st.markdown(
                f'<div class="sigma-alert info">Observaciones cargadas desde gold — corte: <b>{corte_lbl}</b></div>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.markdown(f'<div class="sigma-alert danger">Error cargando datos guardados: {e}</div>',
                        unsafe_allow_html=True)

    if obs_file is not None:
        try:
            df_raw = _read_csv(obs_file)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv",
                                             mode="w", encoding="utf-8-sig", newline="") as tmp:
                df_raw.to_csv(tmp.name, index=False, sep=";")
                tmp_path = tmp.name
            try:
                r = run_obs(tmp_path, obs_gold)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            df_eventos  = r["eventos"]
            df_alumnos  = r["alumnos"]
            df_cursos   = r["cursos"]
            df_docentes = r["docentes"]
            df_serie    = r["serie"]
            corte_lbl   = str(r["corte"])
            st.markdown(
                f'<div class="sigma-alert success">Observaciones procesadas — {len(df_eventos):,} registros hasta {corte_lbl}</div>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.markdown(f'<div class="sigma-alert danger">Error procesando CSV: {e}</div>',
                        unsafe_allow_html=True)

    if df_eventos is None or df_eventos.empty:
        st.markdown("""
        <div class="sigma-alert info">
            <b>Cómo usar el módulo de Observaciones:</b><br>
            1. Exporta el reporte de observaciones desde Syscol como CSV<br>
            2. Cárgalo con el botón de arriba<br>
            3. SIGMA generará indicadores por alumno, curso y docente
        </div>""", unsafe_allow_html=True)
        return

    # ── Métricas globales ─────────────────────────────────────────────
    total_obs   = len(df_eventos)
    n_alumnos   = int(df_eventos["rut_norm"].nunique()) if "rut_norm" in df_eventos.columns else 0
    n_cursos    = int(df_eventos["curso"].nunique()) if "curso" in df_eventos.columns else 0
    n_negativas = int((df_eventos["tipo"] == "NEG").sum()) if "tipo" in df_eventos.columns else 0
    n_positivas = int((df_eventos["tipo"] == "POS").sum()) if "tipo" in df_eventos.columns else 0
    n_neutras   = int((df_eventos["tipo"] == "OBS").sum()) if "tipo" in df_eventos.columns else 0
    pct_neg     = round(n_negativas / total_obs * 100, 1) if total_obs else 0
    criticos    = int((df_alumnos["alerta"] == "CRITICO").sum()) if "alerta" in df_alumnos.columns else 0
    altos       = int((df_alumnos["alerta"] == "ALTO").sum()) if "alerta" in df_alumnos.columns else 0

    # ── TABS ──────────────────────────────────────────────────────────
    tab_dash, tab_alumnos, tab_cursos_t, tab_docentes_t, tab_historial, tab_rep = st.tabs([
        "⚡ Dashboard",
        f"👥 Alumnos ({n_alumnos})",
        f"🏫 Por curso ({n_cursos})",
        "👨‍🏫 Por docente",
        "🔍 Historial alumno",
        "📄 Reportes",
    ])

    # ════════════════════════════════════════════════════════
    # TAB DASHBOARD
    # ════════════════════════════════════════════════════════
    with tab_dash:
        st.markdown('<div class="section-title">Indicadores generales</div>', unsafe_allow_html=True)

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        _kpi(c1, f"{total_obs:,}",    "Observaciones",       "#2563eb")
        _kpi(c2, f"{n_alumnos:,}",    "Alumnos involucrados","#6b7280")
        _kpi(c3, f"{n_negativas:,}",  "Negativas",           "#dc2626")
        _kpi(c4, f"{pct_neg}%",       "% Negativas",         "#dc2626")
        _kpi(c5, f"{criticos:,}",     "Críticos (≥5 neg.)",  "#dc2626")
        _kpi(c6, f"{n_positivas:,}",  "Positivas",           "#16a34a")
        st.markdown("<br>", unsafe_allow_html=True)

        g1, g2 = st.columns(2)

        with g1:
            # Donut por tipo
            tipos   = ["NEG", "OBS", "POS"]
            vals    = [n_negativas, n_neutras, n_positivas]
            labels  = ["🔴 Negativas", "🔵 Neutras", "🟢 Positivas"]
            colores = ["#dc2626", "#2563eb", "#16a34a"]
            fig_tipo = go.Figure(go.Pie(
                labels=labels, values=vals, hole=0.52,
                marker={"colors": colores},
                textinfo="percent",          # solo porcentaje dentro del slice
                textposition="inside",
                insidetextorientation="radial",
                textfont={"size": 12, "color": "#ffffff", "family": "DM Sans"},
                hovertemplate="<b>%{label}</b>: %{value} (%{percent})<extra></extra>",
                showlegend=True,
            ))
            fig_tipo.update_layout(
                paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                font={"color": "#e2e8f0"}, height=300,
                margin={"l": 10, "r": 120, "t": 40, "b": 10},
                title={"text": "Distribución por tipo", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                legend={
                    "font": {"size": 11}, "bgcolor": "rgba(0,0,0,0)",
                    "orientation": "v", "x": 1.02, "y": 0.5,
                    "xanchor": "left", "yanchor": "middle",
                },
                annotations=[
                    {"text": f"<b>{total_obs}</b>", "x": 0.42, "y": 0.55,
                     "font": {"size": 20, "color": "#e2e8f0"}, "showarrow": False},
                    {"text": "total", "x": 0.42, "y": 0.42,
                     "font": {"size": 10, "color": "#4a5568"}, "showarrow": False},
                ],
            )
            st.plotly_chart(fig_tipo, use_container_width=True, config={"displayModeBar": False})

        with g2:
            # Serie diaria
            if df_serie is not None and not df_serie.empty and "fecha" in df_serie.columns:
                fig_serie = go.Figure()
                neg_col   = df_serie["negativas_dia"] if "negativas_dia" in df_serie.columns else pd.Series([0]*len(df_serie))
                total_col = df_serie["total_dia"]   if "total_dia"    in df_serie.columns else pd.Series([0]*len(df_serie))
                otras_col = (total_col - neg_col).clip(lower=0)
                fig_serie.add_trace(go.Bar(
                    x=df_serie["fecha"], y=neg_col,
                    name="Negativas", marker_color="#dc2626", opacity=0.85,
                    hovertemplate="<b>%{x}</b><br>Negativas: %{y}<extra></extra>",
                ))
                fig_serie.add_trace(go.Bar(
                    x=df_serie["fecha"], y=otras_col,
                    name="Neutras / Positivas", marker_color="#2563eb", opacity=0.6,
                    hovertemplate="<b>%{x}</b><br>Otras: %{y}<extra></extra>",
                ))
                fig_serie.update_layout(
                    barmode="stack",
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color": "#e2e8f0"}, height=300,
                    margin={"l": 10, "r": 10, "t": 40, "b": 10},
                    title={"text": "Observaciones por día", "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                    xaxis={"gridcolor": "#1a2035"}, yaxis={"gridcolor": "#1a2035"},
                    legend={"font": {"size": 10}, "bgcolor": "rgba(0,0,0,0)", "orientation": "h", "y": -0.15},
                )
                st.plotly_chart(fig_serie, use_container_width=True, config={"displayModeBar": False})

        # Distribución alerta
        st.markdown('<div class="section-title">Distribución por nivel de alerta</div>', unsafe_allow_html=True)
        if "alerta" in df_alumnos.columns:
            orden = ["CRITICO", "ALTO", "MEDIO", "BAJO"]
            conteos = {nivel: int((df_alumnos["alerta"] == nivel).sum()) for nivel in orden}
            fig_alert = go.Figure(go.Bar(
                x=orden, y=[conteos[n] for n in orden],
                marker_color=[COLORES_ALERTA[n] for n in orden],
                text=[conteos[n] for n in orden],
                textposition="outside", textfont={"size": 12, "color": "#e2e8f0"},
                hovertemplate="<b>%{x}</b>: %{y} alumnos<extra></extra>",
            ))
            fig_alert.update_layout(
                paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                font={"color": "#e2e8f0"}, height=260,
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                xaxis={"gridcolor": "rgba(0,0,0,0)"},
                yaxis={"gridcolor": "#1a2035"},
                showlegend=False,
            )
            st.plotly_chart(fig_alert, use_container_width=True, config={"displayModeBar": False})

    # ════════════════════════════════════════════════════════
    # TAB ALUMNOS
    # ════════════════════════════════════════════════════════
    with tab_alumnos:
        st.markdown('<div class="section-title">Alumnos con observaciones</div>', unsafe_allow_html=True)

        # Filtros
        f1, f2, f3 = st.columns(3)
        with f1:
            alertas_opts = ["Todos", "CRITICO", "ALTO", "MEDIO", "BAJO"]
            fil_alerta = st.selectbox("Nivel de alerta", alertas_opts, key="obs_alerta")
        with f2:
            cursos_opts = ["Todos"] + sorted(df_alumnos["curso"].dropna().unique().tolist()) \
                if "curso" in df_alumnos.columns else ["Todos"]
            fil_curso = st.selectbox("Curso", cursos_opts, key="obs_curso_al")
        with f3:
            orden_opts = ["Más negativas", "Más observaciones", "Nombre"]
            fil_orden  = st.selectbox("Ordenar por", orden_opts, key="obs_orden")

        df_al = df_alumnos.copy()
        if fil_alerta != "Todos" and "alerta" in df_al.columns:
            df_al = df_al[df_al["alerta"] == fil_alerta]
        if fil_curso != "Todos" and "curso" in df_al.columns:
            df_al = df_al[df_al["curso"] == fil_curso]

        sort_col = {"Más negativas": "obs_negativas", "Más observaciones": "total_obs", "Nombre": "nombre"}
        asc_col  = {"Más negativas": False, "Más observaciones": False, "Nombre": True}
        sc = sort_col.get(fil_orden, "obs_negativas")
        if sc in df_al.columns:
            df_al = df_al.sort_values(sc, ascending=asc_col.get(fil_orden, False))

        st.markdown(
            f'<div class="record-count">Mostrando <span>{len(df_al):,}</span> alumnos</div>',
            unsafe_allow_html=True,
        )

        df_al_show = df_al.rename(columns={
            "nombre":         "Nombre",
            "curso":          "Curso",
            "total_obs":      "Total obs.",
            "obs_negativas":  "Negativas",
            "obs_positivas":  "Positivas",
            "obs_neutras":    "Neutras",
            "pct_negativas":  "% Neg.",
            "alerta":         "Alerta",
            "primera_obs":    "Primera obs.",
            "ultima_obs":     "Última obs.",
        }).copy()

        if "Alerta" in df_al_show.columns:
            emoji_map = {"CRITICO": "🔴 Crítico", "ALTO": "🟡 Alto",
                         "MEDIO":   "🟠 Medio",   "BAJO": "🟢 Bajo"}
            df_al_show["Alerta"] = df_al_show["Alerta"].map(emoji_map).fillna("—")
        if "% Neg." in df_al_show.columns:
            df_al_show["% Neg."] = df_al_show["% Neg."].apply(
                lambda v: f"{v:.1f}%" if pd.notna(v) else "—"
            )

        show_cols = [c for c in ["Nombre","Curso","Total obs.","Negativas","Positivas",
                                  "Neutras","% Neg.","Alerta","Última obs."] if c in df_al_show.columns]
        show_pretty_table(df_al_show[show_cols], max_rows=200, height=500)

    # ════════════════════════════════════════════════════════
    # TAB CURSOS
    # ════════════════════════════════════════════════════════
    with tab_cursos_t:
        st.markdown('<div class="section-title">Observaciones por curso</div>', unsafe_allow_html=True)

        if df_cursos is not None and not df_cursos.empty:
            c_left, c_right = st.columns([2, 3])

            with c_left:
                df_c_show = df_cursos.rename(columns={
                    "curso":               "Curso",
                    "total_obs":           "Total",
                    "alumnos_unicos":      "Alumnos",
                    "obs_negativas":       "Negativas",
                    "obs_positivas":       "Positivas",
                    "pct_negativas":       "% Neg.",
                    "promedio_por_alumno": "Prom/Alumno",
                }).copy()
                if "% Neg." in df_c_show.columns:
                    df_c_show["% Neg."] = df_c_show["% Neg."].apply(
                        lambda v: f"{v:.1f}%"
                    )
                show_cols_c = [c for c in ["Curso","Total","Alumnos","Negativas","% Neg.","Prom/Alumno"] if c in df_c_show.columns]
                show_pretty_table(df_c_show[show_cols_c], max_rows=50, height=520)

            with c_right:
                df_c = df_cursos.sort_values("total_obs", ascending=True)
                max_obs = df_c["total_obs"].max() or 1
                colores_c = [
                    "#dc2626" if v/max_obs >= 0.7 else ("#d97706" if v/max_obs >= 0.4 else "#2563eb")
                    for v in df_c["total_obs"]
                ]
                fig_c = go.Figure(go.Bar(
                    name="Total obs.",
                    y=df_c["curso"], x=df_c["total_obs"],
                    orientation="h",
                    marker_color=colores_c,
                    text=df_c["total_obs"], textposition="outside",
                    textfont={"size": 10, "color": "#e2e8f0"},
                    hovertemplate="<b>%{y}</b>: %{x} obs.<extra></extra>",
                ))
                # Superponer negativas
                df_c2 = df_cursos.sort_values("total_obs", ascending=True)
                fig_c.add_trace(go.Bar(
                    y=df_c2["curso"], x=df_c2.get("obs_negativas", df_c2["total_obs"]),
                    orientation="h",
                    marker_color="rgba(220,38,38,0.35)",
                    name="Negativas",
                    hovertemplate="<b>%{y}</b> negativas: %{x}<extra></extra>",
                    showlegend=True,
                ))
                fig_c.update_layout(
                    barmode="overlay",
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color": "#e2e8f0"},
                    height=max(400, len(df_c) * 26),
                    margin={"l": 10, "r": 60, "t": 40, "b": 10},
                    title={"text": "Observaciones por curso (🔴 negativas superpuestas)",
                           "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                    xaxis={"gridcolor": "#1a2035"},
                    yaxis={"gridcolor": "rgba(0,0,0,0)", "tickfont": {"size": 10}},
                    legend={"font": {"size": 10}, "bgcolor": "rgba(0,0,0,0)"},
                )
                st.plotly_chart(fig_c, use_container_width=True, config={"displayModeBar": False})

    # ════════════════════════════════════════════════════════
    # TAB DOCENTES
    # ════════════════════════════════════════════════════════
    with tab_docentes_t:
        st.markdown('<div class="section-title">Observaciones registradas por docente</div>', unsafe_allow_html=True)

        if df_docentes is not None and not df_docentes.empty:
            d_left, d_right = st.columns([2, 3])

            with d_left:
                df_d_show = df_docentes.rename(columns={
                    "docente":        "Docente",
                    "total_obs":      "Total",
                    "alumnos_unicos": "Alumnos",
                    "obs_negativas":  "Negativas",
                    "obs_positivas":  "Positivas",
                    "obs_neutras":    "Neutras",
                }).copy()
                show_pretty_table(df_d_show, max_rows=30, height=460)

            with d_right:
                df_d = df_docentes.sort_values("total_obs", ascending=True).tail(15)
                fig_d = go.Figure(go.Bar(
                    y=df_d["docente"], x=df_d["total_obs"],
                    orientation="h",
                    marker={"color": df_d["total_obs"],
                            "colorscale": [[0, "#1a2035"], [1, "#7c3aed"]]},
                    text=df_d["total_obs"], textposition="outside",
                    textfont={"size": 11, "color": "#e2e8f0"},
                    hovertemplate="<b>%{y}</b>: %{x} obs.<extra></extra>",
                ))
                fig_d.update_layout(
                    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
                    font={"color": "#e2e8f0"}, height=420,
                    margin={"l": 10, "r": 60, "t": 40, "b": 10},
                    title={"text": "Observaciones por docente",
                           "font": {"size": 12, "color": "#63b3ed"}, "x": 0},
                    xaxis={"gridcolor": "#1a2035"},
                    yaxis={"gridcolor": "rgba(0,0,0,0)", "tickfont": {"size": 10}},
                    showlegend=False,
                )
                st.plotly_chart(fig_d, use_container_width=True, config={"displayModeBar": False})

    # ════════════════════════════════════════════════════════
    # TAB HISTORIAL ALUMNO
    # ════════════════════════════════════════════════════════
    with tab_historial:
        st.markdown('<div class="section-title">Historial de observaciones por alumno</div>', unsafe_allow_html=True)

        busqueda = st.text_input(
            "🔍 Buscar por nombre o RUT",
            placeholder="Ej: RODRIGUEZ o 12345678-9",
            key="obs_busqueda",
        )

        if busqueda and len(busqueda) >= 3:
            busq = busqueda.strip().upper()
            mask = pd.Series([False] * len(df_alumnos), index=df_alumnos.index)
            if "nombre" in df_alumnos.columns:
                mask |= df_alumnos["nombre"].astype(str).str.upper().str.contains(busq, na=False)
            if "rut_norm" in df_alumnos.columns:
                mask |= df_alumnos["rut_norm"].astype(str).str.contains(busq, na=False)
            resultados = df_alumnos[mask]

            if resultados.empty:
                st.markdown('<div class="sigma-alert">No se encontraron alumnos con ese criterio.</div>',
                            unsafe_allow_html=True)
            else:
                for _, alu in resultados.iterrows():
                    nombre  = str(alu.get("nombre", "—"))
                    curso   = str(alu.get("curso", "—"))
                    n_total = int(alu.get("total_obs", 0))
                    n_neg   = int(alu.get("obs_negativas", 0))
                    n_pos   = int(alu.get("obs_positivas", 0))
                    alerta  = str(alu.get("alerta", "—"))
                    emoji   = {"CRITICO":"🔴","ALTO":"🟡","MEDIO":"🟠","BAJO":"🟢"}.get(alerta, "⚪")
                    color_a = COLORES_ALERTA.get(alerta, "#6b7280")

                    with st.expander(
                        f"{emoji} {nombre} — {curso}  |  {n_total} obs.  |  {n_neg} negativas  |  Alerta: {alerta}",
                        expanded=True,
                    ):
                        ic1, ic2, ic3, ic4 = st.columns(4)
                        _kpi(ic1, str(n_total), "Total obs.",    "#2563eb")
                        _kpi(ic2, str(n_neg),   "Negativas",     "#dc2626")
                        _kpi(ic3, str(n_pos),   "Positivas",     "#16a34a")
                        _kpi(ic4, alerta,       "Nivel de alerta", color_a)
                        st.markdown("<br>", unsafe_allow_html=True)

                        # Eventos del alumno
                        if "rut_norm" in df_eventos.columns:
                            rut_key = str(alu.get("rut_norm", ""))
                            df_hist = df_eventos[
                                df_eventos["rut_norm"].astype(str) == rut_key
                            ].copy().sort_values("fecha", ascending=False)

                            if not df_hist.empty:
                                # Tag visual por tipo
                                def _tag(t):
                                    return {"NEG":"🔴 Negativa","POS":"🟢 Positiva","OBS":"🔵 Neutra"}.get(t, t)
                                df_hist["tipo_label"] = df_hist["tipo"].apply(_tag)
                                cols_h = [c for c in ["fecha","hora","tipo_label","descripcion","docente","curso"] if c in df_hist.columns]
                                df_hist_show = df_hist[cols_h].rename(columns={
                                    "fecha":"Fecha","hora":"Hora","tipo_label":"Tipo",
                                    "descripcion":"Descripción","docente":"Docente","curso":"Curso",
                                })
                                show_pretty_table(df_hist_show, max_rows=50, height=320)
                            else:
                                st.info("Sin eventos registrados.")
        elif busqueda and len(busqueda) < 3:
            st.caption("Ingresa al menos 3 caracteres para buscar.")
        else:
            st.markdown(
                '<div class="sigma-alert info">Ingresa un nombre o RUT para ver el historial completo de observaciones del alumno.</div>',
                unsafe_allow_html=True,
            )
            # Top alumnos críticos por defecto
            if "alerta" in df_alumnos.columns:
                df_top = df_alumnos[df_alumnos["alerta"].isin(["CRITICO","ALTO"])].copy()
                if not df_top.empty:
                    st.markdown('<div class="section-title" style="margin-top:16px">Alumnos críticos y altos</div>',
                                unsafe_allow_html=True)
                    df_top = df_top.sort_values("obs_negativas", ascending=False).reset_index(drop=True)
                    df_top_show = df_top.rename(columns={
                        "nombre":"Nombre","curso":"Curso","total_obs":"Total",
                        "obs_negativas":"Negativas","obs_positivas":"Positivas",
                        "pct_negativas":"% Neg.","alerta":"Alerta",
                    })
                    if "Alerta" in df_top_show.columns:
                        df_top_show["Alerta"] = df_top_show["Alerta"].map(
                            {"CRITICO":"🔴 Crítico","ALTO":"🟡 Alto"}
                        ).fillna("—")
                    if "% Neg." in df_top_show.columns:
                        df_top_show["% Neg."] = df_top_show["% Neg."].apply(lambda v: f"{v:.1f}%")
                    show_cols_t = [c for c in ["Nombre","Curso","Total","Negativas","% Neg.","Alerta"] if c in df_top_show.columns]
                    show_pretty_table(df_top_show[show_cols_t], max_rows=50, height=400)

    # ════════════════════════════════════════════════════════
    # TAB REPORTES
    # ════════════════════════════════════════════════════════
    with tab_rep:
        st.markdown('<div class="section-title">Reportes y DATA entregable</div>', unsafe_allow_html=True)

        resumen = pd.DataFrame([{
            "Corte":         corte_lbl,
            "Observaciones": total_obs,
            "Alumnos":       n_alumnos,
            "Cursos":        n_cursos,
            "Negativas":     n_negativas,
            "% Negativas":   f"{pct_neg}%",
            "Positivas":     n_positivas,
            "Críticos":      criticos,
            "Altos":         altos,
        }])
        show_pretty_table(resumen, max_rows=5, height=110)
        st.markdown("<br>", unsafe_allow_html=True)

        d1, d2, d3, d4, d5 = st.columns(5)
        safe_stamp = str(corte_lbl).replace("-", "")
        d1.download_button("📥 Resumen",   data=_to_csv_bytes(resumen),
            file_name=f"obs_resumen__{safe_stamp}.csv",    mime=MIME_CSV, use_container_width=True, key="dl_obs_resumen")
        d2.download_button("📥 Eventos",   data=_to_csv_bytes(df_eventos),
            file_name=f"obs_eventos__{safe_stamp}.csv",    mime=MIME_CSV, use_container_width=True, key="dl_obs_eventos")
        d3.download_button("📥 Alumnos",   data=_to_csv_bytes(df_alumnos),
            file_name=f"obs_alumnos__{safe_stamp}.csv",    mime=MIME_CSV, use_container_width=True, key="dl_obs_alumnos")
        d4.download_button("📥 Cursos",    data=_to_csv_bytes(df_cursos),
            file_name=f"obs_cursos__{safe_stamp}.csv",     mime=MIME_CSV, use_container_width=True, key="dl_obs_cursos")
        d5.download_button("📥 Docentes",  data=_to_csv_bytes(df_docentes),
            file_name=f"obs_docentes__{safe_stamp}.csv",   mime=MIME_CSV, use_container_width=True, key="dl_obs_docentes")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">PDF Ejecutivo</div>', unsafe_allow_html=True)

        if st.button("📄 Generar PDF Ejecutivo Observaciones", use_container_width=True, key="btn_pdf_obs"):
            with st.spinner("Generando PDF ejecutivo..."):
                pdf_bytes = generate_pdf_observaciones(
                    df_eventos=df_eventos,
                    df_alumnos=df_alumnos,
                    df_cursos=df_cursos,
                    df_docentes=df_docentes,
                    df_serie=df_serie,
                    corte=str(corte_lbl),
                )
            st.session_state["pdf_observaciones"] = pdf_bytes

        if "pdf_observaciones" in st.session_state:
            pdf_bytes = st.session_state["pdf_observaciones"]
            st.download_button(
                "⬇️ Descargar PDF Ejecutivo Observaciones",
                data=pdf_bytes,
                file_name=f"SIGMA_Observaciones_{safe_stamp}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="dl_obs_pdf",
            )
            with st.expander("👁️ Ver PDF en pantalla", expanded=False):
                render_pdf_preview(pdf_bytes, height=700)