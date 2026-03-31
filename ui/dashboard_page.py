"""
SIGMA — Dashboard Ejecutivo Unificado
ui/dashboard_page.py

Vista consolidada de todos los módulos en una sola página.
Pensado para dirección y UTP — resumen rápido del estado del establecimiento.
"""
from __future__ import annotations

from pathlib import Path
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.executive_pdf import show_pretty_table, generate_pdf_ejecutivo

# ── Colores ───────────────────────────────────────────────────────────
C_RED    = "#dc2626"
C_AMBER  = "#d97706"
C_GREEN  = "#16a34a"
C_BLUE   = "#2563eb"
C_PURPLE = "#7c3aed"
C_MUTED  = "#4a5568"


def _kpi(col, val, label, color=C_BLUE, sub=""):
    col.markdown(
        f"""<div style="background:#0d1220;border-radius:10px;padding:16px 10px;
            text-align:center;border:1px solid rgba(99,179,237,0.10);
            border-bottom:3px solid {color};min-height:90px">
            <div style="font-size:1.8rem;font-weight:800;color:{color};line-height:1">{val}</div>
            <div style="font-size:0.62rem;color:#94a3b8;margin-top:4px;
                text-transform:uppercase;letter-spacing:1.5px">{label}</div>
            {f'<div style="font-size:0.6rem;color:{C_MUTED};margin-top:2px">{sub}</div>' if sub else ''}
        </div>""",
        unsafe_allow_html=True,
    )


def _semaforo(v, umbral_rojo, umbral_amarillo, invert=False):
    """Retorna color semáforo según umbrales."""
    if invert:
        if v >= umbral_rojo:    return C_RED
        if v >= umbral_amarillo: return C_AMBER
        return C_GREEN
    else:
        if v <= umbral_rojo:    return C_RED
        if v <= umbral_amarillo: return C_AMBER
        return C_GREEN


def _mini_gauge(pct: float, label: str, color: str) -> str:
    """Barra de progreso compacta."""
    pct_c = max(0, min(100, pct))
    return f"""
    <div style="margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:3px">
            <span style="font-size:0.72rem;color:#94a3b8">{label}</span>
            <span style="font-size:0.82rem;font-weight:700;color:{color}">{pct:.1f}%</span>
        </div>
        <div style="background:rgba(99,179,237,0.08);border-radius:4px;height:5px">
            <div style="width:{pct_c}%;background:{color};height:100%;border-radius:4px"></div>
        </div>
    </div>"""


def render_dashboard_page(
    df_current:          pd.DataFrame | None,
    metrics:             pd.DataFrame | None,
    stamp:               str = "",
):
    # ── Header ────────────────────────────────────────────────────────
    try:
        # Formatear fecha en español sin depender del locale del sistema
        _MESES_ES = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                     7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
        _dt = pd.to_datetime(stamp, format="%Y%m%d")
        fecha_label = f"{_dt.day} de {_MESES_ES[_dt.month]} de {_dt.year}"
    except Exception:
        fecha_label = stamp

    st.markdown(f"""
    <div class="sigma-header">
        <div>
            <div class="sigma-logo" style="font-size:1.5rem">SIGMA</div>
            <div class="sigma-tagline">Dashboard Ejecutivo · {fecha_label}</div>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── Cargar datos de todos los módulos ─────────────────────────────
    gold = Path("data/gold")

    # Matrícula
    row_m = metrics.iloc[0].to_dict() if metrics is not None and not metrics.empty else {}
    matriculados  = int(row_m.get("matriculados_actuales", 0) or 0)
    retirados     = int(row_m.get("retirados_reales", 0) or 0)
    n_alumnos_mat = len(df_current) if df_current is not None else 0

    # Asistencia
    df_asist_alumnos = _load_csv(gold / "asistencia/asistencia_alumnos.csv")
    df_asist_serie   = _load_csv(gold / "asistencia/asistencia_serie.csv")
    pct_asist_global = 0.0
    bajo85 = bajo75 = tend_baja = 0
    if df_asist_alumnos is not None and not df_asist_alumnos.empty:
        if "pct_asistencia" in df_asist_alumnos.columns:
            pct_asist_global = round(float(df_asist_alumnos["pct_asistencia"].mean()), 1)
        if "alerta" in df_asist_alumnos.columns:
            bajo85   = int(df_asist_alumnos["alerta"].isin(["LEGAL","CRITICO"]).sum())
            bajo75   = int((df_asist_alumnos["alerta"] == "CRITICO").sum())
        if "tendencia" in df_asist_alumnos.columns:
            tend_baja = int((df_asist_alumnos["tendencia"] == "BAJA").sum())

    # Atrasos
    df_atr_alumnos = _load_csv(gold / "atrasos/atrasos_alumnos.csv")
    total_atrasos = reincidentes_atr = criticos_atr = 0
    if df_atr_alumnos is not None and not df_atr_alumnos.empty:
        if "n_atrasos" in df_atr_alumnos.columns:
            total_atrasos    = int(df_atr_alumnos["n_atrasos"].sum())
            reincidentes_atr = int((df_atr_alumnos["n_atrasos"] >= 3).sum())
        if "alerta" in df_atr_alumnos.columns:
            criticos_atr = int((df_atr_alumnos["alerta"] == "CRITICO").sum())

    # Observaciones
    df_obs_alumnos = _load_csv(gold / "observaciones/obs_alumnos.csv")
    df_obs_serie   = _load_csv(gold / "observaciones/obs_serie.csv")
    total_obs = criticos_obs = altos_obs = 0
    if df_obs_alumnos is not None and not df_obs_alumnos.empty:
        if "total_obs" in df_obs_alumnos.columns:
            total_obs = int(df_obs_alumnos["total_obs"].sum())
        if "alerta" in df_obs_alumnos.columns:
            criticos_obs = int((df_obs_alumnos["alerta"] == "CRITICO").sum())
            altos_obs    = int((df_obs_alumnos["alerta"] == "ALTO").sum())

    # ── BLOQUE 1: KPIs críticos ───────────────────────────────────────
    st.markdown('<div class="section-title">Estado general del establecimiento</div>',
                unsafe_allow_html=True)

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    _kpi(k1, f"{matriculados:,}", "Matriculados",
         _semaforo(matriculados, 1200, 1250), f"{retirados} retirados")
    _kpi(k2, f"{pct_asist_global}%", "Asistencia global",
         _semaforo(pct_asist_global, 85, 90), f"↘ {tend_baja} bajando")
    _kpi(k3, f"{bajo85}", "Bajo 85% asistencia",
         _semaforo(bajo85, 100, 50, invert=True), f"{bajo75} críticos")
    _kpi(k4, f"{total_atrasos:,}", "Atrasos registrados",
         _semaforo(total_atrasos, 2000, 1000, invert=True), f"{criticos_atr} críticos")
    _kpi(k5, f"{total_obs:,}", "Observaciones",
         _semaforo(total_obs, 200, 100, invert=True), f"{criticos_obs} críticos")
    _kpi(k6, f"{criticos_obs + criticos_atr + bajo75}", "Alumnos en riesgo total",
         C_RED if (criticos_obs + criticos_atr + bajo75) > 20 else C_AMBER,
         "multi-módulo")
    st.markdown("<br>", unsafe_allow_html=True)

    # ── BLOQUE 2: Gráficos laterales ──────────────────────────────────
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown('<div class="section-title">Series temporales</div>', unsafe_allow_html=True)

        fig_series = go.Figure()

        # Asistencia diaria
        if df_asist_serie is not None and not df_asist_serie.empty and "pct_dia" in df_asist_serie.columns:
            df_asist_serie["fecha"] = pd.to_datetime(df_asist_serie["fecha"], errors="coerce")
            fig_series.add_trace(go.Scatter(
                x=df_asist_serie["fecha"], y=df_asist_serie["pct_dia"],
                name="% Asistencia", yaxis="y1",
                line={"color": C_BLUE, "width": 2},
                hovertemplate="<b>%{x|%d/%m}</b> Asistencia: %{y:.1f}%<extra></extra>",
            ))
            fig_series.add_hline(y=85, line_dash="dot", line_color=C_AMBER,
                line_width=1, annotation_text="85%",
                annotation_font={"color": C_AMBER, "size": 9})

        # Observaciones diarias
        if df_obs_serie is not None and not df_obs_serie.empty and "total_dia" in df_obs_serie.columns:
            df_obs_serie["fecha"] = pd.to_datetime(df_obs_serie["fecha"], errors="coerce")
            fig_series.add_trace(go.Bar(
                x=df_obs_serie["fecha"], y=df_obs_serie["total_dia"],
                name="Observaciones/día", yaxis="y2",
                marker_color="rgba(124,58,237,0.4)",
                hovertemplate="<b>%{x|%d/%m}</b> Obs: %{y}<extra></extra>",
            ))

        fig_series.update_layout(
            paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
            font={"color": "#e2e8f0"}, height=300,
            margin={"l": 10, "r": 60, "t": 10, "b": 10},
            legend={"font": {"size": 10}, "bgcolor": "rgba(0,0,0,0)",
                    "orientation": "h", "y": -0.15},
            yaxis={"gridcolor": "#1a2035",
                   "title": {"text": "% Asistencia", "font": {"color": C_BLUE, "size": 10}},
                   "range": [70, 102]},
            yaxis2={"overlaying": "y", "side": "right",
                    "title": {"text": "Observaciones", "font": {"color": C_PURPLE, "size": 10}},
                    "gridcolor": "rgba(0,0,0,0)"},
        )
        st.plotly_chart(fig_series, use_container_width=True, config={"displayModeBar": False})

    with col_right:
        st.markdown('<div class="section-title">Semáforos de riesgo</div>', unsafe_allow_html=True)

        gauges_html = ""
        # Asistencia
        color_asist = _semaforo(pct_asist_global, 85, 90)
        gauges_html += _mini_gauge(pct_asist_global, "Asistencia global", color_asist)

        # % alumnos bajo 85%
        pct_bajo85 = round(bajo85 / matriculados * 100, 1) if matriculados else 0
        color_b85 = _semaforo(100 - pct_bajo85, 85, 92)
        gauges_html += _mini_gauge(100 - pct_bajo85, "Alumnos sobre 85%", color_b85)

        # % sin atrasos
        n_con_atr = len(df_atr_alumnos) if df_atr_alumnos is not None else 0
        pct_sin_atr = round((1 - n_con_atr / matriculados) * 100, 1) if matriculados else 100
        color_atr = _semaforo(pct_sin_atr, 50, 70)
        gauges_html += _mini_gauge(pct_sin_atr, "Alumnos sin atrasos", color_atr)

        # % sin observaciones negativas
        n_con_obs_neg = int((df_obs_alumnos["obs_negativas"] > 0).sum()) \
            if df_obs_alumnos is not None and "obs_negativas" in (df_obs_alumnos.columns if df_obs_alumnos is not None else []) else 0
        pct_sin_obs = round((1 - n_con_obs_neg / matriculados) * 100, 1) if matriculados else 100
        color_obs = _semaforo(pct_sin_obs, 80, 90)
        gauges_html += _mini_gauge(pct_sin_obs, "Sin obs. negativas", color_obs)

        st.markdown(f'<div style="padding:16px 8px">{gauges_html}</div>',
                    unsafe_allow_html=True)

    # ── BLOQUE 3: Alumnos en riesgo multi-módulo ──────────────────────
    st.markdown('<div class="section-title">Alumnos en riesgo — vista consolidada</div>',
                unsafe_allow_html=True)

    if df_current is not None and not df_current.empty:
        def _norm(s): return str(s).strip().upper()

        df_riesgo = df_current[["nombre","course_code","specialty"]].copy()
        df_riesgo["_key"] = df_riesgo["nombre"].apply(_norm)
        df_riesgo = df_riesgo.rename(columns={
            "nombre": "Nombre", "course_code": "Curso", "specialty": "Especialidad"
        })
        df_riesgo["Asistencia"] = "—"
        df_riesgo["Atrasos"]    = 0
        df_riesgo["Obs. Neg."]  = 0
        df_riesgo["Riesgo"]     = 0

        # Enriquecer con asistencia
        if df_asist_alumnos is not None and not df_asist_alumnos.empty:
            df_asist_alumnos["_key"] = df_asist_alumnos["nombre"].apply(_norm) \
                if "nombre" in df_asist_alumnos.columns else df_asist_alumnos.index.astype(str)
            asist_map = df_asist_alumnos.set_index("_key")["pct_asistencia"] \
                if "pct_asistencia" in df_asist_alumnos.columns else pd.Series(dtype=float)
            df_riesgo["Asistencia"] = df_riesgo["_key"].map(asist_map).apply(
                lambda v: f"{v:.1f}%" if pd.notna(v) else "—"
            )
            alerta_asist = df_asist_alumnos.set_index("_key")["alerta"] \
                if "alerta" in df_asist_alumnos.columns else pd.Series(dtype=str)
            df_riesgo["_r_asist"] = df_riesgo["_key"].map(alerta_asist).map(
                {"CRITICO": 3, "LEGAL": 2, "NORMAL": 0}
            ).fillna(0)
            df_riesgo["Riesgo"] += df_riesgo["_r_asist"]

        # Enriquecer con atrasos
        if df_atr_alumnos is not None and not df_atr_alumnos.empty and "nombre" in df_atr_alumnos.columns:
            df_atr_alumnos["_key"] = df_atr_alumnos["nombre"].apply(_norm)
            atr_map = df_atr_alumnos.set_index("_key")["n_atrasos"] \
                if "n_atrasos" in df_atr_alumnos.columns else pd.Series(dtype=float)
            df_riesgo["Atrasos"] = df_riesgo["_key"].map(atr_map).fillna(0).astype(int)
            alerta_atr = df_atr_alumnos.set_index("_key")["alerta"] \
                if "alerta" in df_atr_alumnos.columns else pd.Series(dtype=str)
            df_riesgo["_r_atr"] = df_riesgo["_key"].map(alerta_atr).map(
                {"CRITICO": 3, "ALTO": 2, "MEDIO": 1, "BAJO": 0}
            ).fillna(0)
            df_riesgo["Riesgo"] += df_riesgo["_r_atr"]

        # Enriquecer con observaciones
        if df_obs_alumnos is not None and not df_obs_alumnos.empty and "nombre" in df_obs_alumnos.columns:
            df_obs_alumnos["_key"] = df_obs_alumnos["nombre"].apply(_norm)
            obs_map = df_obs_alumnos.set_index("_key")["obs_negativas"] \
                if "obs_negativas" in df_obs_alumnos.columns else pd.Series(dtype=float)
            df_riesgo["Obs. Neg."] = df_riesgo["_key"].map(obs_map).fillna(0).astype(int)
            alerta_obs = df_obs_alumnos.set_index("_key")["alerta"] \
                if "alerta" in df_obs_alumnos.columns else pd.Series(dtype=str)
            df_riesgo["_r_obs"] = df_riesgo["_key"].map(alerta_obs).map(
                {"CRITICO": 3, "ALTO": 2, "MEDIO": 1, "BAJO": 0}
            ).fillna(0)
            df_riesgo["Riesgo"] += df_riesgo["_r_obs"]

        # Filtrar solo los que tienen algún riesgo
        df_alto_riesgo = df_riesgo[df_riesgo["Riesgo"] >= 3].sort_values(
            "Riesgo", ascending=False
        ).reset_index(drop=True)

        df_alto_riesgo["Nivel"] = df_alto_riesgo["Riesgo"].apply(
            lambda v: "🔴 Crítico" if v >= 6 else ("🟡 Alto" if v >= 3 else "🟢 Normal")
        )

        cols_show = ["Nombre","Curso","Especialidad","Asistencia","Atrasos","Obs. Neg.","Nivel"]
        df_show = df_alto_riesgo[cols_show]

        if df_show.empty:
            st.markdown(
                '<div class="sigma-alert success">✅ Sin alumnos con riesgo cruzado alto en este corte.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="sigma-alert"><b>{len(df_show)} alumnos</b> con riesgo en múltiples módulos.</div>',
                unsafe_allow_html=True,
            )
            show_pretty_table(df_show, max_rows=50, height=400)

            # Descarga
            st.download_button(
                "📥 Descargar listado de riesgo consolidado",
                data=df_show.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                file_name=f"SIGMA_riesgo_consolidado__{stamp}.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_dashboard_riesgo",
            )

    # ── BLOQUE PDF ────────────────────────────────────────────────────
    st.markdown('<div class="section-title" style="margin-top:8px">📄 Reporte ejecutivo consolidado</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="sigma-alert info">Genera un PDF de 3 páginas con todos los módulos: '
        'matrícula, asistencia, atrasos, riesgo, histórico y benchmarking MINEDUC.</div>',
        unsafe_allow_html=True)

    if st.button("📥 Generar Reporte Ejecutivo PDF", type="primary",
                 use_container_width=True, key="btn_reporte_ejecutivo"):
        with st.spinner("Generando reporte..."):
            try:
                from pathlib import Path as _Path
                import pandas as _pd

                def _load_gold(name):
                    p = _Path(f"data/gold/{name}")
                    if not p.exists(): return None
                    try: return _pd.read_csv(p, encoding="utf-8")
                    except: return None

                pdf_bytes = generate_pdf_ejecutivo(
                    stamp=stamp,
                    df_current=df_current,
                    metrics=metrics,
                    df_asist_alumnos=_load_gold("asistencia/asistencia_alumnos.csv"),
                    df_asist_cursos=_load_gold("asistencia/asistencia_cursos.csv"),
                    df_asist_serie=_load_gold("asistencia/asistencia_serie.csv"),
                    df_atr_alumnos=_load_gold("atrasos/atrasos_alumnos.csv"),
                    df_atr_serie=_load_gold("atrasos/atrasos_serie.csv"),
                    df_atr_cursos=_load_gold("atrasos/atrasos_cursos.csv"),
                    df_hist_mat=_load_gold("historico/hist_matricula_resumen.csv"),
                    df_hist_atr=_load_gold("historico/hist_atrasos_resumen.csv"),
                    df_hist_asi=_load_gold("historico/hist_asistencia_mensual.csv"),
                )
                try:
                    _stamp_fmt = stamp.replace("/","")
                except Exception:
                    _stamp_fmt = str(stamp)
                st.download_button(
                    "⬇️ Descargar Reporte Ejecutivo",
                    data=pdf_bytes,
                    file_name=f"SIGMA_Reporte_Ejecutivo_{_stamp_fmt}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="dl_reporte_ejecutivo",
                )
            except Exception as e:
                import traceback
                st.error(f"Error generando PDF: {e}\n{traceback.format_exc()}")

    # ── BLOQUE 4: Resumen por especialidad ────────────────────────────
    st.markdown('<div class="section-title" style="margin-top:8px">Resumen por especialidad</div>',
                unsafe_allow_html=True)

    if df_current is not None and not df_current.empty and "specialty" in df_current.columns:
        specs = df_current["specialty"].dropna().unique().tolist()
        spec_cols = st.columns(len(specs))
        for col, spec in zip(spec_cols, sorted(specs)):
            df_sp = df_current[df_current["specialty"] == spec]
            n_sp  = len(df_sp)
            # Asistencia promedio de la especialidad
            asist_sp = "—"
            if df_asist_alumnos is not None and "nombre" in df_asist_alumnos.columns and "pct_asistencia" in df_asist_alumnos.columns:
                nombres_sp = set(df_sp["nombre"].str.upper().str.strip())
                sub = df_asist_alumnos[df_asist_alumnos["nombre"].str.upper().str.strip().isin(nombres_sp)]
                if not sub.empty:
                    asist_sp = f"{round(sub['pct_asistencia'].mean(), 1)}%"
            color_sp = {"TELECOM": C_BLUE, "ELECTRONICA": C_GREEN, "MECANICA": C_AMBER}.get(spec.upper(), C_PURPLE)
            col.markdown(
                f"""<div style="background:#0d1220;border-radius:10px;padding:16px;
                    border:1px solid rgba(99,179,237,0.10);border-left:4px solid {color_sp};
                    text-align:center">
                    <div style="font-size:0.65rem;color:{color_sp};text-transform:uppercase;
                        letter-spacing:2px;font-weight:700">{spec}</div>
                    <div style="font-size:1.6rem;font-weight:800;color:#e2e8f0;margin:6px 0">{n_sp:,}</div>
                    <div style="font-size:0.7rem;color:#94a3b8">alumnos · asist. {asist_sp}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    # ── BLOQUE 5: Análisis estadístico consolidado ────────────────────
    st.markdown('<div class="section-title" style="margin-top:16px">📊 Análisis estadístico consolidado</div>',
                unsafe_allow_html=True)

    tab_dist, tab_corr, tab_outliers = st.tabs([
        "📈 Distribuciones",
        "🔗 Correlaciones",
        "⚠️ Outliers",
    ])

    # ── TAB DISTRIBUCIONES ────────────────────────────────────────────
    with tab_dist:
        if df_asist_alumnos is not None and not df_asist_alumnos.empty and "pct_asistencia" in df_asist_alumnos.columns:
            import numpy as np

            pct = df_asist_alumnos["pct_asistencia"].dropna()
            n   = len(pct)

            # Medidas de tendencia central y dispersión
            media   = round(float(pct.mean()), 1)
            mediana = round(float(pct.median()), 1)
            std     = round(float(pct.std()), 1)
            q1      = round(float(pct.quantile(0.25)), 1)
            q3      = round(float(pct.quantile(0.75)), 1)
            iqr     = round(q3 - q1, 1)
            p_min   = round(float(pct.min()), 1)
            p_max   = round(float(pct.max()), 1)

            st.markdown('<div class="section-title">Asistencia — estadísticas descriptivas</div>',
                        unsafe_allow_html=True)

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Media",    f"{media}%",   help="Promedio aritmético — sensible a valores extremos")
            c2.metric("Mediana",  f"{mediana}%", help="Valor central — más representativo cuando hay outliers")
            c3.metric("Desv. Std",f"{std}%",     help="Dispersión respecto a la media")
            c4.metric("IQR",      f"{iqr}%",     help="Rango intercuartílico Q3-Q1 — dispersión robusta")

            c5,c6,c7,c8 = st.columns(4)
            c5.metric("Q1 (25%)", f"{q1}%",  help="El 25% de alumnos tiene asistencia bajo este valor")
            c6.metric("Q3 (75%)", f"{q3}%",  help="El 75% de alumnos tiene asistencia bajo este valor")
            c7.metric("Mínimo",   f"{p_min}%")
            c8.metric("Máximo",   f"{p_max}%")

            # Insight automático media vs mediana
            if abs(media - mediana) > 5:
                st.markdown(
                    f'<div class="sigma-alert warn">⚠️ La media ({media}%) y la mediana ({mediana}%) difieren en '
                    f'{abs(media-mediana):.1f}pp — la distribución es asimétrica. '
                    f'La mediana es más representativa del alumno típico.</div>',
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    f'<div class="sigma-alert info">✅ Media ({media}%) y mediana ({mediana}%) son similares — '
                    f'distribución aproximadamente simétrica.</div>',
                    unsafe_allow_html=True)

            # Histograma por rangos
            st.markdown('<div class="section-title" style="margin-top:8px">Distribución por rango de asistencia</div>',
                        unsafe_allow_html=True)

            rangos = [
                ("100%",    (pct == 100).sum(),              "#16a34a"),
                ("95-99%",  ((pct >= 95) & (pct < 100)).sum(), "#22c55e"),
                ("90-94%",  ((pct >= 90) & (pct < 95)).sum(),  "#86efac"),
                ("85-89%",  ((pct >= 85) & (pct < 90)).sum(),  "#fbbf24"),
                ("75-84%",  ((pct >= 75) & (pct < 85)).sum(),  "#f97316"),
                ("60-74%",  ((pct >= 60) & (pct < 75)).sum(),  "#ef4444"),
                ("<60%",    (pct < 60).sum(),                  "#991b1b"),
            ]
            max_n = max(r[1] for r in rangos) or 1
            for label, cnt, color in rangos:
                pct_bar = cnt / n * 100
                width   = int(cnt / max_n * 100)
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:10px;margin:3px 0;font-size:0.8rem">
                  <span style="min-width:55px;color:#94a3b8">{label}</span>
                  <div style="flex:1;background:#1a2035;border-radius:4px;height:20px">
                    <div style="width:{width}%;background:{color};height:100%;border-radius:4px;
                         transition:width 0.4s"></div>
                  </div>
                  <span style="min-width:90px;color:#e2e8f0">{cnt:,} alumnos ({pct_bar:.1f}%)</span>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("Sin datos de asistencia para análisis.")

        # Atrasos — distribución
        if df_atr_alumnos is not None and not df_atr_alumnos.empty and "n_atrasos" in df_atr_alumnos.columns:
            atr = df_atr_alumnos["n_atrasos"].dropna()
            n_atr = len(df_asist_alumnos) if df_asist_alumnos is not None else len(atr)

            st.markdown('<div class="section-title" style="margin-top:16px">Atrasos — estadísticas descriptivas</div>',
                        unsafe_allow_html=True)

            ca1,ca2,ca3,ca4 = st.columns(4)
            ca1.metric("Media atrasos",   f"{atr.mean():.1f}",  help="Entre alumnos con al menos 1 atraso")
            ca2.metric("Mediana atrasos", f"{atr.median():.0f}")
            ca3.metric("Desv. Std",       f"{atr.std():.1f}")
            ca4.metric("Máximo",          f"{int(atr.max())} atrasos")

            rangos_atr = [
                ("Sin atrasos", n_atr - len(atr),          "#16a34a"),
                ("1-2",        ((atr >= 1) & (atr <= 2)).sum(), "#fbbf24"),
                ("3-5",        ((atr >= 3) & (atr <= 5)).sum(), "#f97316"),
                ("6-9",        ((atr >= 6) & (atr <= 9)).sum(), "#ef4444"),
                ("10+",        (atr >= 10).sum(),              "#991b1b"),
            ]
            max_na = max(r[1] for r in rangos_atr) or 1
            for label, cnt, color in rangos_atr:
                pct_bar = cnt / n_atr * 100
                width   = int(cnt / max_na * 100)
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:10px;margin:3px 0;font-size:0.8rem">
                  <span style="min-width:70px;color:#94a3b8">{label}</span>
                  <div style="flex:1;background:#1a2035;border-radius:4px;height:20px">
                    <div style="width:{width}%;background:{color};height:100%;border-radius:4px"></div>
                  </div>
                  <span style="min-width:90px;color:#e2e8f0">{cnt:,} alumnos ({pct_bar:.1f}%)</span>
                </div>""", unsafe_allow_html=True)

    # ── TAB CORRELACIONES ─────────────────────────────────────────────
    with tab_corr:
        if (df_asist_alumnos is not None and not df_asist_alumnos.empty and
            df_atr_alumnos is not None and not df_atr_alumnos.empty):

            df_merged = df_asist_alumnos.merge(
                df_atr_alumnos[["rut_norm","n_atrasos","dias_con_atraso","pct_justificados"]],
                on="rut_norm", how="left"
            )
            df_merged["n_atrasos"]        = df_merged["n_atrasos"].fillna(0)
            df_merged["dias_con_atraso"]  = df_merged["dias_con_atraso"].fillna(0)
            df_merged["pct_justificados"] = df_merged["pct_justificados"].fillna(0)

            pct_col = df_merged["pct_asistencia"]

            corrs = {
                "% asistencia últimos 3 días":  ("pct_ultimos_3", "Fuerte — tendencia reciente predice el estado actual"),
                "N° de atrasos":                ("n_atrasos",      "Casi nula — atrasos ≠ ausentismo, son problemas independientes"),
                "Días con atraso":              ("dias_con_atraso","Casi nula — ídem"),
                "% atrasos justificados":       ("pct_justificados","Sin correlación relevante"),
            }

            st.markdown('<div class="section-title">Correlación de Pearson con % de asistencia</div>',
                        unsafe_allow_html=True)
            st.markdown(
                '<div class="sigma-alert info">El coeficiente r varía entre -1 (correlación negativa perfecta) '
                'y +1 (positiva perfecta). Valores cercanos a 0 indican que las variables son independientes.</div>',
                unsafe_allow_html=True)

            for nombre, (col, interpretacion) in corrs.items():
                if col in df_merged.columns:
                    r = round(float(pct_col.corr(df_merged[col])), 3)
                    abs_r   = abs(r)
                    color   = "#16a34a" if abs_r >= 0.5 else ("#f97316" if abs_r >= 0.2 else "#64748b")
                    width_b = int(abs_r * 100)
                    signo   = "+" if r >= 0 else ""
                    st.markdown(f"""
                    <div style="background:#0d1220;border-radius:8px;padding:12px 14px;margin:6px 0;
                         border:1px solid rgba(99,179,237,0.08)">
                      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                        <span style="font-size:0.82rem;color:#e2e8f0">{nombre}</span>
                        <span style="font-size:1rem;font-weight:700;color:{color}">r = {signo}{r}</span>
                      </div>
                      <div style="background:#1a2035;border-radius:4px;height:8px;margin-bottom:6px">
                        <div style="width:{width_b}%;background:{color};height:100%;border-radius:4px"></div>
                      </div>
                      <div style="font-size:0.75rem;color:#64748b">{interpretacion}</div>
                    </div>""", unsafe_allow_html=True)

            # Insight clave
            st.markdown("""
            <div class="sigma-alert warn" style="margin-top:12px">
            💡 <b>Implicancia para SIGMA:</b> Un alumno con muchos atrasos no necesariamente va a tener
            baja asistencia. Son dos poblaciones de riesgo distintas que requieren intervenciones separadas.
            El mejor predictor de asistencia baja es la propia tendencia reciente de asistencia.
            </div>""", unsafe_allow_html=True)
        else:
            st.info("Se necesitan datos de asistencia y atrasos para calcular correlaciones.")

    # ── TAB OUTLIERS ──────────────────────────────────────────────────
    with tab_outliers:
        st.markdown('<div class="section-title">Detección de outliers — método IQR y Z-score</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div class="sigma-alert info">Un outlier es un valor estadísticamente anómalo respecto al resto. '
            'Se usan dos métodos: IQR (robusto, basado en cuartiles) y Z-score (basado en desviación estándar).</div>',
            unsafe_allow_html=True)

        col_o1, col_o2 = st.columns(2)

        # Outliers asistencia — Z-score (IQR no sirve cuando Q1=Q3=100)
        with col_o1:
            st.markdown("**🔵 Outliers asistencia (Z-score)**")
            if df_asist_alumnos is not None and not df_asist_alumnos.empty and "pct_asistencia" in df_asist_alumnos.columns:
                pct = df_asist_alumnos["pct_asistencia"].dropna()
                media_z = pct.mean()
                std_z   = pct.std()
                if std_z > 0:
                    df_asist_alumnos["z_score"] = ((df_asist_alumnos["pct_asistencia"] - media_z) / std_z).round(2)
                    outliers_z = df_asist_alumnos[df_asist_alumnos["z_score"] < -2].copy()
                    outliers_z = outliers_z.sort_values("pct_asistencia")

                    st.markdown(f"*Z-score < -2 | {len(outliers_z)} alumnos detectados*")
                    st.markdown(
                        f'<div class="sigma-alert warn">⚠️ Nota: IQR no aplica aquí porque Q1=Q3=100% '
                        f'(el 76% tiene asistencia perfecta). Se usa Z-score en su lugar.</div>',
                        unsafe_allow_html=True)

                    if not outliers_z.empty:
                        cols_show = [c for c in ["nombre","curso","pct_asistencia","z_score"] if c in outliers_z.columns]
                        df_out_show = outliers_z[cols_show].rename(columns={
                            "nombre":"Nombre","curso":"Curso",
                            "pct_asistencia":"% Asist.","z_score":"Z-score"
                        })
                        show_pretty_table(df_out_show, max_rows=20, height=350)

        # Outliers atrasos — IQR
        with col_o2:
            st.markdown("**🔴 Outliers atrasos (IQR)**")
            if df_atr_alumnos is not None and not df_atr_alumnos.empty and "n_atrasos" in df_atr_alumnos.columns:
                atr = df_atr_alumnos["n_atrasos"]
                Q1  = atr.quantile(0.25)
                Q3  = atr.quantile(0.75)
                IQR = Q3 - Q1
                lim = Q3 + 1.5 * IQR

                outliers_atr = df_atr_alumnos[atr > lim].copy()
                outliers_atr = outliers_atr.sort_values("n_atrasos", ascending=False)

                st.markdown(f"*Límite: {lim:.0f} atrasos (Q3 + 1.5×IQR) | {len(outliers_atr)} detectados*")

                pct_asi_col = None
                if df_asist_alumnos is not None and "rut_norm" in df_asist_alumnos.columns:
                    outliers_atr = outliers_atr.merge(
                        df_asist_alumnos[["rut_norm","pct_asistencia"]],
                        on="rut_norm", how="left"
                    )
                    pct_asi_col = "pct_asistencia"

                if not outliers_atr.empty:
                    cols_atr = [c for c in ["nombre","curso","n_atrasos","pct_asistencia","alerta"]
                                if c in outliers_atr.columns]
                    df_atr_show = outliers_atr[cols_atr].rename(columns={
                        "nombre":"Nombre","curso":"Curso","n_atrasos":"Atrasos",
                        "pct_asistencia":"% Asist.","alerta":"Nivel"
                    })
                    show_pretty_table(df_atr_show, max_rows=20, height=350)

                    # Insight: ¿los outliers de atrasos tienen baja asistencia?
                    if pct_asi_col and pct_asi_col in outliers_atr.columns:
                        pct_100 = (outliers_atr[pct_asi_col] == 100).mean() * 100
                        st.markdown(
                            f'<div class="sigma-alert info">💡 {pct_100:.0f}% de los outliers de atrasos '
                            f'tiene 100% de asistencia — llegan todos los días pero siempre tarde.</div>',
                            unsafe_allow_html=True)


def _load_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, encoding="utf-8")
    except Exception:
        return None