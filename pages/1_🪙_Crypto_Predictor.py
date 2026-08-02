import streamlit as st

from src import crypto_model, market_data, tracking
from src.errors import MarketDataError

st.set_page_config(page_title="Crypto Predictor", page_icon="🪙", layout="wide")
st.title("🪙 Perpetual Crypto Predictor")


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
    klines = market_data.get_klines(symbol, interval="1m", limit=1)
    return float(klines["close"].iloc[-1])


try:
    source = market_data.active_provider_name()
except MarketDataError as exc:
    st.error(str(exc))
    st.caption(
        "Kalau semua sumber gagal dengan error DNS, kemungkinan jaringan/ISP kamu "
        "memblokir domain exchange-nya."
    )
    st.stop()

st.caption(f"Sumber data: **{source}** · perpetual USDT · live saat halaman dibuka/refresh")

try:
    tracking.evaluate_pending(current_price)
except Exception:
    pass  # never block the page on background housekeeping

try:
    volatile_df = load_volatile_symbols()
except MarketDataError as exc:
    st.error(str(exc))
    st.stop()

if volatile_df.empty:
    st.warning("Tidak ada data simbol saat ini. Coba refresh.")
    st.stop()

st.subheader("Coin paling volatile hari ini")
display_df = volatile_df.rename(columns={
    "symbol": "Simbol",
    "lastPrice": "Harga Terakhir",
    "priceChangePercent": "Perubahan 24h (%)",
    "dayRangePct": "Rentang Harian (%)",
    "quoteVolume": "Volume (USDT)",
})
st.dataframe(display_df, use_container_width=True, hide_index=True)

symbol = st.selectbox("Pilih coin untuk diprediksi", volatile_df["symbol"].tolist())

if symbol:
    try:
        klines, funding, order_book = load_symbol_data(symbol)
    except MarketDataError as exc:
        st.error(str(exc))
        st.stop()

    result = crypto_model.predict(symbol, klines, funding, order_book)

    col1, col2, col3 = st.columns(3)
    col1.metric("Harga Terakhir", f"${result['last_price']:,.4f}")
    col2.metric("Prediksi Arah (jangka pendek)", result["direction"])
    col3.metric("Confidence", f"{result['confidence']*100:.0f}%")

    st.line_chart(klines.set_index("open_time")["close"], height=250)

    st.subheader("Rincian sinyal (biar ga black box)")
    breakdown_rows = [
        {
            "Sinyal": s.name,
            "Nilai Mentah": round(s.raw_value, 4),
            "Skor (-1..1)": round(s.signal, 2),
            "Bobot": s.weight,
            "Kontribusi": round(s.contribution, 3),
        }
        for s in result["breakdown"]
    ]
    st.dataframe(breakdown_rows, use_container_width=True, hide_index=True)

    if st.button("Catat prediksi ini ke track record"):
        tracking.log_prediction(symbol, result["direction"], result["last_price"], result["confidence"])
        st.success("Prediksi dicatat. Hasilnya bakal ikut dihitung ke akurasi setelah beberapa jam.")

st.divider()
st.subheader("Track record model (auto-check tiap kamu buka halaman ini)")
stats = tracking.get_accuracy_stats()
if stats["total"] == 0:
    st.caption("Belum ada prediksi yang selesai dicek. Klik 'Catat prediksi ini' di atas buat mulai ngumpulin data.")
else:
    st.metric(
        "Hit rate",
        f"{stats['hit_rate']*100:.1f}%",
        help=f"{stats['correct']} benar dari {stats['total']} prediksi yang sudah jatuh tempo",
    )

st.caption(
    "Model ini rule-based (bukan machine learning) dan dioptimalkan buat transparansi, "
    "bukan buat mengejar 'akurasi tinggi' yang palsu. Bukan nasihat finansial."
)
