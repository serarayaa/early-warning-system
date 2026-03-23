"""
SIGMA — Módulo Análisis Histórico 2022-2026
ui/historico_page.py
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from ui.executive_pdf import show_pretty_table

GOLD_HIST = Path("data/gold/historico")
C = {"TELECOM":"#2563eb","ELECTRONICA":"#16a34a","MECANICA":"#d97706","COMUN":"#6b7280"}
AÑOS_COLOR = {2022:"#6b7280",2023:"#7c3aed",2024:"#dc2626",2025:"#d97706",2026:"#2563eb"}
MESES = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
         7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}

def _kpi(col, val, label, color="#2563eb", sub=""):
    col.markdown(f"""
    <div style="background:#0d1220;border-radius:8px;padding:14px 8px;text-align:center;
        border:1px solid rgba(99,179,237,0.10);border-bottom:3px solid {color}">
        <div style="font-size:1.6rem;font-weight:800;color:{color}">{val}</div>
        <div style="font-size:0.62rem;color:#94a3b8;margin-top:3px;text-transform:uppercase">{label}</div>
        {f'<div style="font-size:0.6rem;color:#4a5568">{sub}</div>' if sub else ''}
    </div>""", unsafe_allow_html=True)

def _load(name):
    p = GOLD_HIST / name
    if not p.exists(): return None
    try: return pd.read_csv(p, encoding="utf-8-sig")
    except: return None


def render_historico_page(df_current_2026=None, df_atrasos_2026=None, stamp=""):
    st.markdown("""
    <div class="sigma-header"><div>
        <div class="sigma-logo" style="font-size:1.5rem">SIGMA</div>
        <div class="sigma-tagline">Análisis Histórico · 2022 — 2026</div>
    </div></div>""", unsafe_allow_html=True)

    df_mat_r  = _load("hist_matricula_resumen.csv")
    df_atr_r  = _load("hist_atrasos_resumen.csv")
    df_asi_m  = _load("hist_asistencia_mensual.csv")
    df_asi    = _load("hist_asistencia.csv")
    df_obs_m  = _load("hist_observaciones_mensual.csv")
    df_atr    = _load("hist_atrasos.csv")

    if all(x is None for x in [df_mat_r, df_atr_r, df_asi_m]):
        st.markdown('<div class="sigma-alert info"><b>Sin datos históricos.</b> Cárgalos desde el tab "📂 Cargar datos".</div>', unsafe_allow_html=True)
        _render_uploader()
        return

    # Agregar 2026 parcial
    if df_mat_r is not None and df_current_2026 is not None and not df_current_2026.empty:
        row_2026 = {"anio":2026,"total":len(df_current_2026),
                    "activos":int(df_current_2026.get("activo_al_corte", pd.Series([True]*len(df_current_2026))).sum()),
                    "retirados":int(df_current_2026["fecha_retiro"].notna().sum() if "fecha_retiro" in df_current_2026.columns else 0),
                    "extranjeros":0}
        df_mat_r = pd.concat([df_mat_r, pd.DataFrame([row_2026])], ignore_index=True)

    tabs = st.tabs(["📋 Matrícula","⏰ Atrasos","📅 Asistencia","📋 Observaciones","🔍 Desglose personalizado","📂 Cargar datos"])

    # ════ TAB MATRÍCULA ════
    with tabs[0]:
        _tab_matricula(df_mat_r)

    # ════ TAB ATRASOS ════
    with tabs[1]:
        _tab_atrasos(df_atr_r, df_atr)

    # ════ TAB ASISTENCIA ════
    with tabs[2]:
        _tab_asistencia(df_asi_m, df_asi)

    # ════ TAB OBSERVACIONES ════
    with tabs[3]:
        _tab_observaciones(df_obs_m)

    # ════ TAB DESGLOSE PERSONALIZADO ════
    with tabs[4]:
        _tab_desglose(df_asi_m, df_atr, df_obs_m)

    # ════ TAB CARGAR ════
    with tabs[5]:
        _render_uploader()


# ─────────────────────────────────────────────────────────────────────
def _tab_matricula(df_mat_r):
    st.markdown('<div class="section-title">Evolución de matrícula 2022–2026</div>', unsafe_allow_html=True)
    if df_mat_r is None or df_mat_r.empty:
        st.info("Sin datos de matrícula histórica.")
        return

    df_r = df_mat_r.sort_values("anio")
    anio_min, anio_max = int(df_r["anio"].min()), int(df_r["anio"].max())
    total_min = int(df_r[df_r["anio"]==anio_min]["total"].iloc[0])
    total_max = int(df_r[df_r["anio"]==anio_max]["total"].iloc[0])
    caida = total_min - total_max

    k1,k2,k3,k4 = st.columns(4)
    _kpi(k1, f"{total_max:,}", f"Matriculados {anio_max}", "#2563eb")
    _kpi(k2, f"-{caida}", f"Caída desde {anio_min}", "#dc2626", f"-{round(caida/total_min*100,1)}% en {anio_max-anio_min} años")
    _kpi(k3, str(int(df_r["anio"].nunique())), "Años de datos", "#7c3aed", f"{anio_min}–{anio_max}")
    ret_ult = int(df_r[df_r["anio"]==anio_max]["retirados"].iloc[0]) if "retirados" in df_r.columns else 0
    _kpi(k4, str(ret_ult), f"Retirados {anio_max}", "#d97706")
    st.markdown("<br>", unsafe_allow_html=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_r["anio"], y=df_r["total"], mode="lines+markers+text",
        line={"color":"#2563eb","width":3},
        marker={"size":12,"color":[AÑOS_COLOR.get(a,"#2563eb") for a in df_r["anio"]]},
        text=df_r["total"].astype(int), textposition="top center",
        textfont={"size":11,"color":"#e2e8f0"},
        hovertemplate="<b>%{x}</b>: %{y:,} alumnos<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
        font={"color":"#e2e8f0"}, height=280,
        margin={"l":10,"r":10,"t":10,"b":10},
        xaxis={"gridcolor":"#1a2035","dtick":1},
        yaxis={"gridcolor":"#1a2035","range":[1100,1600]},
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})

    cols_show = [c for c in ["anio","total","activos","retirados","extranjeros"] if c in df_r.columns]
    show_pretty_table(df_r[cols_show].rename(columns={"anio":"Año","total":"Total","activos":"Activos","retirados":"Retirados","extranjeros":"Extranjeros"}), max_rows=10, height=220)


# ─────────────────────────────────────────────────────────────────────
def _tab_atrasos(df_atr_r, df_atr):
    st.markdown('<div class="section-title">Evolución de atrasos 2022–2026</div>', unsafe_allow_html=True)
    if df_atr_r is None or df_atr_r.empty:
        st.info("Sin datos de atrasos históricos.")
        return

    df_a = df_atr_r.sort_values("anio")
    max_anio = int(df_a.loc[df_a["eventos"].idxmax(),"anio"])
    max_ev   = int(df_a["eventos"].max())
    ult_ev   = int(df_a.iloc[-1]["eventos"])
    pico     = df_a.iloc[-1].get("pico_hora","—")

    k1,k2,k3,k4 = st.columns(4)
    _kpi(k1, f"{max_ev:,}", f"Pico histórico ({max_anio})", "#dc2626")
    _kpi(k2, f"{ult_ev:,}", f"Año {int(df_a.iloc[-1]['anio'])}", "#d97706")
    _kpi(k3, f"{int(df_a['eventos'].mean()):,}", "Promedio anual", "#7c3aed")
    _kpi(k4, str(pico), "Hora pico", "#2563eb", "bloque de 10 min")
    st.markdown("<br>", unsafe_allow_html=True)

    g1, g2 = st.columns(2)
    with g1:
        fig = go.Figure(go.Bar(
            x=df_a["anio"].astype(str), y=df_a["eventos"],
            marker_color=[AÑOS_COLOR.get(int(a),"#6b7280") for a in df_a["anio"]],
            text=df_a["eventos"].astype(int), textposition="outside",
            textfont={"size":11,"color":"#e2e8f0"},
            hovertemplate="<b>%{x}</b>: %{y:,}<extra></extra>",
        ))
        fig.update_layout(
            paper_bgcolor="#0d1220",plot_bgcolor="#0d1220",font={"color":"#e2e8f0"},height=280,
            margin={"l":10,"r":10,"t":40,"b":10},
            title={"text":"Total atrasos por año","font":{"size":12,"color":"#63b3ed"},"x":0},
            xaxis={"gridcolor":"rgba(0,0,0,0)"},yaxis={"gridcolor":"#1a2035"},showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})

    with g2:
        # Atrasos por mes superpuesto (todos los años)
        if df_atr is not None and not df_atr.empty:
            df_atr["mes"] = pd.to_numeric(df_atr["mes"], errors="coerce")
            df_atr["anio"] = pd.to_numeric(df_atr["anio"], errors="coerce")
            monthly = df_atr.groupby(["anio","mes"])["id_atraso"].count().reset_index()
            fig2 = go.Figure()
            for anio in sorted(monthly["anio"].dropna().unique()):
                sub = monthly[monthly["anio"]==anio].sort_values("mes")
                sub = sub[sub["mes"].between(1,12)]
                fig2.add_trace(go.Scatter(
                    x=sub["mes"].map(MESES), y=sub["id_atraso"],
                    name=str(int(anio)), mode="lines+markers",
                    line={"color":AÑOS_COLOR.get(int(anio),"#6b7280"),"width":2},
                    marker={"size":6},
                    hovertemplate=f"<b>%{{x}}</b> {int(anio)}: %{{y}}<extra></extra>",
                ))
            fig2.update_layout(
                paper_bgcolor="#0d1220",plot_bgcolor="#0d1220",font={"color":"#e2e8f0"},height=280,
                margin={"l":10,"r":10,"t":40,"b":30},
                title={"text":"Atrasos mes a mes por año","font":{"size":12,"color":"#63b3ed"},"x":0},
                xaxis={"gridcolor":"#1a2035"},yaxis={"gridcolor":"#1a2035"},
                legend={"font":{"size":10},"bgcolor":"rgba(0,0,0,0)","orientation":"h","y":-0.2},
            )
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar":False})

    show_pretty_table(df_a.rename(columns={"anio":"Año","eventos":"Atrasos","alumnos_unicos":"Alumnos",
        "justificados":"Justificados","pct_justificados":"% Justif.","pico_hora":"Pico"}),
        max_rows=10, height=200)


# ─────────────────────────────────────────────────────────────────────
def _tab_asistencia(df_asi_m, df_asi):
    st.markdown('<div class="section-title">Comparativa de asistencia 2022–2026</div>', unsafe_allow_html=True)
    if df_asi_m is None or df_asi_m.empty:
        st.info("Sin datos de asistencia histórica.")
        return

    df = df_asi_m.copy()
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce")
    df["mes"]  = pd.to_numeric(df["mes"],  errors="coerce")

    # Resumen anual
    anual = df.groupby("anio").agg(presentes=("presentes","sum"), ausentes=("ausentes","sum")).reset_index()
    anual["pct"] = (anual["presentes"]/(anual["presentes"]+anual["ausentes"])*100).round(1)

    k1,k2,k3,k4 = st.columns(4)
    mejor = anual.loc[anual["pct"].idxmax()]
    peor  = anual.loc[anual["pct"].idxmin()]
    ult   = anual.iloc[-1]
    prom  = round(anual["pct"].mean(),1)
    _kpi(k1, f"{ult['pct']}%", f"Asistencia {int(ult['anio'])}", "#2563eb")
    _kpi(k2, f"{prom}%", "Promedio 4 años", "#7c3aed")
    _kpi(k3, f"{mejor['pct']}%", f"Mejor año ({int(mejor['anio'])})", "#16a34a")
    _kpi(k4, f"{peor['pct']}%", f"Peor año ({int(peor['anio'])})", "#dc2626")
    st.markdown("<br>", unsafe_allow_html=True)

    g1, g2 = st.columns(2)
    with g1:
        # Líneas superpuestas mes a mes
        fig = go.Figure()
        for anio in sorted(df["anio"].dropna().unique()):
            sub = df[df["anio"]==anio].sort_values("mes")
            sub = sub[sub["mes"].between(1,12)]
            fig.add_trace(go.Scatter(
                x=sub["mes"].map(MESES), y=sub["pct_asistencia"],
                name=str(int(anio)), mode="lines+markers",
                line={"color":AÑOS_COLOR.get(int(anio),"#6b7280"),"width":2},
                marker={"size":6},
                hovertemplate=f"<b>%{{x}}</b> {int(anio)}: %{{y:.1f}}%<extra></extra>",
            ))
        fig.add_hline(y=85, line_dash="dot", line_color="#d97706", line_width=1,
            annotation_text="85% umbral", annotation_font={"size":9,"color":"#d97706"})
        fig.update_layout(
            paper_bgcolor="#0d1220",plot_bgcolor="#0d1220",font={"color":"#e2e8f0"},height=300,
            margin={"l":10,"r":10,"t":40,"b":30},
            title={"text":"Asistencia mes a mes — todos los años","font":{"size":12,"color":"#63b3ed"},"x":0},
            xaxis={"gridcolor":"#1a2035"},
            yaxis={"gridcolor":"#1a2035","range":[70,100]},
            legend={"font":{"size":10},"bgcolor":"rgba(0,0,0,0)","orientation":"h","y":-0.2},
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})

    with g2:
        # Barras asistencia anual
        fig2 = go.Figure(go.Bar(
            x=anual["anio"].astype(int).astype(str), y=anual["pct"],
            marker_color=[AÑOS_COLOR.get(int(a),"#6b7280") for a in anual["anio"]],
            text=[f"{v}%" for v in anual["pct"]], textposition="outside",
            textfont={"size":11,"color":"#e2e8f0"},
            hovertemplate="<b>%{x}</b>: %{y:.1f}%<extra></extra>",
        ))
        fig2.add_hline(y=85, line_dash="dot", line_color="#d97706", line_width=1)
        fig2.update_layout(
            paper_bgcolor="#0d1220",plot_bgcolor="#0d1220",font={"color":"#e2e8f0"},height=300,
            margin={"l":10,"r":10,"t":40,"b":10},
            title={"text":"Asistencia anual promedio","font":{"size":12,"color":"#63b3ed"},"x":0},
            xaxis={"gridcolor":"rgba(0,0,0,0)"},
            yaxis={"gridcolor":"#1a2035","range":[80,100]},
            showlegend=False,
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar":False})

    # Por especialidad si tenemos el detalle diario
    if df_asi is not None and not df_asi.empty and "specialty" in df_asi.columns:
        st.markdown('<div class="section-title">Asistencia por especialidad y año</div>', unsafe_allow_html=True)
        df_asi["anio"] = pd.to_numeric(df_asi["anio"], errors="coerce")
        spec_anual = df_asi.groupby(["anio","specialty"]).agg(
            presentes=("presentes","sum"), ausentes=("ausentes","sum")
        ).reset_index()
        spec_anual["pct"] = (spec_anual["presentes"]/(spec_anual["presentes"]+spec_anual["ausentes"])*100).round(1)

        fig3 = go.Figure()
        for spec in ["TELECOM","ELECTRONICA","MECANICA"]:
            sub = spec_anual[spec_anual["specialty"]==spec].sort_values("anio")
            if not sub.empty:
                fig3.add_trace(go.Bar(
                    name=spec, x=sub["anio"].astype(int).astype(str), y=sub["pct"],
                    marker_color=C.get(spec,"#6b7280"),
                    text=[f"{v}%" for v in sub["pct"]], textposition="outside",
                    textfont={"size":9,"color":"#e2e8f0"},
                ))
        fig3.add_hline(y=85, line_dash="dot", line_color="#d97706", line_width=1)
        fig3.update_layout(
            barmode="group",
            paper_bgcolor="#0d1220",plot_bgcolor="#0d1220",font={"color":"#e2e8f0"},height=280,
            margin={"l":10,"r":10,"t":10,"b":10},
            xaxis={"gridcolor":"rgba(0,0,0,0)"},
            yaxis={"gridcolor":"#1a2035","range":[80,100]},
            legend={"font":{"size":10},"bgcolor":"rgba(0,0,0,0)","orientation":"h","y":-0.15},
        )
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar":False})


# ─────────────────────────────────────────────────────────────────────
def _tab_observaciones(df_obs_m):
    st.markdown('<div class="section-title">Evolución de observaciones 2022–2026</div>', unsafe_allow_html=True)
    if df_obs_m is None or df_obs_m.empty:
        st.info("Sin datos de observaciones históricas.")
        return

    df = df_obs_m.copy()
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce")
    df["mes"]  = pd.to_numeric(df["mes"],  errors="coerce")

    anual = df.groupby(["anio","tipo"])["cantidad"].sum().reset_index()
    anual_total = anual.groupby("anio")["cantidad"].sum().reset_index().rename(columns={"cantidad":"total"})

    k1,k2,k3,k4 = st.columns(4)
    neg_anual = anual[anual["tipo"]=="NEG"].set_index("anio")["cantidad"]
    ult_anio = int(anual_total["anio"].max())
    ult_total = int(anual_total[anual_total["anio"]==ult_anio]["total"].iloc[0])
    ult_neg = int(neg_anual.get(ult_anio, 0))
    pct_neg = round(ult_neg/ult_total*100,1) if ult_total else 0
    prom_neg = round(neg_anual.mean(),0)

    _kpi(k1, f"{ult_total:,}", f"Total obs. {ult_anio}", "#7c3aed")
    _kpi(k2, f"{ult_neg:,}", f"Negativas {ult_anio}", "#dc2626", f"{pct_neg}% del total")
    _kpi(k3, f"{int(prom_neg):,}", "Prom. negativas/año", "#d97706")
    peak = int(neg_anual.idxmax()) if not neg_anual.empty else ult_anio
    _kpi(k4, str(peak), "Año con más negativos", "#dc2626", f"{int(neg_anual.get(peak,0)):,} obs.")
    st.markdown("<br>", unsafe_allow_html=True)

    g1, g2 = st.columns(2)
    with g1:
        fig = go.Figure()
        for tipo, color in [("NEG","#dc2626"),("OBS","#6b7280"),("POS","#16a34a")]:
            sub = anual[anual["tipo"]==tipo].sort_values("anio")
            if not sub.empty:
                fig.add_trace(go.Bar(
                    name={"NEG":"Negativas","OBS":"Neutras","POS":"Positivas"}.get(tipo,tipo),
                    x=sub["anio"].astype(int).astype(str), y=sub["cantidad"],
                    marker_color=color,
                    hovertemplate=f"<b>%{{x}}</b> {tipo}: %{{y}}<extra></extra>",
                ))
        fig.update_layout(
            barmode="stack",
            paper_bgcolor="#0d1220",plot_bgcolor="#0d1220",font={"color":"#e2e8f0"},height=300,
            margin={"l":10,"r":10,"t":40,"b":10},
            title={"text":"Observaciones por año y tipo","font":{"size":12,"color":"#63b3ed"},"x":0},
            xaxis={"gridcolor":"rgba(0,0,0,0)"},yaxis={"gridcolor":"#1a2035"},
            legend={"font":{"size":10},"bgcolor":"rgba(0,0,0,0)","orientation":"h","y":-0.15},
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})

    with g2:
        # Mes a mes negativas por año
        neg_mensual = df[df["tipo"]=="NEG"].groupby(["anio","mes"])["cantidad"].sum().reset_index()
        fig2 = go.Figure()
        for anio in sorted(neg_mensual["anio"].dropna().unique()):
            sub = neg_mensual[neg_mensual["anio"]==anio].sort_values("mes")
            sub = sub[sub["mes"].between(1,12)]
            fig2.add_trace(go.Scatter(
                x=sub["mes"].map(MESES), y=sub["cantidad"],
                name=str(int(anio)), mode="lines+markers",
                line={"color":AÑOS_COLOR.get(int(anio),"#6b7280"),"width":2},
                marker={"size":6},
                hovertemplate=f"<b>%{{x}}</b> {int(anio)}: %{{y}}<extra></extra>",
            ))
        fig2.update_layout(
            paper_bgcolor="#0d1220",plot_bgcolor="#0d1220",font={"color":"#e2e8f0"},height=300,
            margin={"l":10,"r":10,"t":40,"b":30},
            title={"text":"Obs. negativas mes a mes","font":{"size":12,"color":"#63b3ed"},"x":0},
            xaxis={"gridcolor":"#1a2035"},yaxis={"gridcolor":"#1a2035"},
            legend={"font":{"size":10},"bgcolor":"rgba(0,0,0,0)","orientation":"h","y":-0.2},
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar":False})


# ─────────────────────────────────────────────────────────────────────
def _tab_desglose(df_asi_m, df_atr, df_obs_m):
    st.markdown('<div class="section-title">Desglose personalizado</div>', unsafe_allow_html=True)
    st.markdown('<div class="sigma-alert info">Filtra por año, rango de meses y módulo para comparar exactamente lo que necesitas.</div>', unsafe_allow_html=True)

    # Controles
    c1, c2, c3 = st.columns(3)
    with c1:
        modulo = st.selectbox("Módulo", ["Asistencia","Atrasos","Observaciones"], key="desg_mod")
    with c2:
        anios_disp = []
        if df_asi_m is not None: anios_disp += list(df_asi_m["anio"].dropna().astype(int).unique())
        if df_atr is not None:   anios_disp += list(df_atr["anio"].dropna().astype(int).unique())
        anios_disp = sorted(set(anios_disp))
        anios_sel = st.multiselect("Años a comparar", anios_disp, default=anios_disp, key="desg_anios")
    with c3:
        mes_ini, mes_fin = st.select_slider(
            "Rango de meses",
            options=list(range(1,13)),
            value=(1, 12),
            format_func=lambda m: MESES[m],
            key="desg_meses",
        )

    if not anios_sel:
        st.warning("Selecciona al menos un año.")
        return

    if modulo == "Asistencia" and df_asi_m is not None:
        df = df_asi_m.copy()
        df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
        df["mes"]  = pd.to_numeric(df["mes"],  errors="coerce").astype("Int64")
        df = df[df["anio"].isin(anios_sel) & df["mes"].between(mes_ini, mes_fin)]

        if df.empty:
            st.info("Sin datos para la selección.")
            return

        monthly = df.groupby(["anio","mes"]).agg(presentes=("presentes","sum"),ausentes=("ausentes","sum")).reset_index()
        monthly["pct"] = (monthly["presentes"]/(monthly["presentes"]+monthly["ausentes"])*100).round(1)

        fig = go.Figure()
        for anio in sorted(monthly["anio"].dropna().unique()):
            sub = monthly[monthly["anio"]==anio].sort_values("mes")
            fig.add_trace(go.Scatter(
                x=sub["mes"].map(MESES), y=sub["pct"], name=str(int(anio)),
                mode="lines+markers",
                line={"color":AÑOS_COLOR.get(int(anio),"#6b7280"),"width":2},
                marker={"size":8},
                hovertemplate=f"<b>%{{x}}</b> {int(anio)}: %{{y:.1f}}%<extra></extra>",
            ))
        fig.add_hline(y=85, line_dash="dot", line_color="#d97706", line_width=1,
            annotation_text="85%", annotation_font={"size":9,"color":"#d97706"})
        fig.update_layout(
            paper_bgcolor="#0d1220",plot_bgcolor="#0d1220",font={"color":"#e2e8f0"},height=350,
            margin={"l":10,"r":10,"t":10,"b":30},
            xaxis={"gridcolor":"#1a2035"},
            yaxis={"gridcolor":"#1a2035","range":[70,100],"title":"% Asistencia"},
            legend={"font":{"size":11},"bgcolor":"rgba(0,0,0,0)","orientation":"h","y":-0.15},
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})

        # Tabla resumen del rango
        resumen = monthly.groupby("anio").agg(
            pct_prom=("pct","mean"),
            mes_mejor=("pct", lambda x: MESES.get(int(monthly.loc[x.idxmax(),"mes"]),"-")),
            mes_peor =("pct", lambda x: MESES.get(int(monthly.loc[x.idxmin(),"mes"]),"-")),
        ).reset_index()
        resumen["pct_prom"] = resumen["pct_prom"].round(1)
        resumen = resumen.rename(columns={"anio":"Año","pct_prom":"% Asistencia prom.","mes_mejor":"Mejor mes","mes_peor":"Peor mes"})
        show_pretty_table(resumen, max_rows=10, height=200)

    elif modulo == "Atrasos" and df_atr is not None:
        df = df_atr.copy()
        df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
        df["mes"]  = pd.to_numeric(df["mes"],  errors="coerce").astype("Int64")
        df = df[df["anio"].isin(anios_sel) & df["mes"].between(mes_ini, mes_fin)]

        if df.empty:
            st.info("Sin datos para la selección.")
            return

        monthly = df.groupby(["anio","mes"])["id_atraso"].count().reset_index().rename(columns={"id_atraso":"atrasos"})
        fig = go.Figure()
        for anio in sorted(monthly["anio"].dropna().unique()):
            sub = monthly[monthly["anio"]==anio].sort_values("mes")
            fig.add_trace(go.Bar(
                name=str(int(anio)), x=sub["mes"].map(MESES), y=sub["atrasos"],
                marker_color=AÑOS_COLOR.get(int(anio),"#6b7280"),
                hovertemplate=f"<b>%{{x}}</b> {int(anio)}: %{{y}}<extra></extra>",
            ))
        fig.update_layout(
            barmode="group",
            paper_bgcolor="#0d1220",plot_bgcolor="#0d1220",font={"color":"#e2e8f0"},height=350,
            margin={"l":10,"r":10,"t":10,"b":30},
            xaxis={"gridcolor":"rgba(0,0,0,0)"},yaxis={"gridcolor":"#1a2035","title":"Atrasos"},
            legend={"font":{"size":11},"bgcolor":"rgba(0,0,0,0)","orientation":"h","y":-0.15},
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})

        resumen = monthly.groupby("anio").agg(total=("atrasos","sum"),pico=("atrasos",lambda x: MESES.get(int(monthly.loc[x.idxmax(),"mes"]),"-"))).reset_index()
        resumen = resumen.rename(columns={"anio":"Año","total":"Total atrasos","pico":"Mes pico"})
        show_pretty_table(resumen, max_rows=10, height=200)

    elif modulo == "Observaciones" and df_obs_m is not None:
        df = df_obs_m.copy()
        df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
        df["mes"]  = pd.to_numeric(df["mes"],  errors="coerce").astype("Int64")
        df = df[df["anio"].isin(anios_sel) & df["mes"].between(mes_ini, mes_fin)]

        if df.empty:
            st.info("Sin datos para la selección.")
            return

        tipo_sel = st.multiselect("Tipo de observación", ["NEG","OBS","POS"],
                                   default=["NEG"], key="desg_tipo")
        df = df[df["tipo"].isin(tipo_sel)]
        monthly = df.groupby(["anio","mes"])["cantidad"].sum().reset_index()

        fig = go.Figure()
        for anio in sorted(monthly["anio"].dropna().unique()):
            sub = monthly[monthly["anio"]==anio].sort_values("mes")
            fig.add_trace(go.Scatter(
                x=sub["mes"].map(MESES), y=sub["cantidad"], name=str(int(anio)),
                mode="lines+markers",
                line={"color":AÑOS_COLOR.get(int(anio),"#6b7280"),"width":2},
                marker={"size":8},
                hovertemplate=f"<b>%{{x}}</b> {int(anio)}: %{{y}}<extra></extra>",
            ))
        fig.update_layout(
            paper_bgcolor="#0d1220",plot_bgcolor="#0d1220",font={"color":"#e2e8f0"},height=350,
            margin={"l":10,"r":10,"t":10,"b":30},
            xaxis={"gridcolor":"#1a2035"},yaxis={"gridcolor":"#1a2035","title":"Observaciones"},
            legend={"font":{"size":11},"bgcolor":"rgba(0,0,0,0)","orientation":"h","y":-0.15},
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})


# ─────────────────────────────────────────────────────────────────────
def _render_uploader():
    st.markdown('<div class="section-title">Cargar datos históricos</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="sigma-alert info">
        Sube el ZIP con las carpetas <code>2022/</code>, <code>2023/</code>, <code>2024/</code>, <code>2025/</code>,
        cada una con los CSV de matrícula, atrasos, asistencia y observaciones exportados desde Syscol.
    </div>""", unsafe_allow_html=True)

    uploaded = st.file_uploader("ZIP histórico de Syscol", type=["zip"], key="hist_uploader")
    if uploaded is not None:
        import zipfile, tempfile, os
        with st.spinner("Procesando datos históricos..."):
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    zip_path = Path(tmpdir) / "hist.zip"
                    zip_path.write_bytes(uploaded.read())
                    with zipfile.ZipFile(zip_path) as zf:
                        zf.extractall(tmpdir)
                    hist_root = None
                    for p in Path(tmpdir).rglob("2022"):
                        if p.is_dir():
                            hist_root = p.parent
                            break
                    if hist_root is None:
                        st.error("No se encontró estructura de carpetas 2022/, 2023/, etc.")
                    else:
                        # Forzar recarga del módulo para evitar __pycache__ desactualizado
                        import importlib, sys
                        if "src.staging.build_historico" in sys.modules:
                            del sys.modules["src.staging.build_historico"]
                        from src.staging.build_historico import run as run_hist
                        r = run_hist(hist_dir=hist_root, gold_dir=GOLD_HIST)
                        n_mat = len(r["matricula"])
                        n_atr = len(r["atrasos"])
                        n_asi = len(r.get("asistencia", pd.DataFrame()))
                        n_obs = len(r.get("observaciones", pd.DataFrame()))
                        # Verificar archivos generados directamente en disco
                        archivos_ok = []
                        archivos_faltantes = []
                        for nombre_archivo in ["hist_matricula.csv","hist_atrasos.csv","hist_asistencia_mensual.csv","hist_observaciones_mensual.csv"]:
                            if (GOLD_HIST / nombre_archivo).exists():
                                archivos_ok.append(nombre_archivo)
                            else:
                                archivos_faltantes.append(nombre_archivo)

                        if archivos_faltantes:
                            st.warning(f"⚠️ Archivos faltantes: {archivos_faltantes}. Intenta reinstalar build_historico.py")
                        st.success(f"✅ Archivos generados: {', '.join(archivos_ok)}")
                        st.cache_data.clear()
                        st.rerun()
            except Exception as e:
                import traceback
                st.error(f"Error: {e}\n{traceback.format_exc()}")