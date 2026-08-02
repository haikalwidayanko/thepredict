import streamlit as st

from src import tracking, ui

st.set_page_config(
    page_title="Predictor · Tennis & Crypto",
    page_icon="📈",
    layout="wide",
)

ui.show_logo()
ui.page_header(
    "home",
    "Predictor",
    "Dua alat analisis dalam satu tempat — pertandingan tennis dan pasar kripto perpetual.",
)

col_tennis, col_crypto = st.columns(2, gap="large")

with col_tennis:
    with st.container(border=True):
        st.markdown("### 🎾 Tennis")
        st.caption("Sumber: Polymarket")
        st.write(
            "Jadwal pertandingan **hari ini** beserta peluang menang tiap pemain, "
            "diambil dari harga pasar Polymarket. Fokus ke hasil akhir — "
            "pasar per-set dan total games disaring keluar."
        )
        t = tracking.get_match_accuracy_stats()
        cols = st.columns(2)
        cols[0].metric("Pertandingan tercatat", t["total"])
        cols[1].metric(
            "Akurasi", f"{t['hit_rate']*100:.0f}%" if t["hit_rate"] is not None else "—"
        )
        st.page_link("pages/1_Tennis.py", label="Buka Tennis", icon="🎾")

with col_crypto:
    with st.container(border=True):
        st.markdown("### 🪙 Crypto Perpetual")
        st.caption("Sumber: Binance / Gate.io")
        st.write(
            "Koin perpetual USDT paling volatile hari ini, dengan prediksi arah "
            "jangka pendek dari model ensemble indikator teknikal (RSI, EMA cross, "
            "momentum, funding rate, order book imbalance)."
        )
        c = tracking.get_accuracy_stats()
        cols = st.columns(2)
        cols[0].metric("Prediksi tercatat", c["total"])
        cols[1].metric(
            "Akurasi", f"{c['hit_rate']*100:.0f}%" if c["hit_rate"] is not None else "—"
        )
        st.page_link("pages/2_Crypto.py", label="Buka Crypto", icon="🪙")

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
    "Pilih sendiri pertandingan atau koin yang ingin dilihat. "
    "Tidak ada rekomendasi otomatis."
)
how[2].markdown(
    "**3 · Hasilnya diukur**\n\n"
    "Setiap proyeksi yang kamu catat akan dicek otomatis setelah hasilnya keluar, "
    "lalu ditampilkan sebagai akurasi di tab Riwayat."
)

st.info(
    "**Disclaimer** — Ini alat bantu analisis, bukan nasihat finansial maupun ajakan "
    "berjudi, dan bukan jaminan hasil. Pasar kripto dan pertandingan olahraga pada "
    "dasarnya tidak pasti; gunakan sebagai salah satu input, bukan satu-satunya dasar "
    "keputusan.",
    icon="⚠️",
)
