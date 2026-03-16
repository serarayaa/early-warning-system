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

    nivel_max = niveles[totales.index(max(totales))]
    nivel_min = niveles[totales.index(min(totales))]
    pct_m_total = round(sum(m_vals)/sum(totales)*100, 1)
    texto = (
        f"La matrícula está distribuida en {len(niveles)} niveles. "
        f"El {nivel_max}° Medio concentra la mayor cantidad de alumnos ({max(totales):,}), "
        f"mientras que el {nivel_min}° Medio registra la menor ({min(totales):,}). "
        f"Una reducción progresiva entre niveles puede reflejar deserción acumulada. "
        f"El {pct_m_total}% de la matrícula total corresponde a mujeres."
    )
    return _fig_to_bytes(fig), _wrap(texto)


def pdf_chart_especialidad_resumen(df_current: pd.DataFrame,
                                    df_desiste: pd.DataFrame = None) -> tuple[bytes, str]:
    """Barras horizontales por especialidad con tasa de desistimiento superpuesta."""
    if df_current is None or df_current.empty:
        return b"", ""
    df = df_current.copy()
    df["specialty"] = df.get("specialty", pd.Series(dtype=str)).fillna("SIN DATOS").str.upper().str.strip()
    specs = sorted([s for s in df["specialty"].unique() if s != "SIN DATOS"])
    totales = [int((df["specialty"]==sp).sum()) for sp in specs]

    des_map = {}
    if df_desiste is not None and not df_desiste.empty:
        dd = df_desiste.copy()
        dd["specialty"] = dd.get("specialty", pd.Series(dtype=str)).fillna("").str.upper().str.strip()
        for sp in specs:
            n_mat = int((df["specialty"]==sp).sum())
            n_des = int((dd["specialty"]==sp).sum())
            des_map[sp] = round(n_des/(n_mat+n_des)*100, 1) if (n_mat+n_des) > 0 else 0

    colors = [SPEC_COLORS.get(sp, C_GRAY) for sp in specs]
    fig, ax = _base_fig(10, 3.5)
    y = range(len(specs))
    bars = ax.barh(list(y), totales, color=colors, height=0.5, zorder=3)
    for i, (sp, tot) in enumerate(zip(specs, totales)):
        ax.text(tot + 5, i, f"{tot:,}", va="center", fontsize=10,
                color=C_TEXT, fontweight="bold")
        if sp in des_map:
            ax.text(tot/2, i, f"Des: {des_map[sp]}%", va="center", ha="center",
                    fontsize=8, color="white", fontweight="bold")
    ax.set_yticks(list(y))
    ax.set_yticklabels(specs, fontsize=10, color=C_TEXT, fontweight="bold")
    ax.set_xlabel("Alumnos matriculados", fontsize=9, color=C_GRAY)
    ax.xaxis.grid(True, color=C_LGRAY, linestyle="--", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.set_title("Matrícula y tasa de desistimiento por especialidad",
                 fontsize=11, color=C_NAVY, fontweight="bold", pad=10, loc="left")

    sp_max = specs[totales.index(max(totales))]
    sp_min = specs[totales.index(min(totales))]
    sp_des = max(des_map, key=des_map.get) if des_map else "—"
    texto = (
        f"{sp_max} es la especialidad más grande con {max(totales):,} alumnos, "
        f"seguida por {', '.join([s for s in specs if s != sp_max])}. "
        f"{sp_min} es la de menor matrícula ({min(totales):,} alumnos). "
        + (f"En términos de retención, {sp_des} registra la mayor tasa de desistimiento "
           f"({des_map[sp_des]}%), lo que requiere atención prioritaria." if des_map else "")
    )
    return _fig_to_bytes(fig), _wrap(texto)


# ══════════════════════════════════════════════════════════════════════
# ESPECIALIDADES — 2 gráficos
# ══════════════════════════════════════════════════════════════════════

def pdf_chart_heatmap(df_current: pd.DataFrame,
                      df_desiste: pd.DataFrame = None) -> tuple[bytes, str]:
    """Heatmap de indicadores de contexto por especialidad."""
    if df_current is None or df_current.empty:
        return b"", ""
    df = df_current.copy()
    df["specialty"] = df.get("specialty", pd.Series(dtype=str)).fillna("SIN DATOS").str.upper().str.strip()
    df["_sx"] = _norm_sexo(df.get("sexo", pd.Series(dtype=str)))
    df["is_repeat"] = df.get("is_repeat", pd.Series(dtype=bool)).fillna(False).astype(bool)
    df["is_ext"] = _is_ext(df.get("nacionalidad", pd.Series(dtype=str)))
    specs = sorted([s for s in df["specialty"].unique() if s != "SIN DATOS"])

    des_map = {}
    if df_desiste is not None and not df_desiste.empty:
        dd = df_desiste.copy()
        dd["specialty"] = dd.get("specialty", pd.Series(dtype=str)).fillna("").str.upper().str.strip()
        for sp in specs:
            n_mat = int((df["specialty"]==sp).sum())
            n_des = int((dd["specialty"]==sp).sum())
            des_map[sp] = round(n_des/(n_mat+n_des)*100,1) if (n_mat+n_des)>0 else 0

    indicadores = ["% Mujeres", "% Repitentes", "% Extranjeros", "% Desistimiento"]
    data = []
    for sp in specs:
        d = df[df["specialty"]==sp]; n = len(d) or 1
        data.append([round((d["_sx"]=="F").sum()/n*100,1),
                     round(d["is_repeat"].sum()/n*100,1),
                     round(d["is_ext"].sum()/n*100,1),
                     des_map.get(sp, 0)])
    import numpy as np
    z = np.array(data)

    fig, ax = plt.subplots(figsize=(10, 2.8))
    fig.patch.set_facecolor("white"); ax.set_facecolor("white")
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("sigma", ["#dbeafe","#2563eb","#1e3a5f"])
    im = ax.imshow(z, aspect="auto", cmap=cmap, vmin=0)
    ax.set_xticks(range(len(indicadores))); ax.set_xticklabels(indicadores, fontsize=10)
    ax.set_yticks(range(len(specs))); ax.set_yticklabels(specs, fontsize=10, fontweight="bold")
    ax.tick_params(top=False, bottom=True, labeltop=False, labelbottom=True)
    for i in range(len(specs)):
        for j in range(len(indicadores)):
            val = z[i,j]
            color = "white" if val > (z.max()*0.5) else C_TEXT
            ax.text(j, i, f"{val:.1f}%", ha="center", va="center",
                    fontsize=11, color=color, fontweight="bold")
    ax.spines[:].set_visible(False)
    ax.set_title("Indicadores de contexto por especialidad (%)",
                 fontsize=11, color=C_NAVY, fontweight="bold", pad=10, loc="left")
    fig.tight_layout()

    sp_des = max(des_map, key=des_map.get) if des_map else specs[0]
    sp_ext = max(specs, key=lambda s: data[specs.index(s)][2])
    texto = (
        f"El heatmap compara 4 indicadores de contexto entre especialidades. "
        f"Celdas más oscuras indican valores más altos. "
        f"{sp_des} presenta la mayor tasa de desistimiento ({des_map.get(sp_des,0):.1f}%). "
        f"{sp_ext} concentra el mayor porcentaje de alumnos extranjeros "
        f"({data[specs.index(sp_ext)][2]:.1f}%), grupo que requiere seguimiento diferenciado "
        f"por su mayor vulnerabilidad socioeconómica."
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


# ══════════════════════════════════════════════════════════════════════
# DESISTIMIENTO — 3 gráficos
# ══════════════════════════════════════════════════════════════════════

def pdf_chart_des_nivel(dd: pd.DataFrame,
                        df_current: pd.DataFrame) -> tuple[bytes, str]:
    """Tasa de desistimiento por nivel."""
    if dd is None or dd.empty:
        return b"", ""
    dd = dd.copy()
    dd["level"] = pd.to_numeric(dd.get("level",0), errors="coerce").fillna(0).astype(int)
    tasas, desistes, niveles = [], [], []
    if df_current is not None and not df_current.empty:
        dfc = df_current.copy()
        dfc["level"] = pd.to_numeric(dfc.get("level",0), errors="coerce").fillna(0).astype(int)
        for niv in sorted([n for n in dd["level"].unique() if n > 0]):
            n_mat = int((dfc["level"]==niv).sum())
            n_des = int((dd["level"]==niv).sum())
            tasa = round(n_des/(n_mat+n_des)*100,1) if (n_mat+n_des)>0 else 0
            tasas.append(tasa); desistes.append(n_des); niveles.append(niv)

    if not tasas:
        return b"", ""

    prom = sum(tasas)/len(tasas)
    colors = [C_RED if t > prom else C_AMBER for t in tasas]
    labels = [f"{n}° Medio" for n in niveles]

    fig, ax = _base_fig(8, 3.5)
    bars = ax.bar(labels, tasas, color=colors, width=0.5, zorder=3)
    ax.axhline(prom, color=C_BLUE, linestyle="--", linewidth=1.2,
               label=f"Promedio {prom:.1f}%", zorder=4)
    for i, (t, d) in enumerate(zip(tasas, desistes)):
        ax.text(i, t + 0.1, f"{t}%\n({d})", ha="center", va="bottom",
                fontsize=9, color=C_TEXT, fontweight="bold")
    ax.set_ylabel("Tasa de desistimiento (%)", fontsize=9, color=C_GRAY)
    ax.yaxis.grid(True, color=C_LGRAY, linestyle="--", linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(fontsize=9, framealpha=0)
    ax.set_title("Tasa de desistimiento por nivel",
                 fontsize=11, color=C_NAVY, fontweight="bold", pad=10, loc="left")

    niv_max = niveles[tasas.index(max(tasas))]
    sobre_prom = [f"{n}° Medio" for n,t in zip(niveles,tasas) if t > prom]
    texto = (
        f"El {niv_max}° Medio registra la mayor tasa de abandono ({max(tasas):.1f}%). "
        f"La línea punteada marca el promedio general ({prom:.1f}%). "
        + (f"Los niveles {' y '.join(sobre_prom)} están sobre el promedio y requieren intervención prioritaria." 
           if sobre_prom else "Todos los niveles están dentro del promedio.")
    )
    return _fig_to_bytes(fig), _wrap(texto)


def pdf_chart_des_especialidad(dd: pd.DataFrame,
                                df_current: pd.DataFrame) -> tuple[bytes, str]:
    """Tasa de desistimiento por especialidad — barras horizontales."""
    if dd is None or dd.empty:
        return b"", ""
    dd = dd.copy()
    dd["specialty"] = dd.get("specialty", pd.Series(dtype=str)).fillna("SIN DATOS").str.upper().str.strip()
    rows = []
    for sp in [s for s in dd["specialty"].unique() if s not in ("SIN DATOS","")]:
        n_des = int((dd["specialty"]==sp).sum())
        n_mat = 0
        if df_current is not None and not df_current.empty:
            dfc = df_current.copy()
            dfc["specialty"] = dfc.get("specialty", pd.Series(dtype=str)).fillna("").str.upper().str.strip()
            n_mat = int((dfc["specialty"]==sp).sum())
        tasa = round(n_des/(n_mat+n_des)*100,1) if (n_mat+n_des)>0 else 0
        rows.append({"sp": sp, "des": n_des, "tasa": tasa})
    if not rows:
        return b"", ""

    rows.sort(key=lambda r: r["tasa"])
    specs = [r["sp"] for r in rows]
    tasas = [r["tasa"] for r in rows]
    desistes = [r["des"] for r in rows]
    colors = [SPEC_COLORS.get(s, C_GRAY) for s in specs]
    prom = sum(tasas)/len(tasas)

    fig, ax = _base_fig(8, 3)
    ax.barh(specs, tasas, color=colors, height=0.45, zorder=3)
    ax.axvline(prom, color=C_BLUE, linestyle="--", linewidth=1.2,
               label=f"Promedio {prom:.1f}%", zorder=4)
    for i, (t, d) in enumerate(zip(tasas, desistes)):
        ax.text(t + 0.1, i, f"{t}%  ({d})", va="center", fontsize=10,
                color=C_TEXT, fontweight="bold")
    ax.set_xlabel("Tasa de desistimiento (%)", fontsize=9, color=C_GRAY)
    ax.xaxis.grid(True, color=C_LGRAY, linestyle="--", linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.set_yticklabels(specs, fontsize=11, fontweight="bold")
    ax.legend(fontsize=9, framealpha=0)
    ax.set_title("Tasa de desistimiento por especialidad",
                 fontsize=11, color=C_NAVY, fontweight="bold", pad=10, loc="left")

    sp_max = rows[-1]; sp_min = rows[0]
    texto = (
        f"{sp_max['sp']} presenta la mayor tasa de desistimiento ({sp_max['tasa']}%, "
        f"{sp_max['des']} alumnos), mientras que {sp_min['sp']} muestra mejor retención "
        f"({sp_min['tasa']}%). "
        f"Una diferencia superior a 2 puntos porcentuales entre especialidades sugiere "
        f"factores estructurales propios de cada una que requieren análisis específico."
    )
    return _fig_to_bytes(fig), _wrap(texto)


def pdf_chart_des_perfil(n_rep: int, n_norep: int,
                          n_h: int, n_m: int) -> tuple[bytes, str]:
    """Dos donuts: repitentes vs nuevos + H/M en desistimiento."""
    total = n_rep + n_norep or 1
    pct_rep = round(n_rep/total*100,1)
    total_hm = n_h + n_m or 1

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5))
    fig.patch.set_facecolor("white")

    for ax in [ax1, ax2]:
        ax.set_facecolor("white")

    # Donut 1: repitentes
    wedges1, _ = ax1.pie([n_rep, n_norep], colors=[C_AMBER, C_GREEN],
                          startangle=90, wedgeprops=dict(width=0.55, edgecolor="white", linewidth=2))
    ax1.text(0, 0, f"{total}\ndesistes", ha="center", va="center",
             fontsize=12, fontweight="bold", color=C_TEXT)
    ax1.set_title("Repitentes en desistimiento", fontsize=10,
                  color=C_NAVY, fontweight="bold", pad=8)
    ax1.legend([f"Repitentes ({n_rep})", f"No repitentes ({n_norep})"],
               fontsize=9, loc="lower center", framealpha=0,
               bbox_to_anchor=(0.5, -0.15))

    # Donut 2: H/M
    wedges2, _ = ax2.pie([n_h, n_m], colors=[C_BLUE, C_GREEN],
                          startangle=90, wedgeprops=dict(width=0.55, edgecolor="white", linewidth=2))
    ax2.text(0, 0, f"{round(n_h/total_hm*100,1)}% H\n{round(n_m/total_hm*100,1)}% M",
             ha="center", va="center", fontsize=10, fontweight="bold", color=C_TEXT)
    ax2.set_title("Género en desistimiento", fontsize=10,
                  color=C_NAVY, fontweight="bold", pad=8)
    ax2.legend([f"Hombres ({n_h})", f"Mujeres ({n_m})"],
               fontsize=9, loc="lower center", framealpha=0,
               bbox_to_anchor=(0.5, -0.15))

    fig.tight_layout(pad=2)
    if pct_rep > 40:
        rep_txt = (f"El {pct_rep}% de quienes abandonan son repitentes, lo que indica "
                   f"una fuerte correlación entre historial de repitencia y deserción. "
                   f"La intervención temprana en alumnos repitentes es prioritaria.")
    elif pct_rep > 20:
        rep_txt = (f"El {pct_rep}% de los desistidos son repitentes — proporción moderada. "
                   f"El abandono no está completamente explicado por el historial académico.")
    else:
        rep_txt = (f"Solo el {pct_rep}% de los desistidos son repitentes. "
                   f"El abandono ocurre principalmente en alumnos sin historial previo.")

    texto = rep_txt + (f" En cuanto al género, el {round(n_h/total_hm*100,1)}% "
                       f"de los desistidos son hombres y el {round(n_m/total_hm*100,1)}% mujeres.")
    return _fig_to_bytes(fig), _wrap(texto)