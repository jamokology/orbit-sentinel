import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# ── i18n ─────────────────────────────────────────────────────────────────────
TEXTS = {
    "es": {
        "page_title":     "Orbit Sentinel",
        "title":          "Orbit Sentinel",
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
        "filters_title":  "⚙️ Filtros",
    },
    "en": {
        "page_title":     "Orbit Sentinel",
        "title":          "Orbit Sentinel",
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
        "filters_title":  "⚙️ Filters",
    },
}

# ── Detection data ────────────────────────────────────────────────────────────
DETECTIONS = pd.DataFrame([
    {"lat": -3.7491,  "lon": -73.2538, "confidence": 0.91, "detected_at": "2025-03-15 08:22"},
    {"lat": -5.1843,  "lon": -75.0152, "confidence": 0.84, "detected_at": "2025-03-15 08:45"},
    {"lat": -4.5621,  "lon": -74.1834, "confidence": 0.72, "detected_at": "2025-03-15 09:10"},
    {"lat": -6.3217,  "lon": -76.5409, "confidence": 0.63, "detected_at": "2025-03-15 09:33"},
    {"lat": -7.1562,  "lon": -75.8823, "confidence": 0.55, "detected_at": "2025-03-15 09:55"},
    {"lat": -3.2984,  "lon": -72.6741, "confidence": 0.88, "detected_at": "2025-03-16 07:18"},
    {"lat": -8.8043,  "lon": -74.9215, "confidence": 0.77, "detected_at": "2025-03-16 08:02"},
    {"lat": -13.5317, "lon": -72.8818, "confidence": 0.69, "detected_at": "2025-03-17 10:05"},
    {"lat": -11.2451, "lon": -75.3394, "confidence": 0.82, "detected_at": "2025-03-17 10:30"},
    {"lat": -14.0672, "lon": -73.4129, "confidence": 0.58, "detected_at": "2025-03-17 11:00"},
    {"lat": -12.5934, "lon": -70.0817, "confidence": 0.95, "detected_at": "2025-03-18 06:45"},
    {"lat": -11.8763, "lon": -71.3452, "confidence": 0.87, "detected_at": "2025-03-18 07:20"},
    {"lat": -13.1289, "lon": -69.6543, "confidence": 0.74, "detected_at": "2025-03-18 07:55"},
    {"lat": -0.1834,  "lon": -75.8712, "confidence": 0.61, "detected_at": "2025-03-19 09:00"},
    {"lat": -1.5423,  "lon": -77.1234, "confidence": 0.79, "detected_at": "2025-03-19 09:40"},
])

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
    page_title="Orbit Sentinel",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed",   # モバイルでは初期状態で閉じる
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&display=swap');

/* ── Hide Streamlit chrome (keep top menu) ── */
footer, footer * { visibility: hidden !important; height: 0 !important; }
[data-testid="stToolbar"]        { display: none !important; }
[data-testid="stDecoration"]     { display: none !important; }
[data-testid="stStatusWidget"]   { display: none !important; }
[data-testid="stAppDeployButton"]{ display: none !important; }
/* bottom-right badge on all screen sizes */
.viewerBadge_container__r5tak,
.viewerBadge_link__qRIco,
[class*="viewerBadge"]           { display: none !important; }
/* bottom bar that appears on mobile */
[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"] { display: none !important; }

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
.orbit-title {
    font-family: 'Cormorant Garamond', Georgia, serif;
    color: #e6edf3;
    font-size: clamp(3rem, 11vw, 5.5rem);
    font-weight: 600;
    letter-spacing: 0.06em;
    margin: 0;
    line-height: 1.05;
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
    total = len(DETECTIONS)
    sb_filtered = len(DETECTIONS[DETECTIONS["confidence"] >= min_conf_sb])
    st.metric(t["metric_label"], f"{sb_filtered}  /  {total}")

    st.markdown("---")
    st.markdown(f"**{t['data_status']}**")
    st.markdown(
        f'<span style="color:#3fb950;font-size:0.85rem">● {t["status_demo"]}</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<span style="color:#8b949e;font-size:0.8rem">{t["last_update"]}: 2025-03-19</span>',
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

for _, row in df_filtered.iterrows():
    tier = confidence_tier(row["confidence"])
    color = CONFIDENCE_COLORS[tier]["folium"]
    hex_color = CONFIDENCE_COLORS[tier]["hex"]
    popup_html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                font-size:14px;min-width:190px;padding:4px 2px">
        <b style="font-size:15px;color:{hex_color}">{row['confidence']*100:.1f}%</b>
        <span style="font-size:11px;color:#666;margin-left:6px">{t['popup_conf']}</span>
        <hr style="margin:8px 0;border-color:#e0e0e0">
        <div style="line-height:1.8">
            📅 {row['detected_at']}<br>
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

# 画面の高さに応じて地図の高さを切り替える JS を注入
st.markdown("""
<script>
(function() {
    const isMobile = window.innerWidth < 640;
    const h = isMobile ? Math.floor(window.innerHeight * 0.55) : 600;
    const frames = window.parent.document.querySelectorAll('iframe');
    frames.forEach(f => { if (f.src && f.src.includes('streamlit')) return;
                           f.style.height = h + 'px'; });
})();
</script>
""", unsafe_allow_html=True)

st_folium(m, use_container_width=True, height=580, returned_objects=[])

# ── Detection table ───────────────────────────────────────────────────────────
with st.expander(f"📋  {t['table_expander']}", expanded=False):
    display_df = df_filtered.copy()
    display_df["confidence"] = (display_df["confidence"] * 100).map("{:.1f}%".format)
    display_df.columns = [t["col_lat"], t["col_lon"], t["col_conf"], t["col_date"]]
    st.dataframe(display_df, use_container_width=True, hide_index=True)
