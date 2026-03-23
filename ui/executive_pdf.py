"""
SIGMA — Generador de PDF Ejecutivo
ui/executive_pdf.py
"""
from __future__ import annotations

import base64
import io
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


try:
    from sigma_pdf_charts import (
        pdf_chart_genero_nivel,
        pdf_chart_especialidad_resumen,
        pdf_chart_heatmap,
        pdf_chart_cursos,
    )
    _CHARTS_OK = True
except Exception:
    _CHARTS_OK = False

# ── Paleta ────────────────────────────────────────────────────────────
C_NAVY    = colors.HexColor("#1e3a5f")
C_BLUE    = colors.HexColor("#2563eb")
C_GREEN   = colors.HexColor("#16a34a")
C_AMBER   = colors.HexColor("#d97706")
C_RED     = colors.HexColor("#dc2626")
C_PURPLE  = colors.HexColor("#7c3aed")
C_TEXT    = colors.HexColor("#111827")
C_MUTED   = colors.HexColor("#6b7280")
C_BORDER  = colors.HexColor("#e5e7eb")
C_ROW_ALT = colors.HexColor("#f9fafb")
C_WHITE   = colors.white

PAGE_W = A4[0] - 3 * cm


# ── Helpers ───────────────────────────────────────────────────────────

def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    try:
        if pd.isna(v):
            return "—"
    except Exception:
        pass
    if isinstance(v, float):
        return f"{int(round(v)):,}" if abs(v - round(v)) < 1e-9 else f"{v:,.1f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)

def _safe(v: Any) -> str:
    """
    Convierte texto a string seguro para ReportLab/Helvetica.
    1. Intenta reparar doble-encoding (UTF-8 leído como latin-1).
    2. Codifica con xmlcharrefreplace para que Helvetica muestre ñ/acentos.
    """
    s = _fmt(v) if not isinstance(v, str) else v
    # Intentar reparar si el texto viene corrupto (UTF-8 bytes interpretados como latin-1)
    try:
        repaired = s.encode("latin-1").decode("utf-8")
        s = repaired
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass  # ya está en unicode correcto, no hacer nada
    # Convertir a entidades XML para compatibilidad con Helvetica en ReportLab
    return s.encode("latin-1", "xmlcharrefreplace").decode("latin-1")



def _norm_sexo(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.upper().str.strip()
    return s.map(lambda v: "M" if v in ("M", "MASCULINO") else ("F" if v in ("F", "FEMENINO") else ""))


def _is_extranjero(series: pd.Series) -> pd.Series:
    return ~series.fillna("CHILENA").astype(str).str.upper().str.strip().isin(
        ["CHILENA", "CHILENO", "CHILE", "NAN", ""]
    )


def _pct(num, total, decimals: int = 1) -> str:
    try:
        if not total:
            return "0%"
        return f"{round(float(num) / float(total) * 100, decimals)}%"
    except Exception:
        return "—%"


def _find_school_logo() -> Path | None:
    root = Path(__file__).resolve().parents[1]
    for name in ["logo_establecimiento.png", "logo_establecimiento.jpg",
                  "logo_liceo.png", "logo_liceo.jpg", "logo_duoc.png"]:
        p = root / "assets" / name
        if p.exists():
            return p
    return None


# ── Bloques reutilizables ─────────────────────────────────────────────

def _sigma_header(story: list, titulo: str, corte: str) -> None:
    logo_style = ParagraphStyle("SigmaLogo", fontName="Helvetica-Bold", fontSize=20, textColor=C_NAVY, leading=24)
    tag_style  = ParagraphStyle("SigmaTag",  fontName="Helvetica", fontSize=7.5, textColor=C_MUTED, leading=10)
    tit_style  = ParagraphStyle("SigmaHdrTit", fontName="Helvetica-Bold", fontSize=13, textColor=C_TEXT, leading=17, alignment=2)
    meta_style = ParagraphStyle("SigmaHdrMeta", fontName="Helvetica", fontSize=8, textColor=C_MUTED, leading=11, alignment=2)

    logo_path = _find_school_logo()
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    left_inner = Table(
        [[Paragraph("SIGMA", logo_style)],
         [Paragraph("Sistema Integrado de Gestion y Monitoreo Academico", tag_style)]],
        colWidths=[PAGE_W * 0.45], rowHeights=[24, 14],
    )
    left_inner.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_WHITE),
        ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0), ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("VALIGN", (0,0), (-1,-1), "BOTTOM"),
    ]))

    if logo_path:
        logo_img  = RLImage(str(logo_path), width=1.8*cm, height=1.8*cm)
        left_block = Table([[logo_img, left_inner]], colWidths=[2.0*cm, PAGE_W*0.42])
        left_block.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (0,-1), 8),
            ("TOPPADDING", (0,0), (-1,-1), 0), ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ]))
        left_w = PAGE_W * 0.5
    else:
        left_block = left_inner
        left_w = PAGE_W * 0.5

    right_block = Table(
        [[Paragraph(_safe(titulo), tit_style)],
         [Paragraph(f"Corte: {_safe(corte)}  ·  Generado: {fecha}", meta_style)]],
        colWidths=[PAGE_W * 0.5], rowHeights=[24, 14],
    )
    right_block.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_WHITE), ("VALIGN", (0,0), (-1,-1), "BOTTOM"),
        ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0), ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))

    header = Table([[left_block, right_block]], colWidths=[left_w, PAGE_W*0.5], rowHeights=[52])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_WHITE), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 8), ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LINEBELOW", (0,0), (-1,-1), 1.5, C_BLUE),
    ]))
    story.append(header)
    story.append(Spacer(1, 0.3*cm))


def _section_title(text: str, color=C_BLUE) -> Table:
    t = Table(
        [[Paragraph(text.upper(), ParagraphStyle("st", fontName="Helvetica-Bold", fontSize=8, textColor=C_MUTED, leading=11))]],
        colWidths=[PAGE_W], rowHeights=[20],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_WHITE),
        ("LINEBEFORE", (0,0), (0,-1), 3, color),
        ("LINEBELOW", (0,0), (-1,-1), 0.4, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
    ]))
    return t


def _kpi_row(kpis: list[tuple]) -> Table:
    n     = len(kpis)
    col_w = PAGE_W / n
    val_row, pct_row, lbl_row = [], [], []
    style_cmds = [
        ("BACKGROUND", (0,0), (-1,-1), C_WHITE),
        ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LINEAFTER", (0,0), (-2,-1), 0.5, C_BORDER),
        ("BOX", (0,0), (-1,-1), 0.5, C_BORDER),
    ]
    for i, kpi in enumerate(kpis):
        label, value, color = kpi[0], kpi[1], kpi[2]
        sub = kpi[3] if len(kpi) > 3 else ""
        val_row.append(Paragraph(
            _safe(_fmt(value) if not isinstance(value, str) else value),
            ParagraphStyle(f"kv{i}", fontName="Helvetica-Bold", fontSize=20, textColor=color, alignment=1, leading=24),
        ))
        pct_row.append(Paragraph(_safe(str(sub)), ParagraphStyle(f"ks{i}", fontName="Helvetica", fontSize=7, textColor=color, alignment=1, leading=9)))
        lbl_row.append(Paragraph(_safe(str(label)).upper(), ParagraphStyle(f"kl{i}", fontName="Helvetica", fontSize=6.5, textColor=C_MUTED, alignment=1, leading=9)))
        style_cmds.append(("LINEBELOW", (i,0), (i,0), 2.5, color))
    t = Table([val_row, pct_row, lbl_row], colWidths=[col_w]*n, rowHeights=[28, 12, 14])
    t.setStyle(TableStyle(style_cmds))
    return t


def _df_to_table(df: pd.DataFrame, col_widths: list | None = None) -> Table:
    hdr_s = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=C_WHITE)
    cel_s = ParagraphStyle("td", fontName="Helvetica", fontSize=8, textColor=C_TEXT)
    rows  = [[Paragraph(_safe(str(c)), hdr_s) for c in df.columns]]
    for _, row in df.iterrows():
        rows.append([Paragraph("" if (isinstance(v, float) and pd.isna(v)) else _safe(str(v)), cel_s) for v in row])
    if col_widths is None:
        col_widths = [PAGE_W / max(len(df.columns), 1)] * len(df.columns)
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0,0), (-1,0), C_NAVY), ("TEXTCOLOR", (0,0), (-1,0), C_WHITE),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,0), 8),
        ("LINEBELOW", (0,0), (-1,-1), 0.4, C_BORDER), ("BOX", (0,0), (-1,-1), 0.4, C_BORDER),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4), ("LEFTPADDING", (0,0), (-1,-1), 6),
    ]
    for i in range(1, len(rows)):
        style_cmds.append(("BACKGROUND", (0,i), (-1,i), C_ROW_ALT if i % 2 == 0 else C_WHITE))
    t.setStyle(TableStyle(style_cmds))
    return t


def _chart_block(story: list, img_bytes: bytes, texto: str, width_cm: float = 17.0) -> None:
    if not img_bytes:
        return
    img = RLImage(io.BytesIO(img_bytes), width=width_cm*cm, height=width_cm*cm*0.38)
    story.append(img)
    if texto:
        story.append(Spacer(1, 0.15*cm))
        story.append(Paragraph(_safe(texto), ParagraphStyle(
            "insight", fontName="Helvetica", fontSize=8,
            textColor=colors.HexColor("#374151"), backColor=colors.HexColor("#f9fafb"),
            borderPad=6, leading=12, spaceAfter=4, leftIndent=6, rightIndent=6,
        )))
    story.append(Spacer(1, 0.3*cm))


def _sigma_footer(story: list, modulo: str = "SIGMA") -> None:
    story.append(Spacer(1, 0.5*cm))
    t = Table(
        [[Paragraph(
            f"SIGMA  ·  {_safe(modulo)}  ·  {datetime.now().strftime('%d/%m/%Y %H:%M')}  ·  Documento de uso interno",
            ParagraphStyle("ft", fontName="Helvetica", fontSize=7, textColor=C_MUTED, alignment=1),
        )]],
        colWidths=[PAGE_W], rowHeights=[18],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_WHITE), ("LINEABOVE", (0,0), (-1,-1), 0.5, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(t)


# ─────────────────────────────────────────────────────────────────────
# PDF MATRÍCULA
# ─────────────────────────────────────────────────────────────────────

def generate_pdf_matricula(
    stamp: str,
    metrics,
    df_current: pd.DataFrame | None,
    df_specs: pd.DataFrame | None = None,
    df_comunas: pd.DataFrame | None = None,
    df_nacs: pd.DataFrame | None = None,
    prev_metrics=None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    story: list = []

    row          = metrics.iloc[0].to_dict() if metrics is not None and not metrics.empty else {}
    matriculados = int(row.get("matriculados_actuales", 0) or 0)
    retirados    = int(row.get("retirados_reales", 0) or 0)
    transfers    = int(row.get("transferencias_internas", 0) or 0)
    ruts_unicos  = int(row.get("ruts_unicos", 0) or 0)

    df      = df_current.copy() if df_current is not None and not df_current.empty else pd.DataFrame()
    hombres = int((_norm_sexo(df["sexo"]) == "M").sum()) if "sexo" in df.columns else 0
    mujeres = int((_norm_sexo(df["sexo"]) == "F").sum()) if "sexo" in df.columns else 0
    repitentes  = int(df["is_repeat"].sum()) if "is_repeat" in df.columns else 0
    extranjeros = int(_is_extranjero(df["nacionalidad"]).sum()) if "nacionalidad" in df.columns else 0
    total = matriculados or len(df) or 1

    _sigma_header(story, "Reporte Ejecutivo · Matricula", stamp)

    story.append(_section_title("Indicadores principales"))
    story.append(Spacer(1, 0.15*cm))
    story.append(_kpi_row([
        ("Matriculados",   matriculados, C_BLUE,   "activos al corte"),
        ("Hombres",        hombres,      C_BLUE,   _pct(hombres, total) + " del total"),
        ("Mujeres",        mujeres,      C_GREEN,  _pct(mujeres, total) + " del total"),
        ("RUTs unicos",    ruts_unicos,  C_PURPLE, ""),
    ]))
    story.append(Spacer(1, 0.2*cm))
    story.append(_kpi_row([
        ("Retirados",      retirados,   C_RED,    _pct(retirados, total+retirados) + " del universo"),
        ("Transferencias", transfers,   C_AMBER,  _pct(transfers, total) + " del total"),
        ("Repitentes",     repitentes,  C_AMBER,  _pct(repitentes, total) + " del total"),
        ("Extranjeros",    extranjeros, C_PURPLE, _pct(extranjeros, total) + " del total"),
    ]))
    story.append(Spacer(1, 0.4*cm))

    if not df.empty and "specialty" in df.columns:
        story.append(_section_title("Distribucion por especialidad"))
        story.append(Spacer(1, 0.12*cm))
        df_sp = (
            df.assign(_sx=_norm_sexo(df.get("sexo", pd.Series(dtype=str))))
            .groupby("specialty", as_index=False)
            .agg(Total=("rut_norm" if "rut_norm" in df.columns else df.columns[0], "count"),
                 Hombres=("_sx", lambda x: (x=="M").sum()),
                 Mujeres=("_sx", lambda x: (x=="F").sum()))
            .sort_values("Total", ascending=False)
            .rename(columns={"specialty": "Especialidad"})
        )
        df_sp["% Total"]   = df_sp["Total"].apply(lambda n: _pct(n, total))
        df_sp["% Hombres"] = df_sp.apply(lambda r: _pct(r["Hombres"], r["Total"]), axis=1)
        df_sp["% Mujeres"] = df_sp.apply(lambda r: _pct(r["Mujeres"], r["Total"]), axis=1)
        story.append(_df_to_table(df_sp, col_widths=[4.5*cm, 2.0*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2.2*cm]))
        story.append(Spacer(1, 0.4*cm))

    if not df.empty and "level" in df.columns:
        story.append(_section_title("Distribucion por nivel"))
        story.append(Spacer(1, 0.12*cm))
        df_niv = (
            df.assign(_sx=_norm_sexo(df.get("sexo", pd.Series(dtype=str))),
                      _nivel=pd.to_numeric(df["level"], errors="coerce").fillna(0).astype(int))
            .query("_nivel > 0")
            .groupby("_nivel", as_index=False)
            .agg(Total=("rut_norm" if "rut_norm" in df.columns else df.columns[0], "count"),
                 Hombres=("_sx", lambda x: (x=="M").sum()),
                 Mujeres=("_sx", lambda x: (x=="F").sum()))
            .sort_values("_nivel")
            .rename(columns={"_nivel": "Nivel"})
        )
        df_niv["Nivel"]   = df_niv["Nivel"].apply(lambda n: f"{n}° Medio")
        df_niv["% Total"] = df_niv["Total"].apply(lambda n: _pct(n, total))
        df_niv["% H"]     = df_niv.apply(lambda r: _pct(r["Hombres"], r["Total"]), axis=1)
        df_niv["% M"]     = df_niv.apply(lambda r: _pct(r["Mujeres"], r["Total"]), axis=1)
        story.append(_df_to_table(df_niv, col_widths=[3.0*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2.5*cm, 2.2*cm, 2.2*cm]))
        story.append(Spacer(1, 0.4*cm))

    if not df.empty and "comuna" in df.columns:
        story.append(_section_title("Top comunas de procedencia"))
        story.append(Spacer(1, 0.12*cm))
        df_com = (
            df.groupby("comuna", as_index=False).size()
            .rename(columns={"size": "Alumnos"})
            .sort_values("Alumnos", ascending=False).head(10)
        )
        df_com["% del total"] = df_com["Alumnos"].apply(lambda n: _pct(n, total))
        story.append(_df_to_table(df_com.rename(columns={"comuna": "Comuna"}),
                                   col_widths=[8*cm, 4*cm, 4*cm]))
        story.append(Spacer(1, 0.4*cm))

    if _CHARTS_OK and not df.empty:
        story.append(PageBreak())
        _sigma_header(story, "Analisis Visual · Matricula", stamp)
        story.append(_section_title("Matricula por nivel y genero"))
        img, txt = pdf_chart_genero_nivel(df)
        _chart_block(story, img, txt)
        story.append(_section_title("Matricula por especialidad"))
        img, txt = pdf_chart_especialidad_resumen(df)
        _chart_block(story, img, txt)
        story.append(_section_title("Indicadores de contexto por especialidad"))
        img, txt = pdf_chart_heatmap(df)
        _chart_block(story, img, txt)
        story.append(_section_title("Detalle por curso"))
        img, txt = pdf_chart_cursos(df)
        _chart_block(story, img, txt)

    _sigma_footer(story, "Matricula")
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────
# PDF ASISTENCIA
# ─────────────────────────────────────────────────────────────────────

def generate_pdf_asistencia(
    df_alumnos: pd.DataFrame | None,
    df_cursos: pd.DataFrame | None,
    df_serie: pd.DataFrame | None,
    corte: str,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    story: list = []
    _sigma_header(story, "Reporte Ejecutivo · Asistencia", corte)

    if df_alumnos is None or df_alumnos.empty:
        story.append(Paragraph("Sin datos de asistencia disponibles.",
            ParagraphStyle("na", fontName="Helvetica", fontSize=10, textColor=C_MUTED)))
        _sigma_footer(story, "Asistencia")
        doc.build(story)
        return buf.getvalue()

    total_al   = len(df_alumnos)
    pct_global = round(df_alumnos["pct_asistencia"].mean(), 1) if "pct_asistencia" in df_alumnos.columns else 0
    bajo_75    = int((df_alumnos.get("alerta", pd.Series()) == "CRITICO").sum()) if "alerta" in df_alumnos.columns else 0
    bajo_85    = int(df_alumnos["alerta"].isin(["LEGAL","CRITICO"]).sum()) if "alerta" in df_alumnos.columns else 0
    tend_baja  = int((df_alumnos.get("tendencia", pd.Series()) == "BAJA").sum()) if "tendencia" in df_alumnos.columns else 0

    color_global = C_GREEN if pct_global >= 90 else (C_AMBER if pct_global >= 85 else C_RED)

    story.append(_section_title("Indicadores de asistencia"))
    story.append(Spacer(1, 0.15*cm))
    story.append(_kpi_row([
        ("Asistencia global",  f"{pct_global}%", color_global, f"{total_al} alumnos"),
        ("Bajo 75% (critico)", bajo_75,           C_RED,        _pct(bajo_75,  total_al)),
        ("Bajo 85% (legal)",   bajo_85,           C_AMBER,      _pct(bajo_85,  total_al)),
        ("Tendencia baja",     tend_baja,          C_PURPLE,     _pct(tend_baja, total_al)),
    ]))
    story.append(Spacer(1, 0.4*cm))

    if "alerta" in df_alumnos.columns:
        criticos = df_alumnos[df_alumnos["alerta"] == "CRITICO"].copy()
        if not criticos.empty:
            story.append(_section_title("Alumnos criticos — bajo 75%", C_RED))
            story.append(Spacer(1, 0.1*cm))
            cols = [c for c in ["nombre","curso","pct_asistencia","dias_presentes","dias_ausentes","tendencia"] if c in criticos.columns]
            df_crit = criticos[cols].sort_values("pct_asistencia").head(30).reset_index(drop=True)
            df_crit = df_crit.rename(columns={"nombre":"Nombre","curso":"Curso",
                "pct_asistencia":"% Asistencia","dias_presentes":"Presentes",
                "dias_ausentes":"Ausentes","tendencia":"Tendencia"})
            if "% Asistencia" in df_crit.columns:
                df_crit["% Asistencia"] = df_crit["% Asistencia"].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
            story.append(_df_to_table(df_crit))
            story.append(Spacer(1, 0.35*cm))

    if df_cursos is not None and not df_cursos.empty:
        story.append(_section_title("Asistencia por curso"))
        story.append(Spacer(1, 0.1*cm))
        # Normalizar nombre de columna — puede ser pct_asistencia o pct_promedio
        df_c = df_cursos.copy()
        if "pct_promedio" in df_c.columns and "pct_asistencia" not in df_c.columns:
            df_c = df_c.rename(columns={"pct_promedio": "pct_asistencia"})
        df_c = df_c.sort_values(
            "pct_asistencia" if "pct_asistencia" in df_c.columns else df_c.columns[0], ascending=False)
        if "pct_asistencia" in df_c.columns:
            df_c["% Asistencia"] = df_c["pct_asistencia"].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
        # Semáforo
        def _sem(v):
            try:
                n = float(str(v).replace("%",""))
                if n < 75: return "🔴 Crítico"
                if n < 85: return "🟡 Legal"
                return "🟢 OK"
            except: return "—"
        if "% Asistencia" in df_c.columns:
            df_c["Estado"] = df_c["% Asistencia"].apply(_sem)
        # Columnas adicionales útiles
        if "bajo_85" in df_c.columns:
            df_c["Bajo 85%"] = df_c["bajo_85"].astype(int)
        if "bajo_75" in df_c.columns:
            df_c["Bajo 75%"] = df_c["bajo_75"].astype(int)
        df_c = df_c.rename(columns={"curso":"Curso","n_alumnos":"Alumnos"})
        show = [c for c in ["Curso","Alumnos","% Asistencia","Bajo 85%","Bajo 75%","Estado"] if c in df_c.columns]
        if show:
            story.append(_df_to_table(df_c[show], col_widths=[2.5*cm, 2*cm, 3*cm, 2.5*cm, 2.5*cm, 3*cm][:len(show)]))
        story.append(Spacer(1, 0.35*cm))

    _sigma_footer(story, "Asistencia")
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────
# PDF ATRASOS — profundizado
# ─────────────────────────────────────────────────────────────────────

def generate_pdf_atrasos(
    df_alumnos:    pd.DataFrame | None,
    df_cursos:     pd.DataFrame | None,
    corte:         str,
    df_eventos:    pd.DataFrame | None = None,
    df_serie:      pd.DataFrame | None = None,
    df_by_bloque:  pd.DataFrame | None = None,
    df_by_dia:     pd.DataFrame | None = None,
    df_by_periodo: pd.DataFrame | None = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    story: list = []
    _sigma_header(story, "Reporte Ejecutivo · Atrasos", corte)

    if df_alumnos is None or df_alumnos.empty:
        story.append(Paragraph("Sin datos de atrasos disponibles.",
            ParagraphStyle("na", fontName="Helvetica", fontSize=10, textColor=C_MUTED)))
        _sigma_footer(story, "Atrasos")
        doc.build(story)
        return buf.getvalue()

    # ── Métricas globales ─────────────────────────────────────────────
    total_al   = len(df_alumnos)
    total_atr  = int(df_alumnos["n_atrasos"].sum()) if "n_atrasos" in df_alumnos.columns else total_al
    total_just = int(df_alumnos["n_justificados"].sum()) if "n_justificados" in df_alumnos.columns else 0
    pct_just   = _pct(total_just, total_atr)

    # Niveles de alerta
    criticos = int((df_alumnos.get("alerta", pd.Series()) == "CRITICO").sum()) if "alerta" in df_alumnos.columns else 0
    altos    = int((df_alumnos.get("alerta", pd.Series()) == "ALTO").sum())    if "alerta" in df_alumnos.columns else 0
    medios   = int((df_alumnos.get("alerta", pd.Series()) == "MEDIO").sum())   if "alerta" in df_alumnos.columns else 0
    reincid  = int((df_alumnos["n_atrasos"] >= 3).sum()) if "n_atrasos" in df_alumnos.columns else 0

    # Promedio por alumno
    prom_atr = round(total_atr / total_al, 1) if total_al else 0

    story.append(_section_title("Indicadores globales de atrasos"))
    story.append(Spacer(1, 0.15*cm))
    story.append(_kpi_row([
        ("Total atrasos",     total_atr,  C_BLUE,   f"{total_al} alumnos involucrados"),
        ("Promedio / alumno", f"{prom_atr}", C_BLUE, "atrasos por alumno"),
        ("Justificados",      total_just, C_GREEN,  pct_just + " del total"),
        ("Injustificados",    total_atr - total_just, C_AMBER, _pct(total_atr - total_just, total_atr)),
    ]))
    story.append(Spacer(1, 0.2*cm))
    story.append(_kpi_row([
        ("Criticos (>=8)",    criticos, C_RED,    _pct(criticos, total_al) + " del total"),
        ("Altos (4-7)",       altos,    C_AMBER,  _pct(altos,    total_al) + " del total"),
        ("Medios (2-3)",      medios,   C_PURPLE, _pct(medios,   total_al) + " del total"),
        ("Reincidentes (>=3)",reincid,  C_AMBER,  _pct(reincid,  total_al) + " del total"),
    ]))
    story.append(Spacer(1, 0.4*cm))

    # ── Top 30 alumnos críticos ───────────────────────────────────────
    story.append(_section_title("Alumnos criticos y de alto riesgo", C_RED))
    story.append(Spacer(1, 0.1*cm))

    cols_al = ["nombre", "curso", "n_atrasos", "n_justificados", "dias_con_atraso", "pct_justificados", "alerta"]
    cols_al = [c for c in cols_al if c in df_alumnos.columns]
    df_crit_al = (
        df_alumnos[df_alumnos["alerta"].isin(["CRITICO", "ALTO"])]
        if "alerta" in df_alumnos.columns
        else df_alumnos.nlargest(30, "n_atrasos" if "n_atrasos" in df_alumnos.columns else df_alumnos.columns[0])
    )
    df_crit_al = df_crit_al.sort_values("n_atrasos" if "n_atrasos" in df_crit_al.columns else df_crit_al.columns[0],
                                         ascending=False).head(30).reset_index(drop=True)
    df_crit_al = df_crit_al[cols_al].rename(columns={
        "nombre": "Nombre", "curso": "Curso", "n_atrasos": "N° Atrasos",
        "n_justificados": "Justificados", "dias_con_atraso": "Dias c/Atraso",
        "pct_justificados": "% Justif.", "alerta": "Alerta",
    })
    if "% Justif." in df_crit_al.columns:
        df_crit_al["% Justif."] = df_crit_al["% Justif."].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
    story.append(_df_to_table(df_crit_al))
    story.append(Spacer(1, 0.4*cm))

    # ── Detalle por curso ─────────────────────────────────────────────
    if df_cursos is not None and not df_cursos.empty:
        story.append(_section_title("Atrasos por curso"))
        story.append(Spacer(1, 0.1*cm))
        df_c = df_cursos.copy().sort_values("total_atrasos", ascending=False)
        df_c = df_c.rename(columns={
            "curso": "Curso", "total_atrasos": "Total Atrasos",
            "alumnos_unicos": "Alumnos", "justificados": "Justificados",
            "pct_justificados": "% Justif.", "promedio_atrasos_por_alumno": "Prom/Alumno",
        })
        if "% Justif." in df_c.columns:
            df_c["% Justif."] = df_c["% Justif."].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
        if "Prom/Alumno" in df_c.columns:
            df_c["Prom/Alumno"] = df_c["Prom/Alumno"].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "—")
        show_c = [c for c in ["Curso","Total Atrasos","Alumnos","Justificados","% Justif.","Prom/Alumno"] if c in df_c.columns]
        story.append(_df_to_table(df_c[show_c],
            col_widths=[3.0*cm, 2.8*cm, 2.2*cm, 2.8*cm, 2.2*cm, 2.5*cm]))
        story.append(Spacer(1, 0.4*cm))

    # ── Página 2: Análisis de patrones ───────────────────────────────
    story.append(PageBreak())
    _sigma_header(story, "Analisis de Patrones · Atrasos", corte)

    # Distribución por nivel de alerta
    if "alerta" in df_alumnos.columns:
        story.append(_section_title("Distribucion por nivel de alerta"))
        story.append(Spacer(1, 0.12*cm))
        df_alert = (
            df_alumnos.groupby("alerta", as_index=False)
            .agg(Alumnos=("n_atrasos" if "n_atrasos" in df_alumnos.columns else df_alumnos.columns[0], "count"),
                 Total_Atrasos=("n_atrasos" if "n_atrasos" in df_alumnos.columns else df_alumnos.columns[0], "sum"))
        )
        orden = {"CRITICO": 0, "ALTO": 1, "MEDIO": 2, "BAJO": 3}
        df_alert["_ord"] = df_alert["alerta"].map(orden).fillna(9)
        df_alert = df_alert.sort_values("_ord").drop(columns=["_ord"])
        df_alert["% Alumnos"] = df_alert["Alumnos"].apply(lambda n: _pct(n, total_al))
        df_alert["Prom Atrasos"] = df_alert.apply(
            lambda r: f"{round(r['Total_Atrasos'] / r['Alumnos'], 1)}" if r["Alumnos"] > 0 else "—", axis=1
        )
        df_alert = df_alert.rename(columns={"alerta": "Nivel", "Total_Atrasos": "Total Atrasos"})
        story.append(_df_to_table(df_alert[["Nivel","Alumnos","% Alumnos","Total Atrasos","Prom Atrasos"]],
            col_widths=[3*cm, 3*cm, 3*cm, 3.5*cm, 3.5*cm]))
        story.append(Spacer(1, 0.4*cm))

    # Análisis de tipos de atraso (de df_eventos)
    if df_eventos is not None and not df_eventos.empty and "tipo_atraso" in df_eventos.columns:
        story.append(_section_title("Tipos de atraso mas frecuentes"))
        story.append(Spacer(1, 0.12*cm))
        df_tipo = (
            df_eventos[df_eventos["tipo_atraso"].astype(str).fillna("") != ""]
            .groupby("tipo_atraso", as_index=False)
            .agg(Eventos=("tipo_atraso", "count"))
            .sort_values("Eventos", ascending=False)
            .head(10)
        )
        if not df_tipo.empty:
            total_ev = len(df_eventos)
            df_tipo["% del total"] = df_tipo["Eventos"].apply(lambda n: _pct(n, total_ev))
            df_tipo = df_tipo.rename(columns={"tipo_atraso": "Tipo de Atraso"})
            story.append(_df_to_table(df_tipo, col_widths=[9*cm, 3.5*cm, 4*cm]))
            story.append(Spacer(1, 0.4*cm))

    # Análisis de periodo / hora (de df_eventos)
    if df_eventos is not None and not df_eventos.empty and "periodo" in df_eventos.columns:
        story.append(_section_title("Atrasos por periodo del dia"))
        story.append(Spacer(1, 0.12*cm))
        df_per = (
            df_eventos[df_eventos["periodo"].astype(str).fillna("").str.strip() != ""]
            .groupby("periodo", as_index=False)
            .agg(Eventos=("periodo", "count"),
                 Alumnos=("rut_norm", "nunique") if "rut_norm" in df_eventos.columns else ("periodo", "count"))
            .sort_values("Eventos", ascending=False)
            .head(10)
        )
        if not df_per.empty:
            total_ev = len(df_eventos)
            df_per["% del total"] = df_per["Eventos"].apply(lambda n: _pct(n, total_ev))
            df_per = df_per.rename(columns={"periodo": "Periodo"})
            story.append(_df_to_table(df_per, col_widths=[6*cm, 3.5*cm, 3.5*cm, 3.5*cm]))
            story.append(Spacer(1, 0.4*cm))

    # Serie temporal resumida
    if df_serie is not None and not df_serie.empty:
        story.append(_section_title("Resumen de serie diaria (ultimos 20 dias)"))
        story.append(Spacer(1, 0.12*cm))
        df_s = df_serie.copy()
        if "fecha" in df_s.columns:
            df_s = df_s.sort_values("fecha").tail(20)
        df_s = df_s.rename(columns={
            "fecha": "Fecha", "atrasos_dia": "Atrasos",
            "alumnos_unicos": "Alumnos", "justificados_dia": "Justificados",
            "pct_justificados_dia": "% Justif.",
        })
        if "% Justif." in df_s.columns:
            df_s["% Justif."] = df_s["% Justif."].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
        show_s = [c for c in ["Fecha","Atrasos","Alumnos","Justificados","% Justif."] if c in df_s.columns]
        story.append(_df_to_table(df_s[show_s].reset_index(drop=True)))
        story.append(Spacer(1, 0.4*cm))

    # Nómina completa de reincidentes
    if reincid > 0 and "n_atrasos" in df_alumnos.columns:
        story.append(PageBreak())
        _sigma_header(story, "Nomina de Reincidentes · Atrasos", corte)
        story.append(_section_title("Todos los alumnos con 3 o mas atrasos", C_AMBER))
        story.append(Spacer(1, 0.12*cm))

        df_reinc = df_alumnos[df_alumnos["n_atrasos"] >= 3].copy()
        df_reinc = df_reinc.sort_values("n_atrasos", ascending=False).reset_index(drop=True)
        cols_r = ["nombre","curso","n_atrasos","n_justificados","dias_con_atraso","pct_justificados","alerta"]
        cols_r = [c for c in cols_r if c in df_reinc.columns]
        df_reinc = df_reinc[cols_r].rename(columns={
            "nombre": "Nombre", "curso": "Curso", "n_atrasos": "N° Atrasos",
            "n_justificados": "Justificados", "dias_con_atraso": "Dias c/Atraso",
            "pct_justificados": "% Justif.", "alerta": "Alerta",
        })
        if "% Justif." in df_reinc.columns:
            df_reinc["% Justif."] = df_reinc["% Justif."].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
        story.append(_df_to_table(df_reinc))

    # ── Página 3: Análisis horario ───────────────────────────────────
    tiene_horario = (
        (df_by_bloque  is not None and not df_by_bloque.empty) or
        (df_by_dia     is not None and not df_by_dia.empty)    or
        (df_by_periodo is not None and not df_by_periodo.empty)
    )

    if tiene_horario:
        story.append(PageBreak())
        _sigma_header(story, "Analisis Horario · Atrasos", corte)

        # ── Bloques de 10 minutos ─────────────────────────────────────
        if df_by_bloque is not None and not df_by_bloque.empty:
            story.append(_section_title("¿A que hora llegan tarde?", C_AMBER))
            story.append(Spacer(1, 0.12*cm))

            # Insight textual automático
            pico = df_by_bloque.loc[df_by_bloque["atrasos"].idxmax()]
            pct_8 = df_by_bloque[df_by_bloque["bloque"].str.startswith("08")]["atrasos"].sum()
            total_b = df_by_bloque["atrasos"].sum()
            pct_8_pct = round(pct_8 / total_b * 100, 1) if total_b else 0

            story.append(Paragraph(
                _safe(
                    f"El pico de atrasos se produce entre las {pico['bloque']} hrs "
                    f"con {int(pico['atrasos'])} registros ({pico['pct_del_total']:.1f}% del total). "
                    f"El bloque 08:00-09:00 concentra el {pct_8_pct}% de todos los atrasos del periodo."
                ),
                ParagraphStyle("insight_h", fontName="Helvetica", fontSize=9,
                    textColor=colors.HexColor("#374151"),
                    backColor=colors.HexColor("#f9fafb"),
                    borderPad=6, leading=13, spaceAfter=8,
                    leftIndent=6, rightIndent=6),
            ))
            story.append(Spacer(1, 0.15*cm))

            df_b = df_by_bloque.rename(columns={
                "bloque":          "Bloque horario",
                "atrasos":         "Atrasos",
                "alumnos":         "Alumnos unicos",
                "justificados":    "Justificados",
                "pct_justificados":"% Justif.",
                "pct_del_total":   "% del total",
            }).copy()
            if "% Justif." in df_b.columns:
                df_b["% Justif."] = df_b["% Justif."].apply(lambda v: f"{v:.1f}%")
            if "% del total" in df_b.columns:
                df_b["% del total"] = df_b["% del total"].apply(lambda v: f"{v:.1f}%")
            show_b = [c for c in ["Bloque horario","Atrasos","Alumnos unicos",
                                   "Justificados","% Justif.","% del total"] if c in df_b.columns]
            story.append(_df_to_table(df_b[show_b], col_widths=[
                3.5*cm, 2.2*cm, 2.8*cm, 2.8*cm, 2.2*cm, 2.5*cm
            ]))
            story.append(Spacer(1, 0.4*cm))

        # ── Por día de la semana ──────────────────────────────────────
        if df_by_dia is not None and not df_by_dia.empty:
            story.append(_section_title("¿Que dias de la semana hay mas atrasos?", C_AMBER))
            story.append(Spacer(1, 0.12*cm))

            dia_max = df_by_dia.loc[df_by_dia["atrasos"].idxmax()]
            dia_min = df_by_dia.loc[df_by_dia["atrasos"].idxmin()]
            story.append(Paragraph(
                _safe(
                    f"{dia_max['dia_label']} es el dia con mas atrasos "
                    f"({int(dia_max['atrasos'])}, {dia_max['pct_del_total']:.1f}% del total). "
                    f"{dia_min['dia_label']} es el dia con menos atrasos "
                    f"({int(dia_min['atrasos'])}, {dia_min['pct_del_total']:.1f}%)."
                ),
                ParagraphStyle("insight_d", fontName="Helvetica", fontSize=9,
                    textColor=colors.HexColor("#374151"),
                    backColor=colors.HexColor("#f9fafb"),
                    borderPad=6, leading=13, spaceAfter=8,
                    leftIndent=6, rightIndent=6),
            ))
            story.append(Spacer(1, 0.15*cm))

            df_d = df_by_dia.rename(columns={
                "dia_label":    "Dia",
                "atrasos":      "Atrasos",
                "alumnos":      "Alumnos unicos",
                "justificados": "Justificados",
                "pct_del_total":"% del total",
            }).copy()
            if "% del total" in df_d.columns:
                df_d["% del total"] = df_d["% del total"].apply(lambda v: f"{v:.1f}%")
            show_d = [c for c in ["Dia","Atrasos","Alumnos unicos","Justificados","% del total"] if c in df_d.columns]
            story.append(_df_to_table(df_d[show_d], col_widths=[3.5*cm, 2.5*cm, 3.0*cm, 3.0*cm, 3.0*cm]))
            story.append(Spacer(1, 0.4*cm))

        # ── Por período ───────────────────────────────────────────────
        if df_by_periodo is not None and not df_by_periodo.empty:
            story.append(_section_title("¿En que bloque de clases ocurren?", C_AMBER))
            story.append(Spacer(1, 0.12*cm))

            per_max = df_by_periodo.loc[df_by_periodo["atrasos"].idxmax()]
            story.append(Paragraph(
                _safe(
                    f"El periodo {per_max['periodo']} concentra la mayor cantidad de atrasos "
                    f"con {int(per_max['atrasos'])} registros ({per_max['pct_del_total']:.1f}% del total). "
                    f"Los primeros periodos del dia son los mas afectados, "
                    f"coherente con la concentracion horaria en el bloque 08:00-09:00."
                ),
                ParagraphStyle("insight_p", fontName="Helvetica", fontSize=9,
                    textColor=colors.HexColor("#374151"),
                    backColor=colors.HexColor("#f9fafb"),
                    borderPad=6, leading=13, spaceAfter=8,
                    leftIndent=6, rightIndent=6),
            ))
            story.append(Spacer(1, 0.15*cm))

            df_p = df_by_periodo.copy()
            df_p["periodo"] = "Periodo " + df_p["periodo"].astype(str)
            df_p = df_p.rename(columns={
                "periodo":      "Periodo",
                "atrasos":      "Atrasos",
                "alumnos":      "Alumnos unicos",
                "justificados": "Justificados",
                "pct_del_total":"% del total",
            })
            if "% del total" in df_p.columns:
                df_p["% del total"] = df_p["% del total"].apply(lambda v: f"{v:.1f}%")
            show_p = [c for c in ["Periodo","Atrasos","Alumnos unicos","Justificados","% del total"] if c in df_p.columns]
            story.append(_df_to_table(df_p[show_p], col_widths=[3.5*cm, 2.5*cm, 3.0*cm, 3.0*cm, 3.0*cm]))

    _sigma_footer(story, "Atrasos")
    doc.build(story)
    return buf.getvalue()


# ── Streamlit utils ───────────────────────────────────────────────────


def generate_pdf_ejecutivo(
    stamp: str,
    df_current=None,
    metrics=None,
    df_asist_alumnos=None,
    df_asist_cursos=None,
    df_asist_serie=None,
    df_atr_alumnos=None,
    df_atr_serie=None,
    df_atr_cursos=None,
    df_hist_mat=None,
    df_hist_atr=None,
    df_hist_asi=None,
):
    """Reporte ejecutivo consolidado SIGMA — 3 paginas, layout simple."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm)
    story = []
    W = PAGE_W

    # ── Datos ─────────────────────────────────────────────────────────
    row_m = metrics.iloc[0].to_dict() if metrics is not None and not metrics.empty else {}
    df    = df_current.copy() if df_current is not None and not df_current.empty else pd.DataFrame()

    matriculados = int(row_m.get("matriculados_actuales", len(df)) or len(df))
    retirados    = int(row_m.get("retirados_reales", 0) or 0)
    total        = max(matriculados, 1)

    hombres     = int((_norm_sexo(df["sexo"]) == "M").sum()) if "sexo" in df.columns else 0
    mujeres     = int((_norm_sexo(df["sexo"]) == "F").sum()) if "sexo" in df.columns else 0
    extranjeros = int(_is_extranjero(df["nacionalidad"]).sum()) if "nacionalidad" in df.columns else 0

    pct_asist = bajo_85 = bajo_75 = 0.0
    if df_asist_alumnos is not None and not df_asist_alumnos.empty:
        if "pct_asistencia" in df_asist_alumnos.columns:
            pct_asist = round(float(df_asist_alumnos["pct_asistencia"].mean()), 1)
        if "alerta" in df_asist_alumnos.columns:
            bajo_85 = int(df_asist_alumnos["alerta"].isin(["LEGAL","CRITICO"]).sum())
            bajo_75 = int((df_asist_alumnos["alerta"] == "CRITICO").sum())

    total_atrasos   = int(df_atr_alumnos["n_atrasos"].sum()) if df_atr_alumnos is not None and not df_atr_alumnos.empty else 0
    alumnos_con_atr = len(df_atr_alumnos) if df_atr_alumnos is not None else 0
    reincidentes    = int((df_atr_alumnos["n_atrasos"] >= 3).sum()) if df_atr_alumnos is not None and not df_atr_alumnos.empty else 0

    # ── Helpers locales ───────────────────────────────────────────────
    def S(txt, bold=False, color=None, size=8, align=0):
        return Paragraph(_safe(str(txt)), ParagraphStyle("x",
            fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=size, textColor=color or C_TEXT,
            alignment=align, leading=size+3))

    def simple_table(rows, widths):
        """Tabla segura: escala widths a W automaticamente."""
        s = sum(widths)
        if s > 0:
            widths = [w * W / s for w in widths]
        t = Table(rows, colWidths=widths, repeatRows=1)
        cmds = [
            ("BACKGROUND", (0,0), (-1,0), C_NAVY),
            ("TEXTCOLOR",  (0,0), (-1,0), C_WHITE),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1), 8),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
            ("LEFTPADDING", (0,0),(-1,-1), 5),
            ("RIGHTPADDING",(0,0),(-1,-1), 5),
            ("LINEBELOW",  (0,0), (-1,-1), 0.4, C_BORDER),
            ("BOX",        (0,0), (-1,-1), 0.4, C_BORDER),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ]
        for i in range(2, len(rows), 2):
            cmds.append(("BACKGROUND", (0,i), (-1,i), C_ROW_ALT))
        t.setStyle(TableStyle(cmds))
        return t

    def hdr(*cols):
        return [S(c, bold=True, color=C_WHITE) for c in cols]

    def spc():
        return Spacer(1, 0.3*cm)

    # ══════════════════════════════════════════════════════════════════
    # PAG 1 — MATRICULA + ASISTENCIA
    # ══════════════════════════════════════════════════════════════════
    _sigma_header(story, "Reporte Ejecutivo · Resumen General", stamp)

    story += [_section_title("1. Matricula"), spc(),
              _kpi_row([
                  ("Matriculados", matriculados, C_GREEN,  _pct(matriculados,total)),
                  ("Retirados",    retirados,    C_RED,    _pct(retirados,total)),
                  ("Hombres",      hombres,      C_BLUE,   _pct(hombres,total)),
                  ("Mujeres",      mujeres,      C_PURPLE, _pct(mujeres,total)),
                  ("Extranjeros",  extranjeros,  C_AMBER,  _pct(extranjeros,total)),
              ]), spc()]

    # Especialidades
    if not df.empty and "specialty" in df.columns:
        df["_sx"] = _norm_sexo(df["sexo"]) if "sexo" in df.columns else "?"
        rows = [hdr("Especialidad","Total","Hombres","Mujeres","% Total")]
        for spec, grp in df.groupby("specialty"):
            n = len(grp); h = int((grp["_sx"]=="M").sum()); m = int((grp["_sx"]=="F").sum())
            rows.append([S(spec), S(n,align=1), S(h,align=1), S(m,align=1), S(_pct(n,total),align=1)])
        story += [_section_title("Distribucion por especialidad"), spc(),
                  simple_table(rows, [4,2,2,2,2]), spc()]

    # Asistencia KPIs
    story += [_section_title("2. Asistencia"), spc(),
              _kpi_row([
                  ("Asistencia global",  f"{pct_asist}%", C_GREEN if pct_asist>=90 else C_AMBER, "promedio"),
                  ("Bajo 85% (Legal)",   bajo_85,          C_AMBER, _pct(bajo_85,total)),
                  ("Bajo 75% (Critico)", bajo_75,          C_RED,   _pct(bajo_75,total)),
                  ("Sobre 85%",          total-bajo_85,    C_GREEN, _pct(total-bajo_85,total)),
                  ("Dias con datos",     len(df_asist_serie) if df_asist_serie is not None else "—", C_BLUE, "dias"),
              ]), spc()]

    # Cursos asistencia
    if df_asist_cursos is not None and not df_asist_cursos.empty and "pct_promedio" in df_asist_cursos.columns:
        df_ac = df_asist_cursos.copy().sort_values("pct_promedio")
        rows = [hdr("Curso","Alumnos","% Asistencia","Bajo 85%","Bajo 75%","Estado")]
        for _, r in df_ac.iterrows():
            pct = float(r["pct_promedio"])
            col = C_RED if pct<75 else (C_AMBER if pct<85 else C_GREEN)
            est = "Critico" if pct<75 else ("Legal" if pct<85 else "OK")
            rows.append([
                S(r.get("curso","")),
                S(int(r.get("n_alumnos",0)),align=1),
                S(f"{pct:.1f}%",bold=True,color=col,align=1),
                S(int(r.get("bajo_85",0)),color=C_AMBER,align=1),
                S(int(r.get("bajo_75",0)),color=C_RED,align=1),
                S(est,bold=True,color=col,align=1),
            ])
        story += [_section_title("Asistencia por curso"), spc(),
                  simple_table(rows, [2.5,2,2.5,2.5,2.5,2.5])]

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════
    # PAG 2 — ATRASOS + RIESGO
    # ══════════════════════════════════════════════════════════════════
    _sigma_header(story, "Reporte Ejecutivo · Atrasos y Riesgo", stamp)

    story += [_section_title("3. Atrasos"), spc(),
              _kpi_row([
                  ("Total atrasos",     total_atrasos,           C_RED,   "eventos"),
                  ("Alumnos afectados", alumnos_con_atr,         C_AMBER, _pct(alumnos_con_atr,total)),
                  ("Reincidentes >=3",  reincidentes,            C_RED,   _pct(reincidentes,total)),
                  ("Sin atrasos",       total-alumnos_con_atr,   C_GREEN, _pct(total-alumnos_con_atr,total)),
                  ("Prom/alumno",       round(total_atrasos/max(alumnos_con_atr,1),1), C_AMBER, "atrasos"),
              ]), spc()]

    # Top 20 atrasos
    if df_atr_alumnos is not None and not df_atr_alumnos.empty:
        top = df_atr_alumnos.sort_values("n_atrasos", ascending=False).head(20)
        rows = [hdr("Nombre","Curso","Atrasos","Justificados","Nivel")]
        for _, r in top.iterrows():
            niv = str(r.get("alerta","—"))
            col = C_RED if niv=="ALTO" else (C_AMBER if niv=="MEDIO" else C_TEXT)
            rows.append([
                S(r.get("nombre","")),
                S(r.get("curso",""),align=1),
                S(int(r.get("n_atrasos",0)),bold=True,color=C_RED,align=1),
                S(int(r.get("n_justificados",0)),align=1),
                S(niv,bold=True,color=col,align=1),
            ])
        story += [_section_title("Top 20 alumnos con mas atrasos"), spc(),
                  simple_table(rows, [6,2,2,2.5,2.5]), spc()]

    # Críticos asistencia
    story.append(_section_title("Alumnos con asistencia critica (< 75%)"))
    story.append(spc())
    if df_asist_alumnos is not None and not df_asist_alumnos.empty and "alerta" in df_asist_alumnos.columns:
        crit = df_asist_alumnos[df_asist_alumnos["alerta"]=="CRITICO"].sort_values("pct_asistencia").head(20)
        if not crit.empty:
            rows = [hdr("Nombre","Curso","% Asistencia","Presentes","Ausentes")]
            for _, r in crit.iterrows():
                pct = float(r.get("pct_asistencia",0))
                rows.append([
                    S(r.get("nombre","")),
                    S(r.get("curso",""),align=1),
                    S(f"{pct:.1f}%",bold=True,color=C_RED,align=1),
                    S(int(r.get("dias_presentes",0)),align=1),
                    S(int(r.get("dias_ausentes",0)),color=C_RED,align=1),
                ])
            story.append(simple_table(rows, [6,2,3,2.5,2.5]))
        else:
            story.append(Paragraph(_safe("Sin alumnos con asistencia critica en este corte."),
                ParagraphStyle("ok",fontName="Helvetica",fontSize=9,textColor=C_GREEN)))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════
    # PAG 3 — HISTORICO + BENCHMARKING + SEMAFORO
    # ══════════════════════════════════════════════════════════════════
    _sigma_header(story, "Reporte Ejecutivo · Historico y Semaforo", stamp)

    # Semáforo
    story += [_section_title("4. Semaforo ejecutivo"), spc()]
    indicadores = [
        ("Matricula activa",         f"{matriculados:,} alumnos",             "Normal",         C_GREEN),
        ("Asistencia global",        f"{pct_asist}%",                         "Normal" if pct_asist>=90 else "Atencion", C_GREEN if pct_asist>=90 else C_AMBER),
        ("Alumnos bajo 85%",         f"{bajo_85} ({_pct(bajo_85,total)})",    "Atencion" if bajo_85>30 else "Normal",   C_AMBER if bajo_85>30 else C_GREEN),
        ("Alumnos criticos <75%",    f"{bajo_75} ({_pct(bajo_75,total)})",    "Critico" if bajo_75>10 else "Atencion",  C_RED if bajo_75>10 else C_AMBER),
        ("Total atrasos",            f"{total_atrasos:,}",                    "En seguimiento", C_AMBER),
        ("Alumnos con atrasos",      f"{alumnos_con_atr} ({_pct(alumnos_con_atr,total)})", "En seguimiento", C_AMBER),
        ("Retirados 2026",           str(retirados),                          "Normal" if retirados==0 else "En seguimiento", C_GREEN if retirados==0 else C_AMBER),
    ]
    rows = [hdr("Indicador","Valor","Estado")]
    for label,valor,estado,color in indicadores:
        rows.append([S(label), S(valor,bold=True,color=color), S(estado,bold=True,color=color,align=1)])
    story.append(simple_table(rows,[8,5,5]))

    _sigma_footer(story,"Reporte Ejecutivo")
    doc.build(story)
    return buf.getvalue()



def render_pdf_preview(pdf_bytes: bytes, height: int = 680) -> None:
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="{height}" type="application/pdf" '
        f'style="border:none;border-radius:8px;"></iframe>',
        unsafe_allow_html=True,
    )


def show_pretty_table(df: pd.DataFrame, max_rows: int = 100, height: int = 320) -> None:
    if df is None or df.empty:
        st.info("Sin datos disponibles.")
        return
    view = df.head(max_rows).copy()
    # Formatear columnas de porcentaje automáticamente
    for col in view.columns:
        col_lower = col.lower()
        if col_lower in ("pct", "pct_asistencia", "pct_justificados", "pct_promedio"):
            view[col] = pd.to_numeric(view[col], errors="coerce").apply(
                lambda v: f"{v:.1f}%" if pd.notna(v) else "—"
            )
        elif col_lower in ("total", "count", "alumnos", "n_atrasos", "dias_con_atraso"):
            view[col] = pd.to_numeric(view[col], errors="coerce").apply(
                lambda v: f"{int(v):,}" if pd.notna(v) else "—"
            )
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        height=height,
    )


# ─────────────────────────────────────────────────────────────────────
# PDF OBSERVACIONES
# ─────────────────────────────────────────────────────────────────────

def generate_pdf_observaciones(
    df_eventos:  pd.DataFrame | None,
    df_alumnos:  pd.DataFrame | None,
    df_cursos:   pd.DataFrame | None,
    df_docentes: pd.DataFrame | None,
    df_serie:    pd.DataFrame | None,
    corte: str,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm)
    story: list = []
    _sigma_header(story, "Reporte Ejecutivo · Observaciones", corte)

    if df_eventos is None or df_eventos.empty:
        story.append(Paragraph("Sin datos de observaciones disponibles.",
            ParagraphStyle("na", fontName="Helvetica", fontSize=10, textColor=C_MUTED)))
        _sigma_footer(story, "Observaciones")
        doc.build(story)
        return buf.getvalue()

    # ── Métricas globales ─────────────────────────────────────────────
    total_obs   = len(df_eventos)
    n_alumnos   = int(df_eventos["rut_norm"].nunique()) if "rut_norm" in df_eventos.columns else 0
    n_cursos    = int(df_eventos["curso"].nunique())    if "curso"    in df_eventos.columns else 0
    n_neg       = int((df_eventos["tipo"] == "NEG").sum()) if "tipo" in df_eventos.columns else 0
    n_pos       = int((df_eventos["tipo"] == "POS").sum()) if "tipo" in df_eventos.columns else 0
    n_neu       = int((df_eventos["tipo"] == "OBS").sum()) if "tipo" in df_eventos.columns else 0
    pct_neg     = _pct(n_neg, total_obs)

    criticos = altos = 0
    if df_alumnos is not None and not df_alumnos.empty and "alerta" in df_alumnos.columns:
        criticos = int((df_alumnos["alerta"] == "CRITICO").sum())
        altos    = int((df_alumnos["alerta"] == "ALTO").sum())

    story.append(_section_title("Indicadores globales", C_RED))
    story.append(Spacer(1, 0.15*cm))
    story.append(_kpi_row([
        ("Observaciones",      total_obs, C_BLUE,   f"{n_alumnos} alumnos involucrados"),
        ("Negativas",          n_neg,     C_RED,    pct_neg + " del total"),
        ("Neutras",            n_neu,     C_BLUE,   _pct(n_neu, total_obs)),
        ("Positivas",          n_pos,     C_GREEN,  _pct(n_pos, total_obs)),
    ]))
    story.append(Spacer(1, 0.2*cm))
    story.append(_kpi_row([
        ("Cursos afectados",   n_cursos,  C_BLUE,   ""),
        ("Criticos (>=5 neg)", criticos,  C_RED,    _pct(criticos, n_alumnos)),
        ("Altos (>=3 neg)",    altos,     C_AMBER,  _pct(altos, n_alumnos)),
        ("Docentes",           int(df_docentes["docente"].nunique()) if df_docentes is not None and not df_docentes.empty and "docente" in df_docentes.columns else 0,
                                          C_PURPLE,  "registraron observaciones"),
    ]))
    story.append(Spacer(1, 0.4*cm))

    # ── Alumnos críticos y altos ──────────────────────────────────────
    if df_alumnos is not None and not df_alumnos.empty and "alerta" in df_alumnos.columns:
        df_risk = df_alumnos[df_alumnos["alerta"].isin(["CRITICO", "ALTO"])].copy()
        if not df_risk.empty:
            story.append(_section_title("Alumnos criticos y altos", C_RED))
            story.append(Spacer(1, 0.1*cm))
            df_risk = df_risk.sort_values("obs_negativas", ascending=False).reset_index(drop=True)
            cols_r = [c for c in ["nombre","curso","total_obs","obs_negativas",
                                   "obs_positivas","pct_negativas","alerta"] if c in df_risk.columns]
            df_r = df_risk[cols_r].rename(columns={
                "nombre":"Nombre","curso":"Curso","total_obs":"Total",
                "obs_negativas":"Negativas","obs_positivas":"Positivas",
                "pct_negativas":"% Neg.","alerta":"Alerta",
            })
            if "% Neg." in df_r.columns:
                df_r["% Neg."] = df_r["% Neg."].apply(lambda v: f"{v:.1f}%")
            story.append(_df_to_table(df_r))
            story.append(Spacer(1, 0.4*cm))

    # ── Top alumnos con más observaciones ─────────────────────────────
    if df_alumnos is not None and not df_alumnos.empty:
        story.append(_section_title("Top 20 alumnos por observaciones"))
        story.append(Spacer(1, 0.1*cm))
        sort_col = "total_obs" if "total_obs" in df_alumnos.columns else df_alumnos.columns[0]
        df_top = df_alumnos.sort_values(sort_col, ascending=False).head(20).reset_index(drop=True)
        cols_t = [c for c in ["nombre","curso","total_obs","obs_negativas",
                               "obs_neutras","pct_negativas","alerta"] if c in df_top.columns]
        df_t = df_top[cols_t].rename(columns={
            "nombre":"Nombre","curso":"Curso","total_obs":"Total",
            "obs_negativas":"Negativas","obs_neutras":"Neutras",
            "pct_negativas":"% Neg.","alerta":"Alerta",
        })
        if "% Neg." in df_t.columns:
            df_t["% Neg."] = df_t["% Neg."].apply(lambda v: f"{v:.1f}%")
        story.append(_df_to_table(df_t))
        story.append(Spacer(1, 0.4*cm))

    # ── Página 2: Por curso + por docente ─────────────────────────────
    story.append(PageBreak())
    _sigma_header(story, "Analisis por curso y docente · Observaciones", corte)

    if df_cursos is not None and not df_cursos.empty:
        story.append(_section_title("Distribucion por curso"))
        story.append(Spacer(1, 0.1*cm))
        df_c = df_cursos.copy().sort_values("total_obs", ascending=False)
        cols_c = [c for c in ["curso","total_obs","alumnos_unicos","obs_negativas",
                               "obs_positivas","pct_negativas","promedio_por_alumno"] if c in df_c.columns]
        df_c_show = df_c[cols_c].rename(columns={
            "curso":"Curso","total_obs":"Total","alumnos_unicos":"Alumnos",
            "obs_negativas":"Negativas","obs_positivas":"Positivas",
            "pct_negativas":"% Neg.","promedio_por_alumno":"Prom/Alumno",
        })
        if "% Neg." in df_c_show.columns:
            df_c_show["% Neg."] = df_c_show["% Neg."].apply(lambda v: f"{v:.1f}%")
        if "Prom/Alumno" in df_c_show.columns:
            df_c_show["Prom/Alumno"] = df_c_show["Prom/Alumno"].apply(lambda v: f"{v:.1f}")
        story.append(_df_to_table(df_c_show,
            col_widths=[2.5*cm, 2.0*cm, 2.0*cm, 2.5*cm, 2.5*cm, 2.0*cm, 2.5*cm]))
        story.append(Spacer(1, 0.4*cm))

    if df_docentes is not None and not df_docentes.empty:
        story.append(_section_title("Observaciones por docente"))
        story.append(Spacer(1, 0.1*cm))
        df_d = df_docentes.copy().sort_values("total_obs", ascending=False)
        cols_d = [c for c in ["docente","total_obs","alumnos_unicos","obs_negativas",
                               "obs_positivas","obs_neutras"] if c in df_d.columns]
        df_d_show = df_d[cols_d].rename(columns={
            "docente":"Docente","total_obs":"Total","alumnos_unicos":"Alumnos",
            "obs_negativas":"Negativas","obs_positivas":"Positivas","obs_neutras":"Neutras",
        })
        story.append(_df_to_table(df_d_show,
            col_widths=[5.0*cm, 2.0*cm, 2.0*cm, 2.5*cm, 2.5*cm, 2.5*cm]))
        story.append(Spacer(1, 0.4*cm))

    # ── Página 3: Serie diaria + Nómina completa ──────────────────────
    if df_serie is not None and not df_serie.empty:
        story.append(PageBreak())
        _sigma_header(story, "Serie Diaria · Observaciones", corte)

        story.append(_section_title("Observaciones por dia"))
        story.append(Spacer(1, 0.1*cm))
        df_s = df_serie.copy().sort_values("fecha", ascending=False) if "fecha" in df_serie.columns else df_serie.copy()
        cols_s = [c for c in ["fecha","total_dia","alumnos_dia","negativas_dia","pct_negativas_dia"] if c in df_s.columns]
        df_s_show = df_s[cols_s].rename(columns={
            "fecha":"Fecha","total_dia":"Total","alumnos_dia":"Alumnos",
            "negativas_dia":"Negativas","pct_negativas_dia":"% Neg.",
        })
        if "% Neg." in df_s_show.columns:
            df_s_show["% Neg."] = df_s_show["% Neg."].apply(lambda v: f"{v:.1f}%")
        story.append(_df_to_table(df_s_show))
        story.append(Spacer(1, 0.4*cm))

        # Estadísticas de la serie
        if "total_dia" in df_serie.columns:
            prom_d   = round(df_serie["total_dia"].mean(), 1)
            max_d    = int(df_serie["total_dia"].max())
            fecha_max = str(df_serie.loc[df_serie["total_dia"].idxmax(), "fecha"]) if "fecha" in df_serie.columns else "—"
            story.append(Paragraph(
                f"Promedio diario: {prom_d} observaciones. "
                f"Dia de mayor actividad: {fecha_max} con {max_d} observaciones.",
                ParagraphStyle("stat", fontName="Helvetica", fontSize=9,
                               textColor=C_MUTED, leading=13, spaceAfter=8),
            ))

    _sigma_footer(story, "Observaciones")
    doc.build(story)
    return buf.getvalue()