import streamlit as st

from src import tracking, ui

st.set_page_config(
    page_title="Predictor · Crypto Perpetual",
    page_icon="📈",
    layout="wide",
)

ui.show_logo()
ui.hero_logo()
ui.page_header(
    "home",
    "Predictor",
    "Cari koin perpetual USDT yang lagi bergerak, lalu ukur arahnya dengan model yang bisa diaudit.",
)

stats = tracking.get_accuracy_stats()

with st.container(border=True):
    st.markdown("### 🪙 Crypto Perpetual")
    st.caption("Sumber: Binance Futures / Gate.io Futures")
    st.write(
        "Koin perpetual USDT paling volatile hari ini, dengan prediksi arah jangka "
        "pendek dari model ensemble multi-timeframe (RSI, EMA cross, momentum di "
        "15m/1h/4h, plus funding rate dan order book imbalance), lengkap dengan "
        "level Entry / Stop Loss / Take Profit berbasis ATR."
    )
    cols = st.columns(2)
    cols[0].metric("Prediksi tercatat", stats["total"])
    cols[1].metric(
        "Akurasi", f"{stats['hit_rate']*100:.0f}%" if stats["hit_rate"] is not None else "—"
    )
    st.page_link("pages/1_Crypto.py", label="Buka Crypto Predictor", icon="🪙")

st.divider()

st.markdown("#### Cara kerjanya")
how = st.columns(3)
how[0].markdown(
    "**1 · Live saat dibuka**\n\n"
    "Semua data diambil langsung ketika kamu membuka atau me-refresh halaman. "
    "Tidak ada notifikasi atau proses yang jalan di belakang."
)
how[1].markdown(
    "**2 · Kamu yang memilih**\n\n"
    "Daftar koin diranking dari volatilitas 24 jam, jadi isinya berubah-ubah. "
    "Kamu yang pilih mau lihat koin yang mana."
)
how[2].markdown(
    "**3 · Hasilnya diukur**\n\n"
    "Prediksi yang kamu catat dicek otomatis setelah horizonnya lewat. "
    "Tab Backtest juga menguji ulang model di data historis."
)

st.info(
    "**Disclaimer** — Ini alat bantu analisis, bukan nasihat finansial, dan bukan "
    "jaminan hasil. Pasar kripto pada dasarnya tidak pasti; gunakan sebagai salah "
    "satu input, bukan satu-satunya dasar keputusan. Level Entry/SL/TP adalah "
    "referensi berbasis volatilitas, bukan sinyal beli/jual.",
    icon="⚠️",
)
