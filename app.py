"""
SIGMA — Sistema Integrado de Gestión y Monitoreo Académico
app.py — Interfaz principal Streamlit
"""

from datetime import datetime
from pathlib import Path

import streamlit as st

from ui.enrollment_data import list_enrollment_dates, load_enrollment_bundle
from ui.matricula_page import render_matricula_page
from ui.asistencia_page import render_asistencia_page
from ui.atrasos_page import render_atrasos_page


def _find_school_logo() -> Path | None:
    root = Path(__file__).resolve().parent
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


# ─────────────────────────────────────────────
# Configuración de página
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="SIGMA",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CSS — Identidad visual SIGMA
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500&display=swap');

/* ── Reset y base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, .stApp {
    background: #080c14 !important;
    color: #e2e8f0 !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* ── Contenedor principal ── */
.block-container {
    max-width: 1280px !important;
    padding-top: 1rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    margin: 0 auto !important;
}

/* ── Ocultar elementos Streamlit ── */
#MainMenu, footer, header { visibility: hidden !important; }
.stDeployButton { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0d1220 !important;
    border-right: 1px solid rgba(99,179,237,0.1) !important;
}
[data-testid="stSidebar"] * { color: #cbd5e0 !important; }

/* ── Logo SIGMA ── */
.sigma-logo {
    font-family: 'Syne', sans-serif;
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -1px;
    background: linear-gradient(135deg, #63b3ed 0%, #76e4f7 50%, #9ae6b4 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1;
}
.sigma-tagline {
    font-family: 'DM Mono', monospace;
    font-size: 0.6rem;
    color: #4a5568;
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-top: 4px;
}

/* ── Header principal ── */
.sigma-header {
    display: flex;
    align-items: flex-end;
    gap: 16px;
    padding: 20px 0 18px 0;
    border-bottom: 1px solid rgba(99,179,237,0.12);
    margin-bottom: 24px;
}

/* ── KPI Cards ── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 220px));
    gap: 12px;
    margin-bottom: 24px;
}
.kpi-card {
    background: linear-gradient(135deg, #0d1829 0%, #0a1520 100%);
    border: 1px solid rgba(99,179,237,0.12);
    border-radius: 12px;
    padding: 18px 18px 14px 18px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s, transform 0.2s;
}
.kpi-card:hover {
    border-color: rgba(99,179,237,0.35);
    transform: translateY(-2px);
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #63b3ed, #76e4f7);
}
.kpi-card.green::before { background: linear-gradient(90deg, #68d391, #9ae6b4); }
.kpi-card.amber::before { background: linear-gradient(90deg, #f6ad55, #fbd38d); }
.kpi-card.red::before   { background: linear-gradient(90deg, #fc8181, #feb2b2); }
.kpi-card.cyan::before  { background: linear-gradient(90deg, #76e4f7, #bee3f8); }

.kpi-label {
    font-family: 'DM Mono', monospace;
    font-size: 0.62rem;
    color: #4a5568;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 8px;
}
.kpi-value {
    font-family: 'Syne', sans-serif;
    font-size: 2.1rem;
    font-weight: 800;
    color: #e2e8f0;
    line-height: 1;
}
.kpi-delta {
    font-family: 'DM Mono', monospace;
    font-size: 0.65rem;
    margin-top: 5px;
}
.kpi-delta.up   { color: #68d391; }
.kpi-delta.down { color: #fc8181; }
.kpi-delta.neu  { color: #4a5568; }

/* ── Sección títulos ── */
.section-title {
    font-family: 'Syne', sans-serif;
    font-size: 0.78rem;
    font-weight: 700;
    color: #63b3ed;
    text-transform: uppercase;
    letter-spacing: 3px;
    margin-bottom: 14px;
    margin-top: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: rgba(99,179,237,0.15);
}

/* ── Panel ── */
.sigma-panel {
    background: #0d1220;
    border: 1px solid rgba(99,179,237,0.1);
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 14px;
}

/* ── Tabla ── */
[data-testid="stDataFrame"] {
    border: 1px solid rgba(99,179,237,0.1) !important;
    border-radius: 10px !important;
    overflow: hidden !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] > div:first-child {
    border-bottom: 1px solid rgba(99,179,237,0.12) !important;
    gap: 2px !important;
}
button[data-baseweb="tab"] {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    color: #4a5568 !important;
    border-radius: 8px 8px 0 0 !important;
    padding: 8px 16px !important;
    transition: color 0.2s !important;
}
button[data-baseweb="tab"]:hover { color: #a0aec0 !important; }
button[data-baseweb="tab"][aria-selected="true"] {
    color: #63b3ed !important;
    border-bottom: 2px solid #63b3ed !important;
    background: rgba(99,179,237,0.05) !important;
}

/* ── Inputs ── */
[data-testid="stTextInput"] input {
    background: #0d1220 !important;
    border: 1px solid rgba(99,179,237,0.2) !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.85rem !important;
}
[data-testid="stSelectbox"] > div > div {
    background: #0d1220 !important;
    border: 1px solid rgba(99,179,237,0.2) !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
    font-size: 0.85rem !important;
}

/* ── Alertas ── */
.sigma-alert {
    background: rgba(246,173,85,0.08);
    border: 1px solid rgba(246,173,85,0.2);
    border-left: 3px solid #f6ad55;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.82rem;
    color: #fbd38d;
    margin-bottom: 10px;
    font-family: 'DM Sans', sans-serif;
}
.sigma-alert.info {
    background: rgba(99,179,237,0.06);
    border-color: rgba(99,179,237,0.15);
    border-left-color: #63b3ed;
    color: #bee3f8;
}
.sigma-alert.success {
    background: rgba(104,211,145,0.06);
    border-color: rgba(104,211,145,0.15);
    border-left-color: #68d391;
    color: #9ae6b4;
}
.sigma-alert.danger {
    background: rgba(252,129,129,0.06);
    border-color: rgba(252,129,129,0.15);
    border-left-color: #fc8181;
    color: #feb2b2;
}

/* ── Badge ── */
.sigma-badge {
    display: inline-block;
    font-family: 'DM Mono', monospace;
    font-size: 0.6rem;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid rgba(99,179,237,0.2);
    color: #63b3ed;
    background: rgba(99,179,237,0.06);
    letter-spacing: 1px;
}
.sigma-badge.amber {
    border-color: rgba(246,173,85,0.3);
    color: #f6ad55;
    background: rgba(246,173,85,0.06);
}

/* ── Stat row ── */
.stat-row {
    display: flex;
    gap: 32px;
    flex-wrap: wrap;
}
.stat-item { display: flex; flex-direction: column; gap: 3px; }
.stat-item .s-label {
    font-family: 'DM Mono', monospace;
    font-size: 0.58rem;
    color: #4a5568;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}
.stat-item .s-value {
    font-family: 'Syne', sans-serif;
    font-size: 1.15rem;
    font-weight: 700;
    color: #e2e8f0;
}

/* ── Nav sidebar ── */
.nav-module {
    padding: 7px 10px;
    border-radius: 8px;
    font-size: 0.8rem;
    color: #4a5568;
    margin-bottom: 3px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.nav-module.active {
    background: rgba(99,179,237,0.08);
    color: #63b3ed;
    border: 1px solid rgba(99,179,237,0.15);
}
.nav-module.soon { opacity: 0.4; font-size: 0.75rem; }

/* ── Progress bar ── */
.progress-bar-wrap {
    background: rgba(99,179,237,0.08);
    border-radius: 4px;
    height: 5px;
    overflow: hidden;
    margin-top: 5px;
}
.progress-bar-fill {
    height: 100%;
    border-radius: 4px;
    background: linear-gradient(90deg, #63b3ed, #76e4f7);
}

/* ── Record count ── */
.record-count {
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    color: #4a5568;
    margin-bottom: 10px;
}
.record-count span { color: #63b3ed; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #080c14; }
::-webkit-scrollbar-thumb { background: rgba(99,179,237,0.2); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(99,179,237,0.4); }

/* ── Nav buttons sidebar ── */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: 8px !important;
    color: #4a5568 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    padding: 7px 10px !important;
    text-align: left !important;
    width: 100% !important;
    transition: all 0.15s !important;
    margin-bottom: 2px !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    color: #a0aec0 !important;
    background: rgba(99,179,237,0.04) !important;
    border-color: rgba(99,179,237,0.08) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: rgba(99,179,237,0.08) !important;
    color: #63b3ed !important;
    border-color: rgba(99,179,237,0.2) !important;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
with st.sidebar:
    school_logo = _find_school_logo()
    if school_logo is not None:
        st.image(str(school_logo), use_container_width=True)

    st.markdown("""
    <div style="padding:6px 0 18px 0">
        <div class="sigma-logo">SIGMA</div>
        <div class="sigma-tagline">Sistema Integrado de Gestión</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Módulos</div>', unsafe_allow_html=True)

    if "modulo" not in st.session_state:
        st.session_state.modulo = "matricula"

    def _nav_btn(key: str, icon: str, label: str, soon: bool = False):
        is_active = st.session_state.modulo == key
        if soon:
            st.markdown(
                f'<div class="nav-module soon">{icon} {label} '
                f'<span class="sigma-badge amber">Pronto</span></div>',
                unsafe_allow_html=True,
            )
        else:
            if st.button(
                f"{icon} {label}",
                key=f"nav_{key}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.modulo = key
                st.rerun()

    _nav_btn("matricula", "⚡", "Matrícula")
    _nav_btn("asistencia", "📅", "Asistencia")
    _nav_btn("atrasos", "⏰", "Atrasos")
    _nav_btn("notas", "📝", "Notas", soon=True)
    _nav_btn("dia", "🧠", "DIA / Socioemocional", soon=True)
    _nav_btn("observaciones", "📋", "Observaciones", soon=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Corte</div>', unsafe_allow_html=True)

    available = list_enrollment_dates()
    if not available:
        st.error("Sin datos en data/gold/enrollment")
        st.stop()

    available_sorted = sorted(available, reverse=True)
    stamp = st.selectbox(
        "Fecha",
        available_sorted,
        index=0,
        label_visibility="collapsed",
    )

    prev_idx = available_sorted.index(stamp)
    prev_stamp = available_sorted[prev_idx + 1] if prev_idx + 1 < len(available_sorted) else None

    try:
        label = datetime.strptime(stamp, "%Y%m%d").strftime("%d %b %Y").upper()
    except Exception:
        label = stamp

    st.markdown(
        f'<div style="font-family:DM Mono,monospace;font-size:0.7rem;color:#4a5568;'
        f'background:rgba(99,179,237,0.06);border:1px solid rgba(99,179,237,0.15);'
        f'border-radius:6px;padding:4px 10px;letter-spacing:1px">📅 {label}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div style="font-family:DM Mono,monospace;font-size:0.58rem;color:#2d3748;text-align:center">'
        f"SIGMA v1.0 · "
        f"{ {'matricula': 'Matrícula', 'asistencia': 'Asistencia', 'atrasos': 'Atrasos', 'notas': 'Notas', 'dia': 'DIA / Socioemocional', 'observaciones': 'Observaciones'}.get(st.session_state.get('modulo', 'matricula'), 'Matrícula') }"
        '</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────
# Cargar datos
# ─────────────────────────────────────────────
bundle = load_enrollment_bundle(stamp=stamp, prev_stamp=prev_stamp)

metrics = bundle["metrics"]
df_current = bundle["df_current"]
df_demo = bundle["df_demo"]
df_comunas = bundle["df_comunas"]
df_nacs = bundle["df_nacs"]
df_specs = bundle["df_specs"]
df_anomalies = bundle["df_anomalies"]
df_master = bundle["df_master"]
prev_metrics = bundle["prev_metrics"]
df_transfers = bundle["df_transfers"]
df_diff = bundle["df_diff"]
df_desiste_curr = bundle["df_desiste_curr"]
df_desiste_prev = bundle["df_desiste_prev"]

df_prev_current = bundle["df_prev_current"]

# ─────────────────────────────────────────────
# Enrutador de módulos
# ─────────────────────────────────────────────
_modulo = st.session_state.get("modulo", "matricula")

if _modulo == "matricula":
    render_matricula_page(
        stamp=stamp,
        metrics=metrics,
        prev_metrics=prev_metrics,
        df_current=df_current,
        df_prev_current=df_prev_current,
        df_demo=df_demo,
        df_comunas=df_comunas,
        df_nacs=df_nacs,
        df_specs=df_specs,
    )

elif _modulo == "asistencia":
    render_asistencia_page()

elif _modulo == "atrasos":
    render_atrasos_page()

else:
    st.markdown("""
    <div class="sigma-header">
        <div>
            <div class="sigma-logo" style="font-size:1.5rem">SIGMA</div>
            <div class="sigma-tagline">Sistema Integrado de Gestión y Monitoreo Académico</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="sigma-alert info">
        Este módulo aún está en construcción. Pronto estará disponible en SIGMA.
    </div>
    """, unsafe_allow_html=True)