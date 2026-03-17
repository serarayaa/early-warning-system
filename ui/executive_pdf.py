from __future__ import annotations

import base64
import io
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.config.settings import PATHS


DEFAULT_STATUS_CONFIG: dict[str, Any] = {
    "global": {
        "level_high": 5,
        "level_medium": 2,
        "messages": {
            "high": "Se identifican indicadores de riesgo altos que requieren accion inmediata.",
            "medium": "Se observan señales de alerta moderadas; se recomienda seguimiento semanal.",
            "low": "El corte presenta comportamiento estable en los indicadores principales.",
        },
    },
    "asistencia": {
        "asistencia_global_pct_high": 75,
        "asistencia_global_pct_medium": 85,
        "bajo_75_min": 0,
        "bajo_85_min": 15,
        "tendencia_baja_min": 10,
    },
    "atrasos": {
        "criticos_min": 0,
        "reincidentes_min": 8,
        "pct_justificados_high": 35,
        "pct_justificados_medium": 50,
    },
    "matricula": {
        "retirados_high": 15,
        "retirados_medium": 5,
        "transferencias_min": 10,
    },
}


def _find_school_logo() -> Path | None:
    root = Path(__file__).resolve().parents[1]
    candidates = [
        root / "assets" / "logo_establecimiento.png",
        root / "assets" / "logo_establecimiento.jpg",
        root / "assets" / "logo_liceo.png",
        root / "assets" / "logo_liceo.jpg",
        root / "assets" / "logo_duoc.png",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def _deep_merge(base: dict[str, Any], custom: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for k, v in custom.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


@lru_cache(maxsize=1)
def _load_status_config() -> dict[str, Any]:
    cfg_path = PATHS.raw_config / "pdf_status_thresholds.json"
    if not cfg_path.exists():
        return DEFAULT_STATUS_CONFIG

    try:
        payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_STATUS_CONFIG

    if not isinstance(payload, dict):
        return DEFAULT_STATUS_CONFIG

    return _deep_merge(DEFAULT_STATUS_CONFIG, payload)


def _fmt_value(v: Any) -> str:
    if pd.isna(v):
        return "-"
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-9:
            return f"{int(round(v)):,}"
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _to_float(v: Any) -> float | None:
    try:
        if pd.isna(v):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        txt = str(v).strip().replace("%", "").replace(",", "")
        if txt == "":
            return None
        return float(txt)
    except Exception:
        return None


def _score_from_metric(metric_key: str, metric_value: float) -> int:
    k = metric_key.lower()
    score = 0

    simple_rules = [
        ("critico", 0, 3),
        ("reincidente", 10, 2),
        ("bajo_75", 0, 3),
        ("bajo_85", 10, 2),
        ("retirado", 5, 2),
    ]
    for needle, threshold, points in simple_rules:
        if needle in k and metric_value > threshold:
            score += points

    if "asistencia_global_pct" in k:
        if metric_value < 75:
            score += 3
        elif metric_value < 85:
            score += 2

    if "pct_justificados" in k and metric_value < 50:
        score += 1

    return score


def _score_asistencia(metric_key: str, metric_value: float) -> int:
    cfg = _load_status_config()["asistencia"]
    k = metric_key.lower()
    score = 0

    if "asistencia_global_pct" in k:
        if metric_value < float(cfg["asistencia_global_pct_high"]):
            score += 4
        elif metric_value < float(cfg["asistencia_global_pct_medium"]):
            score += 2

    if "bajo_75" in k and metric_value > float(cfg["bajo_75_min"]):
        score += 3
    if "bajo_85" in k and metric_value >= float(cfg["bajo_85_min"]):
        score += 2
    if "tendencia_baja" in k and metric_value >= float(cfg["tendencia_baja_min"]):
        score += 2

    return score


def _score_atrasos(metric_key: str, metric_value: float) -> int:
    cfg = _load_status_config()["atrasos"]
    k = metric_key.lower()
    score = 0

    if "critico" in k and metric_value > float(cfg["criticos_min"]):
        score += 4
    if "reincidente" in k and metric_value >= float(cfg["reincidentes_min"]):
        score += 2
    if "pct_justificados" in k:
        if metric_value < float(cfg["pct_justificados_high"]):
            score += 2
        elif metric_value < float(cfg["pct_justificados_medium"]):
            score += 1

    return score


def _score_matricula(metric_key: str, metric_value: float) -> int:
    cfg = _load_status_config()["matricula"]
    k = metric_key.lower()
    score = 0

    if "retirado" in k:
        if metric_value >= float(cfg["retirados_high"]):
            score += 4
        elif metric_value >= float(cfg["retirados_medium"]):
            score += 2

    if "transferencia" in k and metric_value >= float(cfg["transferencias_min"]):
        score += 1

    return score


def _infer_status(module_name: str, kpis: dict[str, Any]) -> tuple[str, str, str]:
    module = module_name.strip().lower()
    gcfg = _load_status_config()["global"]
    score = 0
    for key, value in kpis.items():
        n = _to_float(value)
        if n is not None:
            score += _score_from_metric(str(key), n)

            if "asistencia" in module:
                score += _score_asistencia(str(key), n)
            elif "atraso" in module:
                score += _score_atrasos(str(key), n)
            elif "matricula" in module or "matrícula" in module:
                score += _score_matricula(str(key), n)

    high = int(gcfg["level_high"])
    medium = int(gcfg["level_medium"])
    msgs = gcfg["messages"]

    if score >= high:
        return ("ALTO", "#b91c1c", str(msgs["high"]))
    if score >= medium:
        return ("MEDIO", "#b45309", str(msgs["medium"]))
    return ("BAJO", "#166534", str(msgs["low"]))


def _dedupe_pairs(pairs: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    seen: set[str] = set()
    ordered: list[tuple[str, Any]] = []
    for key, value in pairs:
        if key in seen:
            continue
        seen.add(key)
        ordered.append((key, value))
    return ordered


def _build_hallazgos(kpis: dict[str, Any], tables: list[tuple[str, pd.DataFrame]]) -> list[str]:
    hallazgos: list[str] = []

    risk_priority = ["critico", "reincidente", "bajo_75", "bajo_85", "retirado", "tendencia_baja"]
    prioritized = [
        (str(key), value)
        for needle in risk_priority
        for key, value in kpis.items()
        if needle in str(key).lower()
    ]
    fallback = [(str(key), value) for key, value in kpis.items()]
    selected = _dedupe_pairs(prioritized + fallback)[:3]

    for label, value in selected:
        hallazgos.append(f"{label.replace('_', ' ').title()}: {_fmt_value(value)}")

    if tables:
        non_empty = [(name, df) for name, df in tables if df is not None and not df.empty]
        if non_empty:
            first_name, first_df = non_empty[0]
            hallazgos.append(f"{first_name}: {len(first_df):,} registros considerados en el reporte.")

    return hallazgos[:4]


def _df_to_pdf_table(df: pd.DataFrame, max_rows: int = 25, max_cols: int = 8) -> Table:
    view = df.copy()
    if len(view.columns) > max_cols:
        view = view.iloc[:, :max_cols].copy()

    data = [list(view.columns)]
    if not view.empty:
        body = view.head(max_rows)
        for _, row in body.iterrows():
            data.append([_fmt_value(v) for v in row.values])

    col_count = max(1, len(data[0]))
    col_w = (A4[0] - 3 * cm) / col_count
    table = Table(data, colWidths=[col_w] * col_count, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f3a5b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTSIZE", (0, 1), (-1, -1), 7.5),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#0f3a5b")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d6dde4")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
            ]
        )
    )
    return table


def _kpi_cards_table(kpis: dict[str, Any], cards_per_row: int = 3) -> Table:
    label_style = ParagraphStyle(
        "kpi_label",
        fontName="Helvetica",
        fontSize=8,
        textColor=colors.HexColor("#5b6b7a"),
        leading=10,
    )
    value_style = ParagraphStyle(
        "kpi_value",
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#0b2740"),
        leading=14,
    )

    cards: list[Table] = []
    for key, value in kpis.items():
        card = Table(
            [[Paragraph(str(key).replace("_", " ").title(), label_style)], [Paragraph(_fmt_value(value), value_style)]],
            colWidths=[(A4[0] - 3.5 * cm) / cards_per_row],
        )
        card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef5fb")),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#c8d9e8")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ]
            )
        )
        cards.append(card)

    rows: list[list[Any]] = []
    for i in range(0, len(cards), cards_per_row):
        row = cards[i : i + cards_per_row]
        while len(row) < cards_per_row:
            row.append("")
        rows.append(row)

    grid = Table(rows, colWidths=[(A4[0] - 3.5 * cm) / cards_per_row] * cards_per_row, hAlign="LEFT")
    grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return grid


def generate_executive_pdf(
    module_name: str,
    corte: str,
    kpis: dict[str, Any],
    tables: list[tuple[str, pd.DataFrame]],
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    title = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=15, textColor=colors.white)
    subtitle = ParagraphStyle("subtitle", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#d9e7f3"))
    cover_title = ParagraphStyle("cover_title", fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor("#0b2740"))
    cover_subtitle = ParagraphStyle("cover_subtitle", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#475569"))
    section = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=10.5, textColor=colors.HexColor("#0f3a5b"))
    section_hint = ParagraphStyle("section_hint", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#64748b"))
    bullet = ParagraphStyle("bullet", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#1f2937"), leading=13)

    story = []
    logo_path = _find_school_logo()
    header_text = [Paragraph(f"SIGMA | Reporte Ejecutivo {module_name}", title), Paragraph(f"Corte: {corte}  |  Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle)]

    if logo_path is not None:
        logo = RLImage(str(logo_path), width=2.1 * cm, height=2.1 * cm)
        header = Table([[logo, header_text]], colWidths=[2.5 * cm, A4[0] - 5.5 * cm])
        header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0b2740")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(header)
    else:
        header = Table([[header_text]], colWidths=[A4[0] - 3 * cm])
        header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0b2740")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(header)

    story.append(Spacer(1, 0.3 * cm))

    if kpis:
        status, status_color, status_text = _infer_status(module_name, kpis)
        hallazgos = _build_hallazgos(kpis, tables)

        story.append(Paragraph("Portada Ejecutiva", cover_title))
        story.append(Spacer(1, 0.12 * cm))
        story.append(Paragraph(f"Modulo: {module_name} | Corte: {corte}", cover_subtitle))
        story.append(Spacer(1, 0.35 * cm))

        semaforo = Table([[f"Semaforo del corte: {status}"], [status_text]], colWidths=[A4[0] - 3 * cm])
        semaforo.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(status_color)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f8fafc")),
                    ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#334155")),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, 1), 9),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cbd5e1")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ]
            )
        )
        story.append(semaforo)

        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph("Hallazgos clave", section))
        story.append(Spacer(1, 0.08 * cm))
        for item in hallazgos:
            story.append(Paragraph(f"- {item}", bullet))
            story.append(Spacer(1, 0.04 * cm))

        story.append(Spacer(1, 0.25 * cm))
        story.append(PageBreak())

    if kpis:
        story.append(Paragraph("Resumen Ejecutivo", section))
        story.append(Paragraph("Indicadores clave del corte actual", section_hint))
        story.append(Spacer(1, 0.1 * cm))
        story.append(_kpi_cards_table(kpis, cards_per_row=3))
        story.append(Spacer(1, 0.35 * cm))

    for title_text, df in tables:
        if df is None or df.empty:
            continue
        story.append(Paragraph(title_text, section))
        if len(df.columns) > 8:
            story.append(Paragraph("Se muestran las primeras 8 columnas para una lectura mas clara en PDF.", section_hint))
        story.append(Spacer(1, 0.1 * cm))
        story.append(_df_to_pdf_table(df, max_rows=25))
        story.append(Spacer(1, 0.22 * cm))

    doc.build(story)
    return buf.getvalue()


def render_pdf_preview(pdf_bytes: bytes, height: int = 640) -> None:
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="{height}" type="application/pdf"></iframe>',
        unsafe_allow_html=True,
    )


def show_pretty_table(df: pd.DataFrame, max_rows: int = 100, height: int = 320) -> None:
    if df is None:
        st.info("Sin datos disponibles.")
        return

    view = df.head(max_rows).copy()
    st.dataframe(view, use_container_width=True, hide_index=True, height=height)
