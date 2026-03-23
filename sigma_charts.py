"""
SIGMA — Módulo de Gráficos Interactivos
9 gráficos, cada uno con un mensaje único y explicación contextual.

Uso: from sigma_charts import *
"""
from __future__ import annotations
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

# ── Paleta SIGMA ──────────────────────────────────────────────────────
SPEC_COLORS = {
    "TELECOM":     "#2563eb",
    "ELECTRONICA": "#16a34a",
    "MECANICA":    "#d97706",
    "COMUN":       "#7c3aed",
}
C_CYAN   = "#2563eb"
C_GREEN  = "#16a34a"
C_AMBER  = "#d97706"
C_RED    = "#dc2626"
C_PURPLE = "#7c3aed"
C_MUTED  = "#4a5568"
PALETTE  = [C_CYAN, C_GREEN, C_AMBER, C_RED, C_PURPLE, "#0891b2", "#be185d"]

def _hex_rgba(hex_color: str, alpha: float = 0.2) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

def _norm_sexo(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.upper().str.strip()
    return s.map(lambda v: "M" if v in ("M","MASCULINO") else ("F" if v in ("F","FEMENINO") else ""))

def _is_ext(series: pd.Series) -> pd.Series:
    return ~series.fillna("CHILENA").astype(str).str.upper().str.strip().isin(
        ["CHILENA","CHILENO","CHILE","NAN",""])

_BASE = dict(
    paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
    font=dict(family="Inter, Helvetica, Arial, sans-serif", color="#e2e8f0"),
    margin=dict(l=16, r=16, t=48, b=16),
    legend=dict(bgcolor="#0d1220", bordercolor="#1a2035", borderwidth=0,
                font=dict(size=11, color="#a0aec0")),
    xaxis=dict(gridcolor="#1a2035", zerolinecolor="#1a2035",
               tickfont=dict(size=11, color="#a0aec0"), linecolor="#1a2035"),
    yaxis=dict(gridcolor="#1a2035", zerolinecolor="#1a2035",
               tickfont=dict(size=11, color="#a0aec0"), linecolor="#1a2035"),
)

def _apply(fig: go.Figure, title: str = "", height: int = 320) -> go.Figure:
    fig.update_layout(**_BASE,
                      title=dict(text=title, font=dict(size=12, color="#63b3ed"), x=0, y=0.97),
                      height=height)
    return fig

def _insight(texto: str) -> str:
    return (f'<div style="background:#080c14;border-left:3px solid #2563eb;'
            f'border-radius:0 6px 6px 0;padding:8px 14px;margin-top:4px;'
            f'font-size:0.78rem;color:#a0aec0;line-height:1.5">{texto}</div>')



# ══════════════════════════════════════════════════════════════════════
# DASHBOARD — 2 gráficos
# ══════════════════════════════════════════════════════════════════════

def chart_dash_genero(matriculados_h: int, matriculados_m: int):
    total = matriculados_h + matriculados_m or 1
    pct_h = round(matriculados_h / total * 100, 1)
    pct_f = round(matriculados_m / total * 100, 1)
    fig = go.Figure(go.Pie(
        labels=["Hombres", "Mujeres"], values=[matriculados_h, matriculados_m],
        hole=0.62,
        marker=dict(colors=[C_CYAN, C_GREEN], line=dict(color="#0d1220", width=3)),
        textinfo="percent", textfont=dict(size=12, color="white"),
        hovertemplate="<b>%{label}</b><br>%{value:,} alumnos — %{percent}<extra></extra>",
        domain=dict(x=[0.0, 0.72]),
    ))
    fig.add_annotation(text=f"<b>{total:,}</b><br>alumnos",
                       x=0.36, y=0.5, showarrow=False,
                       font=dict(size=15, color="#e2e8f0"), align="center")
    fig.update_layout(legend=dict(x=0.76, y=0.5, xanchor="left", yanchor="middle"),
                      margin=dict(l=8, r=8, t=48, b=8))
    _apply(fig, "Composición global H / M", 300)
    if pct_h > 75:
        msg = f"El <b>{pct_h}%</b> de la matrícula son hombres — alta masculinización típica de especialidades técnico-industriales."
    elif pct_f > 40:
        msg = f"Distribución relativamente equilibrada: <b>{pct_h}%</b> H / <b>{pct_f}%</b> M."
    else:
        msg = f"<b>{pct_h}%</b> hombres y <b>{pct_f}%</b> mujeres sobre {total:,} alumnos."
    return fig, _insight(msg)


def chart_dash_nivel(df_current):
    if df_current is None or df_current.empty:
        return go.Figure(), ""
    df = df_current.copy()
    df["level"] = pd.to_numeric(df.get("level", 0), errors="coerce").fillna(0).astype(int)
    df["_sx"] = _norm_sexo(df.get("sexo", pd.Series(dtype=str)))
    grp = df[df["level"] > 0].groupby(["level", "_sx"]).size().reset_index(name="n")
    niveles = sorted(grp["level"].unique())
    fig = go.Figure()
    for sexo, color, nombre in [("M", C_CYAN, "Hombres"), ("F", C_GREEN, "Mujeres")]:
        d = grp[grp["_sx"] == sexo]
        fig.add_trace(go.Bar(name=nombre, x=d["level"], y=d["n"], marker_color=color,
                             text=d["n"], textposition="inside",
                             textfont=dict(size=11, color="white"),
                             hovertemplate=f"<b>{nombre}</b> — %{{x}}° Medio: %{{y}}<extra></extra>"))
    totales = grp.groupby("level")["n"].sum()
    for niv, tot in totales.items():
        fig.add_annotation(x=niv, y=tot + 8, text=f"<b>{tot}</b>",
                           showarrow=False, font=dict(size=11, color="#e2e8f0"))
    fig.update_layout(barmode="stack",
                      xaxis=dict(tickvals=niveles, ticktext=[f"{v}° Medio" for v in niveles],
                                 tickfont=dict(size=11, color="#a0aec0"), gridcolor="#1a2035"),
                      yaxis=dict(gridcolor="#1a2035", tickfont=dict(color="#a0aec0")),
                      legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
                      margin=dict(l=16, r=16, t=48, b=32))
    _apply(fig, "Matrícula por nivel", 300)
    if totales.empty:
        return fig, _insight("Sin datos de matrícula por nivel para este corte.")
    nivel_max = totales.idxmax()
    nivel_min = totales.idxmin()
    msg = (f"El <b>{nivel_max}° Medio</b> concentra más alumnos ({totales[nivel_max]:,}). "
           f"El <b>{nivel_min}° Medio</b> es el de menor matrícula ({totales[nivel_min]:,}) — "
           f"una reducción progresiva entre niveles puede reflejar deserción acumulada.")
    return fig, _insight(msg)


# ══════════════════════════════════════════════════════════════════════
# ESPECIALIDADES — 3 gráficos
# ══════════════════════════════════════════════════════════════════════

def chart_specs_treemap(df_current):
    if df_current is None or df_current.empty:
        return go.Figure(), ""
    df = df_current.copy()
    df["specialty"] = df.get("specialty", pd.Series(dtype=str)).fillna("SIN DATOS").str.upper().str.strip()
    df["course_code"] = df.get("course_code", pd.Series(dtype=str)).fillna("").str.upper()
    grp = (df[df["specialty"] != "SIN DATOS"]
           .groupby(["specialty", "course_code"]).size().reset_index(name="n"))
    fig = px.treemap(grp, path=["specialty", "course_code"], values="n",
                     color="specialty", color_discrete_map=SPEC_COLORS, custom_data=["n"])
    fig.update_traces(textinfo="label+value", textfont=dict(size=12),
                      hovertemplate="<b>%{label}</b><br>%{customdata[0]} alumnos<extra></extra>",
                      marker=dict(line=dict(width=2, color="#0d1220")))
    _apply(fig, "Distribución por especialidad y curso", 360)
    max_row = grp.loc[grp["n"].idxmax()]
    min_row = grp.loc[grp["n"].idxmin()]
    msg = (f"El curso más grande es <b>{max_row['course_code']}</b> ({max_row['specialty']}, {max_row['n']} alumnos). "
           f"El más pequeño es <b>{min_row['course_code']}</b> ({min_row['specialty']}, {min_row['n']} alumnos). "
           f"Diferencias grandes entre cursos de la misma especialidad pueden indicar abandono entre niveles.")
    return fig, _insight(msg)


def chart_specs_heatmap(df_current):
    """Heatmap Plotly de indicadores de contexto por especialidad."""
    import numpy as np
    if df_current is None or df_current.empty:
        fig = go.Figure()
        return fig, ""
    df = df_current.copy()
    df["specialty"] = df.get("specialty", pd.Series(dtype=str)).fillna("SIN DATOS").str.upper().str.strip()
    df["_sx"] = _norm_sexo(df.get("sexo", pd.Series(dtype=str)))
    df["is_repeat"] = df.get("is_repeat", pd.Series(dtype=bool)).fillna(False).astype(bool)
    df["is_ext"] = _is_ext(df.get("nacionalidad", pd.Series(dtype=str)))
    specs = sorted([s for s in df["specialty"].unique() if s != "SIN DATOS"])
    if not specs:
        return go.Figure(), ""

    indicadores = ["% Mujeres", "% Repitentes", "% Extranjeros"]
    data = []
    for sp in specs:
        d = df[df["specialty"] == sp]
        n = len(d) or 1
        data.append([
            round((d["_sx"] == "F").sum() / n * 100, 1),
            round(d["is_repeat"].sum() / n * 100, 1),
            round(d["is_ext"].sum() / n * 100, 1),
        ])

    z = np.array(data)
    text = [[f"{v:.1f}%" for v in row] for row in z]

    fig = go.Figure(data=go.Heatmap(
        z=z, x=indicadores, y=specs,
        text=text, texttemplate="%{text}",
        colorscale=[[0, "#dbeafe"], [0.5, "#2563eb"], [1, "#1e3a5f"]],
        showscale=False,
    ))
    fig.update_layout(
        paper_bgcolor="#0d1220", plot_bgcolor="#0d1220",
        font=dict(color="#e2e8f0"),
        height=220, margin=dict(l=10, r=10, t=40, b=10),
        title=dict(text="Indicadores de contexto por especialidad", font=dict(size=12, color="#63b3ed"), x=0),
    )
    sp_ext = max(specs, key=lambda s: data[specs.index(s)][2])
    msg = f"<b>{sp_ext}</b> concentra el mayor % de alumnos extranjeros ({data[specs.index(sp_ext)][2]:.1f}%)."
    return fig, f'<p style="font-size:0.78rem;color:#94a3b8">{msg}</p>'


def chart_demo_edad(df_current):
    if df_current is None or df_current.empty or "edad" not in df_current.columns:
        return go.Figure(), ""
    edades = pd.to_numeric(df_current["edad"], errors="coerce").dropna()
    edades = edades[(edades >= 12) & (edades <= 26)]
    prom = edades.mean()
    sobreedad = int((edades > 19).sum())
    pct_sobre = round(sobreedad / len(edades) * 100, 1) if len(edades) > 0 else 0
    fig = go.Figure(go.Histogram(
        x=edades, nbinsx=15, marker_color=C_CYAN,
        marker_line_color="#0d1220", marker_line_width=1.5, opacity=0.9,
        hovertemplate="Edad %{x}: %{y} alumnos<extra></extra>", name="",
    ))
    fig.add_vline(x=prom, line_dash="dash", line_color=C_AMBER,
                  annotation_text=f"Promedio {prom:.1f} años",
                  annotation_font=dict(color=C_AMBER, size=10),
                  annotation_position="top right")
    fig.add_vrect(x0=20, x1=26, fillcolor=_hex_rgba(C_RED, 0.08), line_width=0,
                  annotation_text="Sobreedad", annotation_position="top left",
                  annotation_font=dict(color="#fc8181", size=9))
    fig.update_layout(xaxis=dict(title="Edad", gridcolor="#1a2035", tickfont=dict(color="#a0aec0")),
                      yaxis=dict(title="Cantidad de alumnos", gridcolor="#1a2035", tickfont=dict(color="#a0aec0")),
                      showlegend=False, margin=dict(l=16, r=16, t=48, b=16))
    _apply(fig, "Distribución etaria de la matrícula", 320)
    if pct_sobre > 10:
        msg = (f"Promedio de <b>{prom:.1f} años</b>. El <b>{pct_sobre}%</b> ({sobreedad} alumnos) "
               f"presenta sobreedad (zona roja). La sobreedad es uno de los predictores más robustos de deserción escolar.")
    else:
        msg = (f"Distribución concentrada alrededor de <b>{prom:.1f} años</b>, dentro del rango esperado. "
               f"Solo el {pct_sobre}% presenta sobreedad — matrícula relativamente homogénea en edad.")
    return fig, _insight(msg)


def chart_demo_comunas(df_comunas):
    if df_comunas is None or df_comunas.empty:
        return go.Figure(), ""
    df = df_comunas.copy()
    df["nombre"] = df["comuna"].astype(str).str.title()
    df["count"] = df["count"].astype(int)
    df = df[df["count"] > 0]
    fig = px.treemap(df, path=["nombre"], values="count",
                     color="count",
                     color_continuous_scale=[[0,"#0f172a"],[0.4,"#1e3a5f"],[0.75,"#2563eb"],[1.0,"#93c5fd"]],
                     custom_data=["count", "pct"])
    fig.update_traces(textinfo="label+value", textfont=dict(size=12),
                      hovertemplate="<b>%{label}</b><br>%{customdata[0]} alumnos (%{customdata[1]:.1f}%)<extra></extra>",
                      marker=dict(line=dict(width=2, color="#0d1220")))
    fig.update_coloraxes(showscale=False)
    _apply(fig, "Procedencia por comuna", 360)
    top = df.nlargest(1, "count").iloc[0]
    top3_pct = df.nlargest(3, "count")["count"].sum() / df["count"].sum() * 100
    msg = (f"<b>{top['nombre']}</b> aporta la mayor cantidad de alumnos ({top['count']:,}). "
           f"Las 3 comunas principales concentran el <b>{top3_pct:.1f}%</b> de la matrícula. "
           f"Alta concentración territorial puede indicar zona de influencia acotada o dependencia de transporte.")
    return fig, _insight(msg)