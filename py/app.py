import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# ── ダミーデータ（AIが検知した違法滑走路の候補地） ──────────────────────────
DETECTIONS = pd.DataFrame(
    [
        # アマゾン低地
        {"lat": -3.7491,  "lon": -73.2538, "confidence": 0.91, "detected_at": "2025-03-15 08:22"},
        {"lat": -5.1843,  "lon": -75.0152, "confidence": 0.84, "detected_at": "2025-03-15 08:45"},
        {"lat": -4.5621,  "lon": -74.1834, "confidence": 0.72, "detected_at": "2025-03-15 09:10"},
        {"lat": -6.3217,  "lon": -76.5409, "confidence": 0.63, "detected_at": "2025-03-15 09:33"},
        {"lat": -7.1562,  "lon": -75.8823, "confidence": 0.55, "detected_at": "2025-03-15 09:55"},
        {"lat": -3.2984,  "lon": -72.6741, "confidence": 0.88, "detected_at": "2025-03-16 07:18"},
        {"lat": -8.8043,  "lon": -74.9215, "confidence": 0.77, "detected_at": "2025-03-16 08:02"},
        # 山岳地帯（アンデス）
        {"lat": -13.5317, "lon": -72.8818, "confidence": 0.69, "detected_at": "2025-03-17 10:05"},
        {"lat": -11.2451, "lon": -75.3394, "confidence": 0.82, "detected_at": "2025-03-17 10:30"},
        {"lat": -14.0672, "lon": -73.4129, "confidence": 0.58, "detected_at": "2025-03-17 11:00"},
        # 南部ジャングル（マドレ・デ・ディオス周辺）
        {"lat": -12.5934, "lon": -70.0817, "confidence": 0.95, "detected_at": "2025-03-18 06:45"},
        {"lat": -11.8763, "lon": -71.3452, "confidence": 0.87, "detected_at": "2025-03-18 07:20"},
        {"lat": -13.1289, "lon": -69.6543, "confidence": 0.74, "detected_at": "2025-03-18 07:55"},
        # 北部国境付近
        {"lat": -0.1834,  "lon": -75.8712, "confidence": 0.61, "detected_at": "2025-03-19 09:00"},
        {"lat": -1.5423,  "lon": -77.1234, "confidence": 0.79, "detected_at": "2025-03-19 09:40"},
    ]
)


def confidence_color(conf: float) -> str:
    if conf >= 0.85:
        return "red"
    elif conf >= 0.70:
        return "orange"
    else:
        return "blue"


# ── Streamlit UI ────────────────────────────────────────────────────────────
st.set_page_config(page_title="違法滑走路検出システム", layout="wide")
st.title("🛬 違法滑走路検出システム（ペルー）")
st.caption("衛星画像AIによる検知結果ビューア — バッチ解析済みデータを表示")

with st.sidebar:
    st.header("フィルター設定")
    min_conf = st.slider("最低検知確率（%）", min_value=0, max_value=100, value=50, step=5) / 100.0

    st.markdown("---")
    st.markdown("**マーカー色の凡例**")
    st.markdown("🔴 85%以上　🟠 70〜84%　🔵 70%未満")
    st.markdown("---")
    total = len(DETECTIONS)
    filtered_count = len(DETECTIONS[DETECTIONS["confidence"] >= min_conf])
    st.metric("表示中 / 総検知数", f"{filtered_count} / {total}")

# フィルタリング
df_filtered = DETECTIONS[DETECTIONS["confidence"] >= min_conf].reset_index(drop=True)

# ── Folium 地図の構築 ───────────────────────────────────────────────────────
m = folium.Map(
    location=[-9.19, -75.0],   # ペルー中央付近
    zoom_start=6,
    tiles="CartoDB positron",
)

for _, row in df_filtered.iterrows():
    popup_html = (
        f"<b>検知確率:</b> {row['confidence'] * 100:.1f}%<br>"
        f"<b>検知日時:</b> {row['detected_at']}<br>"
        f"<b>座標:</b> ({row['lat']:.4f}, {row['lon']:.4f})"
    )
    folium.CircleMarker(
        location=[row["lat"], row["lon"]],
        radius=10,
        color=confidence_color(row["confidence"]),
        fill=True,
        fill_opacity=0.8,
        popup=folium.Popup(popup_html, max_width=220),
        tooltip=f"{row['confidence'] * 100:.1f}%",
    ).add_to(m)

st_folium(m, use_container_width=True, height=650, returned_objects=[])

# ── データテーブル ──────────────────────────────────────────────────────────
with st.expander("📋 検知リスト（テーブル表示）", expanded=False):
    display_df = df_filtered.copy()
    display_df["confidence"] = (display_df["confidence"] * 100).map("{:.1f}%".format)
    display_df.columns = ["緯度", "経度", "検知確率", "検知日時"]
    st.dataframe(display_df, use_container_width=True, hide_index=True)
