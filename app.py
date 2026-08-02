import streamlit as st

st.set_page_config(
    page_title="Predictor Hub",
    page_icon="🔮",
    layout="wide",
)

st.title("🔮 Predictor Hub")
st.markdown(
    """
Web ini punya dua fitur, buka lewat menu di sidebar kiri:

- **🪙 Crypto Predictor** — pilih dari daftar koin perpetual USDT yang lagi
  paling volatile hari ini, lihat prediksi arah jangka pendek dari model
  ensemble indikator teknikal (RSI, EMA cross, momentum, funding rate,
  order book imbalance).
- **🏆 Match Predictor** — lihat pertandingan sepakbola & tennis yang lagi
  aktif di Polymarket beserta probabilitas implisit dari harga pasarnya.

Semua data diambil langsung saat kamu buka/refresh halaman — tidak ada
notifikasi atau proses background.
"""
)

st.info(
    "⚠️ **Disclaimer**: Ini alat bantu analisis, bukan nasihat finansial atau "
    "jaminan hasil. Pasar kripto dan taruhan olahraga pada dasarnya "
    "tidak pasti — gunakan sebagai salah satu input, bukan satu-satunya dasar keputusan.",
    icon="⚠️",
)
