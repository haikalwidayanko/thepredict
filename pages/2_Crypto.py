import time

import streamlit as st

from src import crypto_model, market_data, tracking, ui
from src.errors import MarketDataError

st.set_page_config(page_title="Crypto · Predictor", page_icon="🪙", layout="wide")
ui.show_logo()
ui.page_header(
    "crypto",
    "🪙 Crypto Perpetual",
    "Koin perpetual USDT paling volatile hari ini, dengan prediksi arah jangka pendek.",
)


@st.cache_data(ttl=60, show_spinner=False)
def load_volatile_symbols():
    return market_data.get_top_volatile_symbols(n=20)


@st.cache_data(ttl=30, show_spinner=False)
def load_symbol_data(symbol: str):
    klines = market_data.get_klines(symbol, interval="15m", limit=100)
    funding = market_data.get_funding_rate(symbol)
    order_book = market_data.get_order_book(symbol, limit=50)
    return klines, funding, order_book


def current_price(symbol: str) -> float:
    return float(market_data.get_klines(symbol, interval="1m", limit=1)["close"].iloc[-1])


try:
    tracking.evaluate_pending(current_price)
except Exception:
    pass  # never block the page on housekeeping

tab_predict, tab_history = st.tabs(["📈 Prediksi Hari Ini", "📊 Riwayat & Akurasi"])


# -------------------------------------------------------------- predict ----
with tab_predict:
    try:
        source = market_data.active_provider_name()
    except MarketDataError as exc:
        st.error(str(exc))
        st.caption(
            "Kalau semua sumber gagal dengan error DNS, jaringan/ISP kamu "
            "kemungkinan memblokir domain exchange-nya."
        )
        st.stop()

    st.caption(f"Sumber data: **{source}** · perpetual USDT · live saat halaman dibuka")

    try:
        volatile_df = load_volatile_symbols()
    except MarketDataError as exc:
        st.error(str(exc))
        st.stop()

    if volatile_df.empty:
        st.warning("Tidak ada data simbol saat ini. Coba refresh.")
        st.stop()

    st.subheader("Koin paling volatile hari ini")
    st.dataframe(
        volatile_df.rename(columns={
            "symbol": "Simbol",
            "lastPrice": "Harga Terakhir",
            "priceChangePercent": "Perubahan 24h (%)",
            "dayRangePct": "Rentang Harian (%)",
            "quoteVolume": "Volume (USDT)",
        }),
        width="stretch",
        hide_index=True,
    )

    symbol = st.selectbox("Pilih koin untuk diprediksi", volatile_df["symbol"].tolist())

    if symbol:
        try:
            klines, funding, order_book = load_symbol_data(symbol)
        except MarketDataError as exc:
            st.error(str(exc))
            st.stop()

        result = crypto_model.predict(symbol, klines, funding, order_book)

        st.divider()
        cols = st.columns(3)
        cols[0].metric("Harga Terakhir", f"${result['last_price']:,.4f}")
        cols[1].metric("Prediksi Arah", result["direction"])
        cols[2].metric("Confidence", f"{result['confidence']*100:.0f}%")

        st.line_chart(klines.set_index("open_time")["close"], height=250)

        st.subheader("Rincian sinyal")
        st.caption("Setiap sinyal dan bobotnya ditampilkan supaya modelnya bisa diaudit, bukan black box.")
        st.dataframe(
            [{
                "Sinyal": s.name,
                "Nilai Mentah": round(s.raw_value, 4),
                "Skor (-1..1)": round(s.signal, 2),
                "Bobot": s.weight,
                "Kontribusi": round(s.contribution, 3),
            } for s in result["breakdown"]],
            width="stretch",
            hide_index=True,
        )

        if st.button(f"Catat prediksi: {symbol} {result['direction']}"):
            tracking.log_prediction(
                symbol, result["direction"], result["last_price"], result["confidence"]
            )
            st.success(
                "Prediksi dicatat. Hasilnya dicek otomatis "
                f"{tracking.DEFAULT_HORIZON_HOURS} jam lagi, saat kamu buka halaman ini."
            )


# -------------------------------------------------------------- history ----
with tab_history:
    stats = tracking.get_accuracy_stats()
    history = tracking.get_crypto_history()

    if not history:
        st.info(
            "Belum ada prediksi yang dicatat. Buka tab **Prediksi Hari Ini**, "
            "pilih koin, lalu klik *Catat prediksi*. Hasilnya dicek otomatis "
            f"{tracking.DEFAULT_HORIZON_HOURS} jam kemudian."
        )
    else:
        ui.accuracy_row(
            total=stats["total"],
            correct=stats["correct"],
            hit_rate=stats["hit_rate"],
            brier=stats["brier"],
            noun="prediksi",
        )
        st.caption(
            f"{stats['total']} prediksi sudah jatuh tempo, "
            f"{len(history) - stats['total']} masih menunggu."
        )
        st.divider()

        rows = []
        for rec in history:
            if rec["resolved"]:
                hasil = "✅ Tepat" if rec["correct"] else "❌ Meleset"
                harga_akhir = f"${rec['price_at_resolution']:,.4f}" if rec.get("price_at_resolution") else "—"
            else:
                sisa = rec["horizon_hours"] - (time.time() - rec["timestamp"]) / 3600
                hasil = f"⏳ {max(sisa, 0):.1f} jam lagi"
                harga_akhir = "—"
            rows.append({
                "Koin": rec["symbol"],
                "Prediksi": rec["direction"],
                "Confidence": f"{rec['confidence']*100:.0f}%",
                "Harga saat prediksi": f"${rec['price_at_prediction']:,.4f}",
                "Harga saat dicek": harga_akhir,
                "Hasil": hasil,
            })
        st.dataframe(rows, width="stretch", hide_index=True)

st.caption(
    "Model ini rule-based (bukan machine learning) dan dioptimalkan untuk transparansi, "
    "bukan untuk mengejar klaim akurasi tinggi. Bukan nasihat finansial."
)
