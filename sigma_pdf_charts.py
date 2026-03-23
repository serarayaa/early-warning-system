"""
SIGMA — Gráficos para PDF (matplotlib, estilo impresión)
Cada función retorna (img_bytes, texto_explicativo).
Paleta ejecutiva: fondo blanco, acentos azul navy.
"""
from __future__ import annotations
import io
import textwrap
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

# ── Paleta ejecutiva (impresión) ──────────────────────────────────────
C_NAVY   = "#1e3a5f"
C_BLUE   = "#2563eb"
C_GREEN  = "#16a34a"
C_AMBER  = "#d97706"
C_RED    = "#dc2626"
C_PURPLE = "#7c3aed"
C_GRAY   = "#6b7280"
C_LGRAY  = "#e5e7eb"
C_TEXT   = "#111827"

SPEC_COLORS = {
    "TELECOM":     C_BLUE,
    "ELECTRONICA": C_GREEN,
    "MECANICA":    C_AMBER,
    "COMUN":       C_PURPLE,
}

def _norm_sexo(series):
    s = series.astype(str).str.upper().str.strip()
    return s.map(lambda v: "M" if v in ("M","MASCULINO") else ("F" if v in ("F","FEMENINO") else ""))

def _is_ext(series):
    return ~series.fillna("CHILENA").astype(str).str.upper().str.strip().isin(
        ["CHILENA","CHILENO","CHILE","NAN",""])

def _fig_to_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()

def _base_fig(w=14, h=4):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(C_LGRAY)
    ax.spines["bottom"].set_color(C_LGRAY)
    ax.tick_params(colors=C_GRAY, labelsize=9)
    ax.yaxis.label.set_color(C_GRAY)
    ax.xaxis.label.set_color(C_GRAY)
    return fig, ax

def _wrap(text: str, width=110) -> str:
    return "\n".join(textwrap.wrap(text, width))

# ══════════════════════════════════════════════════════════════════════
# EJECUTIVO — 2 gráficos
# ══════════════════════════════════════════════════════════════════════

def pdf_chart_genero_nivel(df_current: pd.DataFrame) -> tuple[bytes, str]:
    """Barras apiladas H/M por nivel — para PDF ejecutivo."""
    if df_current is None or df_current.empty:
        return b"", ""
    df = df_current.copy()
    df["level"] = pd.to_numeric(df.get("level", 0), errors="coerce").fillna(0).astype(int)
    df["_sx"] = _norm_sexo(df.get("sexo", pd.Series(dtype=str)))
    niveles = sorted([n for n in df["level"].unique() if n > 0])
    h_vals = [int((df[df["level"]==n]["_sx"]=="M").sum()) for n in niveles]
    m_vals = [int((df[df["level"]==n]["_sx"]=="F").sum()) for n in niveles]
    totales = [h+m for h,m in zip(h_vals, m_vals)]
    labels = [f"{n}° Medio" for n in niveles]

    fig, ax = _base_fig(10, 4)
    x = range(len(niveles))
    bars_h = ax.bar(x, h_vals, color=C_BLUE, label="Hombres", zorder=3)
    bars_m = ax.bar(x, m_vals, bottom=h_vals, color=C_GREEN, label="Mujeres", zorder=3)

    for i, (hv, mv, tot) in enumerate(zip(h_vals, m_vals, totales)):
        if hv > 15: ax.text(i, hv/2, str(hv), ha="center", va="center",
                            fontsize=9, color="white", fontweight="bold")
        if mv > 15: ax.text(i, hv + mv/2, str(mv), ha="center", va="center",
                            fontsize=9, color="white", fontweight="bold")
        ax.text(i, tot + 4, str(tot), ha="center", va="bottom",
                fontsize=9, color=C_TEXT, fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Alumnos", fontsize=9, color=C_GRAY)
    ax.yaxis.grid(True, color=C_LGRAY, linestyle="--", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(fontsize=9, framealpha=0, labelcolor=C_TEXT)
    ax.set_title("Matrícula por nivel y género", fontsize=11, color=C_NAVY,
                 fontweight="bold", pad=10, loc="left")

    if not niveles or sum(totales) == 0:
        plt.close(fig)
        return b"", ""
    nivel_max = niveles[totales.index(max(totales))]
    nivel_min = niveles[totales.index(min(totales))]
    pct_m_total = round(sum(m_vals) / sum(totales) * 100, 1)
    texto = (
        f"La matrícula está distribuida en {len(niveles)} niveles. "
        f"El {nivel_max}° Medio concentra la mayor cantidad de alumnos ({max(totales):,}), "
        f"mientras que el {nivel_min}° Medio registra la menor ({min(totales):,}). "
        f"Una reducción progresiva entre niveles puede reflejar deserción acumulada. "
        f"El {pct_m_total}% de la matrícula total corresponde a mujeres."
    )
    return _fig_to_bytes(fig), _wrap(texto)


def pdf_chart_especialidad_resumen(df_current: pd.DataFrame) -> tuple[bytes, str]:
    """Barras horizontales de matrícula por especialidad."""
    if df_current is None or df_current.empty:
        return b"", ""
    df = df_current.copy()
    df["specialty"] = df.get("specialty", pd.Series(dtype=str)).fillna("SIN DATOS").str.upper().str.strip()
    specs = sorted([s for s in df["specialty"].unique() if s != "SIN DATOS"])
    if not specs:
        return b"", ""
    totales = [int((df["specialty"] == sp).sum()) for sp in specs]
    total_general = sum(totales) or 1

    colors = [SPEC_COLORS.get(sp, C_GRAY) for sp in specs]
    fig, ax = _base_fig(10, 3.5)
    y = range(len(specs))
    ax.barh(list(y), totales, color=colors, height=0.5, zorder=3)
    for i, (sp, tot) in enumerate(zip(specs, totales)):
        pct = round(tot / total_general * 100, 1)
        ax.text(tot + 5, i, f"{tot:,}  ({pct}%)", va="center", fontsize=10,
                color=C_TEXT, fontweight="bold")
    ax.set_yticks(list(y))
    ax.set_yticklabels(specs, fontsize=10, color=C_TEXT, fontweight="bold")
    ax.set_xlabel("Alumnos matriculados", fontsize=9, color=C_GRAY)
    ax.xaxis.grid(True, color=C_LGRAY, linestyle="--", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.set_title("Matrícula por especialidad",
                 fontsize=11, color=C_NAVY, fontweight="bold", pad=10, loc="left")

    sp_max = specs[totales.index(max(totales))]
    sp_min = specs[totales.index(min(totales))]
    pct_max = round(max(totales) / total_general * 100, 1)
    pct_min = round(min(totales) / total_general * 100, 1)
    texto = (
        f"{sp_max} es la especialidad más grande con {max(totales):,} alumnos ({pct_max}% del total), "
        f"seguida por {', '.join([s for s in specs if s != sp_max])}. "
        f"{sp_min} es la de menor matrícula ({min(totales):,} alumnos, {pct_min}%)."
    )
    return _fig_to_bytes(fig), _wrap(texto)


# ══════════════════════════════════════════════════════════════════════
# ESPECIALIDADES — 2 gráficos
# ══════════════════════════════════════════════════════════════════════

def pdf_chart_heatmap(df_current: pd.DataFrame) -> tuple[bytes, str]:
    """Heatmap de indicadores de contexto por especialidad (3 indicadores)."""
    if df_current is None or df_current.empty:
        return b"", ""
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap

    df = df_current.copy()
    df["specialty"] = df.get("specialty", pd.Series(dtype=str)).fillna("SIN DATOS").str.upper().str.strip()
    df["_sx"] = _norm_sexo(df.get("sexo", pd.Series(dtype=str)))
    df["is_repeat"] = df.get("is_repeat", pd.Series(dtype=bool)).fillna(False).astype(bool)
    df["is_ext"] = _is_ext(df.get("nacionalidad", pd.Series(dtype=str)))
    specs = sorted([s for s in df["specialty"].unique() if s != "SIN DATOS"])

    if not specs:
        return b"", ""

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
    z_max = z.max() if z.max() > 0 else 1

    fig, ax = plt.subplots(figsize=(9, 2.8))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    cmap = LinearSegmentedColormap.from_list("sigma", ["#dbeafe", "#2563eb", "#1e3a5f"])
    ax.imshow(z, aspect="auto", cmap=cmap, vmin=0)
    ax.set_xticks(range(len(indicadores)))
    ax.set_xticklabels(indicadores, fontsize=10)
    ax.set_yticks(range(len(specs)))
    ax.set_yticklabels(specs, fontsize=10, fontweight="bold")
    ax.tick_params(top=False, bottom=True, labeltop=False, labelbottom=True)
    for i in range(len(specs)):
        for j in range(len(indicadores)):
            val = z[i, j]
            color = "white" if val > (z_max * 0.5) else C_TEXT
            ax.text(j, i, f"{val:.1f}%", ha="center", va="center",
                    fontsize=11, color=color, fontweight="bold")
    ax.spines[:].set_visible(False)
    ax.set_title("Indicadores de contexto por especialidad (%)",
                 fontsize=11, color=C_NAVY, fontweight="bold", pad=10, loc="left")
    fig.tight_layout()

    sp_ext = max(specs, key=lambda s: data[specs.index(s)][2])
    sp_rep = max(specs, key=lambda s: data[specs.index(s)][1])
    sp_muj = max(specs, key=lambda s: data[specs.index(s)][0])
    texto = (
        f"El heatmap compara 3 indicadores de contexto entre especialidades. "
        f"Celdas más oscuras indican valores más altos. "
        f"{sp_ext} concentra el mayor porcentaje de alumnos extranjeros "
        f"({data[specs.index(sp_ext)][2]:.1f}%), grupo que requiere seguimiento diferenciado. "
        f"{sp_rep} presenta la mayor proporción de repitentes ({data[specs.index(sp_rep)][1]:.1f}%). "
        f"{sp_muj} tiene la mayor presencia femenina ({data[specs.index(sp_muj)][0]:.1f}%)."
    )
    return _fig_to_bytes(fig), _wrap(texto)


def pdf_chart_cursos(df_current: pd.DataFrame) -> tuple[bytes, str]:
    """Barras apiladas por curso, agrupadas por especialidad."""
    if df_current is None or df_current.empty:
        return b"", ""
    df = df_current.copy()
    df["specialty"] = df.get("specialty", pd.Series(dtype=str)).fillna("SIN DATOS").str.upper().str.strip()
    df["course_code"] = df.get("course_code", pd.Series(dtype=str)).fillna("").str.upper()
    df["_sx"] = _norm_sexo(df.get("sexo", pd.Series(dtype=str)))
    grp = (df[df["specialty"]!="SIN DATOS"]
           .groupby(["course_code","specialty"])
           .agg(H=("_sx", lambda x: (x=="M").sum()),
                M=("_sx", lambda x: (x=="F").sum()))
           .reset_index().sort_values(["specialty","course_code"]))

    fig, ax = _base_fig(14, 4)
    x = range(len(grp))
    ax.bar(list(x), grp["H"], color=[SPEC_COLORS.get(s, C_GRAY) for s in grp["specialty"]],
           label="Hombres", zorder=3, alpha=0.9)
    ax.bar(list(x), grp["M"], bottom=grp["H"],
           color=[SPEC_COLORS.get(s, C_GRAY) for s in grp["specialty"]],
           label="Mujeres", zorder=3, alpha=0.5)
    totales = grp["H"] + grp["M"]
    for i, tot in enumerate(totales):
        ax.text(i, tot+1, str(tot), ha="center", va="bottom", fontsize=7, color=C_TEXT)

    ax.set_xticks(list(x))
    ax.set_xticklabels(grp["course_code"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Alumnos", fontsize=9, color=C_GRAY)
    ax.yaxis.grid(True, color=C_LGRAY, linestyle="--", linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.set_title("Matrícula por curso (color = especialidad)",
                 fontsize=11, color=C_NAVY, fontweight="bold", pad=10, loc="left")
    handles = [mpatches.Patch(color=c, label=s) for s,c in SPEC_COLORS.items()
               if s in grp["specialty"].values]
    ax.legend(handles=handles, fontsize=8, framealpha=0, labelcolor=C_TEXT, ncol=len(handles))

    max_row = grp.loc[(grp["H"]+grp["M"]).idxmax()]
    min_row = grp.loc[(grp["H"]+grp["M"]).idxmin()]
    texto = (
        f"El gráfico muestra los {len(grp)} cursos activos agrupados por especialidad (color). "
        f"El curso más grande es {max_row['course_code']} ({max_row['specialty']}, "
        f"{int(max_row['H']+max_row['M'])} alumnos) y el más pequeño "
        f"{min_row['course_code']} ({min_row['specialty']}, "
        f"{int(min_row['H']+min_row['M'])} alumnos). "
        f"Diferencias marcadas entre cursos de la misma especialidad y nivel "
        f"pueden indicar deserción entre años."
    )
    return _fig_to_bytes(fig), _wrap(texto)