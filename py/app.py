import json
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

DATA_FILE = Path(__file__).parent.parent / "data" / "detections.json"

# ── i18n ─────────────────────────────────────────────────────────────────────
TEXTS = {
    "es": {
        "page_title":     "GeoVigil Analytics",
        "title":          "GeoVigil Analytics",
        "subtitle":       "Detección de pistas clandestinas · Perú",
        "caption":        "Resultados del análisis por IA de imágenes satelitales",
        "filter_header":  "Filtros",
        "slider_label":   "Confianza mínima (%)",
        "legend_title":   "Nivel de confianza",
        "legend_high":    "Alta ≥ 85%",
        "legend_mid":     "Media 70–84%",
        "legend_low":     "Baja < 70%",
        "metric_label":   "Detecciones visibles",
        "table_expander": "Lista de detecciones",
        "col_lat":        "Latitud",
        "col_lon":        "Longitud",
        "col_conf":       "Confianza",
        "col_date":       "Fecha de detección",
        "popup_conf":     "Confianza",
        "popup_date":     "Detectado",
        "popup_coord":    "Coord.",
        "lang_toggle":    "🇬🇧 English",
        "last_update":    "Último lote",
        "data_status":    "Estado",
        "status_demo":    "Demo — datos simulados",
        "status_live":    "En vivo — datos reales",
        "filters_title":  "⚙️ Filtros",
        "legend_active":       "Activo (confirmado en 3 meses)",
        "legend_unconfirmed":  "No confirmado (3–6 meses)",
        "popup_first":    "Primera detección",
        "popup_last":     "Última confirmación",
        "popup_source":   "Fuente",
    },
    "en": {
        "page_title":     "GeoVigil Analytics",
        "title":          "GeoVigil Analytics",
        "subtitle":       "Clandestine airstrip detection · Peru",
        "caption":        "AI satellite imagery analysis results",
        "filter_header":  "Filters",
        "slider_label":   "Minimum confidence (%)",
        "legend_title":   "Confidence level",
        "legend_high":    "High ≥ 85%",
        "legend_mid":     "Medium 70–84%",
        "legend_low":     "Low < 70%",
        "metric_label":   "Visible detections",
        "table_expander": "Detection list",
        "col_lat":        "Latitude",
        "col_lon":        "Longitude",
        "col_conf":       "Confidence",
        "col_date":       "Detected at",
        "popup_conf":     "Confidence",
        "popup_date":     "Detected",
        "popup_coord":    "Coord.",
        "lang_toggle":    "🇪🇸 Español",
        "last_update":    "Last batch",
        "data_status":    "Status",
        "status_demo":    "Demo — simulated data",
        "status_live":    "Live — real data",
        "legend_active":       "Active (confirmed within 3 months)",
        "legend_unconfirmed":  "Unconfirmed (3–6 months)",
        "popup_first":    "First detected",
        "popup_last":     "Last confirmed",
        "popup_source":   "Source",
        "filters_title":  "⚙️ Filters",
    },
}

# ── Detection data ────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_detections() -> tuple[pd.DataFrame, str, bool]:
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    df = pd.DataFrame(raw["detections"])
    return df, raw.get("generated_at", ""), raw.get("is_demo", True)

DETECTIONS, _GENERATED_AT, _IS_DEMO = load_detections()

CONFIDENCE_COLORS = {
    "high":   {"hex": "#E53935", "folium": "red"},
    "medium": {"hex": "#FB8C00", "folium": "orange"},
    "low":    {"hex": "#1E88E5", "folium": "blue"},
}


def confidence_tier(conf: float) -> str:
    if conf >= 0.85:
        return "high"
    elif conf >= 0.70:
        return "medium"
    return "low"


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GeoVigil Analytics",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed",   # モバイルでは初期状態で閉じる
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&display=swap');

/* ── Base ── */
[data-testid="stAppViewContainer"] { background: #0f1117; }
[data-testid="stMain"] { padding: 0.75rem 1rem 1rem; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #161b22;
    border-right: 1px solid #30363d;
    min-width: 260px !important;
    max-width: 260px !important;
}
[data-testid="stSidebar"] * { color: #e6edf3 !important; }

/* サイドバー開閉ボタンを大きく・タップしやすく */
[data-testid="stSidebarCollapsedControl"] button,
[data-testid="stSidebarCollapseButton"] button {
    width: 44px !important;
    height: 44px !important;
    border-radius: 8px !important;
    background: #21262d !important;
    border: 1px solid #30363d !important;
}

/* ── Header ── */
.orbit-title, p.orbit-title, div p.orbit-title {
    font-family: 'Cormorant Garamond', Georgia, serif !important;
    color: #e6edf3 !important;
    font-size: clamp(3rem, 11vw, 5.5rem) !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    margin: 0 !important;
    line-height: 1.05 !important;
}
.orbit-subtitle {
    color: #8b949e;
    font-size: clamp(0.75rem, 3vw, 0.95rem);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 5px 0 0;
}
.orbit-caption {
    color: #58a6ff;
    font-size: clamp(0.7rem, 2.5vw, 0.8rem);
    margin-top: 5px;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 10px 14px;
}
[data-testid="stMetricValue"] { font-size: 1.4rem !important; color: #58a6ff !important; }

/* ── Inline filter bar (モバイル用) ── */
.filter-bar {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 12px 16px 8px;
    margin-bottom: 12px;
}

/* ── Slider: トラック・サム を大きく ── */
[data-testid="stSlider"] [role="slider"] {
    width: 24px !important;
    height: 24px !important;
}
[data-testid="stSlider"] { padding: 4px 0; }

/* ── Buttons ── */
[data-testid="stButton"] button {
    height: 44px !important;
    font-size: 0.9rem !important;
    border-radius: 8px !important;
    border: 1px solid #30363d !important;
    background: #21262d !important;
    color: #e6edf3 !important;
    transition: background 0.15s;
}
[data-testid="stButton"] button:hover { background: #2d333b !important; }

/* ── Legend dots ── */
.legend-dot {
    display: inline-block;
    width: 11px; height: 11px;
    border-radius: 50%;
    margin-right: 7px;
    vertical-align: middle;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
}

/* ── Divider ── */
hr { border-color: #30363d !important; }

/* ── Status dot (active / unconfirmed) ── */
.status-dot {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
}
.status-dot-active {
    background: #3fb950;
    box-shadow: 0 0 0 0 rgba(63,185,80,0.6);
    animation: pulse-green 2s infinite;
}
.status-dot-unconfirmed {
    background: #d29922;
}
@keyframes pulse-green {
    0%   { box-shadow: 0 0 0 0 rgba(63,185,80,0.6); }
    70%  { box-shadow: 0 0 0 6px rgba(63,185,80,0); }
    100% { box-shadow: 0 0 0 0 rgba(63,185,80,0); }
}

/* ── Mobile breakpoint (<640px) ── */
@media (max-width: 640px) {
    [data-testid="stMain"] { padding: 0.5rem 0.6rem 2rem; }
    /* Folium地図の高さはJSで制御するため、ここでは余白を詰める */
    iframe { border-radius: 10px; }
}
</style>
""", unsafe_allow_html=True)

# ── State ─────────────────────────────────────────────────────────────────────
if "lang" not in st.session_state:
    st.session_state.lang = "es"

t = TEXTS[st.session_state.lang]

# ── Sidebar（デスクトップ用フィルター）─────────────────────────────────────────
with st.sidebar:
    if st.button(t["lang_toggle"], use_container_width=True):
        st.session_state.lang = "en" if st.session_state.lang == "es" else "es"
        st.rerun()

    st.markdown("---")
    st.markdown(f"### {t['filter_header']}")
    min_conf_sb = st.slider(
        t["slider_label"], min_value=0, max_value=100, value=50, step=5,
        key="slider_sidebar",
    ) / 100.0

    st.markdown("---")
    st.markdown(f"**{t['legend_title']}**")
    for tier, label_key in [("high", "legend_high"), ("medium", "legend_mid"), ("low", "legend_low")]:
        color = CONFIDENCE_COLORS[tier]["hex"]
        st.markdown(
            f'<span class="legend-dot" style="background:{color}"></span>{t[label_key]}',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown("**Status**")
    st.markdown(
        '<span class="status-dot status-dot-active" style="margin-right:7px;vertical-align:middle"></span>'
        f'{t["legend_active"]}',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<span class="status-dot status-dot-unconfirmed" style="margin-right:7px;vertical-align:middle"></span>'
        f'{t["legend_unconfirmed"]}',
        unsafe_allow_html=True,
    )

    st.markdown("---")
    total = len(DETECTIONS)
    sb_filtered = len(DETECTIONS[DETECTIONS["confidence"] >= min_conf_sb])
    st.metric(t["metric_label"], f"{sb_filtered}  /  {total}")

    st.markdown("---")
    st.markdown(f"**{t['data_status']}**")
    status_label = t["status_demo"] if _IS_DEMO else t["status_live"]
    status_color = "#8b949e" if _IS_DEMO else "#3fb950"
    st.markdown(
        f'<span style="color:{status_color};font-size:0.85rem">● {status_label}</span>',
        unsafe_allow_html=True,
    )
    last_update = _GENERATED_AT[:10] if _GENERATED_AT else "—"
    st.markdown(
        f'<span style="color:#8b949e;font-size:0.8rem">{t["last_update"]}: {last_update}</span>',
        unsafe_allow_html=True,
    )

# ── Header ────────────────────────────────────────────────────────────────────
col_title, col_lang = st.columns([5, 1])
with col_title:
    st.markdown(f'<p class="orbit-title">🛰️ {t["title"]}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="orbit-subtitle">{t["subtitle"]}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="orbit-caption">{t["caption"]}</p>', unsafe_allow_html=True)
with col_lang:
    if st.button(t["lang_toggle"], key="lang_top"):
        st.session_state.lang = "en" if st.session_state.lang == "es" else "es"
        st.rerun()

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ── モバイル用インラインフィルターバー ────────────────────────────────────────
st.markdown(f'<div class="filter-bar">', unsafe_allow_html=True)
col_sl, col_met = st.columns([3, 1])
with col_sl:
    min_conf = st.slider(
        t["slider_label"], min_value=0, max_value=100, value=50, step=5,
        key="slider_main",
        label_visibility="visible",
    ) / 100.0
with col_met:
    total = len(DETECTIONS)
    filtered_count = len(DETECTIONS[DETECTIONS["confidence"] >= min_conf])
    st.metric(t["metric_label"], f"{filtered_count} / {total}")
st.markdown("</div>", unsafe_allow_html=True)

# ── Map ───────────────────────────────────────────────────────────────────────
df_filtered = DETECTIONS[DETECTIONS["confidence"] >= min_conf].reset_index(drop=True)

m = folium.Map(
    location=[-9.19, -75.0],
    zoom_start=6,
    tiles="CartoDB positron",
)

# タッチ操作用にピンチズーム・タップポップアップを有効化
m.options["tap"] = True

STATUS_DOT = {
    "active":      '<span class="status-dot status-dot-active"></span>',
    "unconfirmed": '<span class="status-dot status-dot-unconfirmed"></span>',
}

for _, row in df_filtered.iterrows():
    tier = confidence_tier(row["confidence"])
    color = CONFIDENCE_COLORS[tier]["folium"]
    hex_color = CONFIDENCE_COLORS[tier]["hex"]
    status = row.get("status", "active")
    dot = STATUS_DOT.get(status, "")
    source = row.get("source", "—")
    confirmed_at = row.get("confirmed_at", row["detected_at"])
    popup_html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                font-size:14px;min-width:210px;padding:4px 2px">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
            <span>
                <b style="font-size:15px;color:{hex_color}">{row['confidence']*100:.1f}%</b>
                <span style="font-size:11px;color:#666;margin-left:6px">{t['popup_conf']}</span>
            </span>
            {dot}
        </div>
        <hr style="margin:8px 0;border-color:#e0e0e0">
        <div style="line-height:1.9;font-size:13px">
            📅 <b>{t['popup_first']}:</b> {row['detected_at']}<br>
            🔄 <b>{t['popup_last']}:</b> {confirmed_at}<br>
            🛰️ <b>{t['popup_source']}:</b> {source}<br>
            📍 {row['lat']:.4f}, {row['lon']:.4f}
        </div>
    </div>
    """
    folium.CircleMarker(
        location=[row["lat"], row["lon"]],
        radius=11,          # タップしやすいよう少し大きめ
        color=color,
        weight=2,
        fill=True,
        fill_color=color,
        fill_opacity=0.75,
        popup=folium.Popup(popup_html, max_width=240),
        tooltip=f"{row['confidence']*100:.1f}%",
    ).add_to(m)

st_folium(m, use_container_width=True, height=580, returned_objects=[])

# ── Detection table ───────────────────────────────────────────────────────────
with st.expander(f"📋  {t['table_expander']}", expanded=False):
    display_df = df_filtered.copy()
    display_df["confidence"] = (display_df["confidence"] * 100).map("{:.1f}%".format)
    display_df.columns = [t["col_lat"], t["col_lon"], t["col_conf"], t["col_date"]]
    st.dataframe(display_df, use_container_width=True, hide_index=True)
