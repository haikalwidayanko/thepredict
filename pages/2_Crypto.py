import time

import streamlit as st

from src import backtest, crypto_model, market_data, tracking, ui
from src.errors import MarketDataError

st.set_page_config(page_title="Crypto · Predictor", page_icon="🪙", layout="wide")
ui.show_logo()
ui.page_header(
    "crypto",
    "🪙 Crypto Perpetual",
    "Koin perpetual USDT paling volatile hari ini, dengan prediksi arah jangka pendek multi-timeframe.",
)

MTF_INTERVALS = crypto_model.MTF_INTERVALS  # ["15m", "1h", "4h"]


@st.cache_data(ttl=60, show_spinner=False)
def load_volatile_symbols():
    return market_data.get_top_volatile_symbols(n=20)


@st.cache_data(ttl=30, show_spinner=False)
def load_symbol_data(symbol: str):
    klines_by_tf = {
        tf: market_data.get_klines(symbol, interval=tf, limit=100) for tf in MTF_INTERVALS
    }
    funding = market_data.get_funding_rate(symbol)
    order_book = market_data.get_order_book(symbol, limit=50)
    return klines_by_tf, funding, order_book


@st.cache_data(ttl=1800, show_spinner=False)
def load_backtest_klines(symbol: str, limit: int):
    return market_data.get_klines(symbol, interval="15m", limit=limit)


def current_price(symbol: str) -> float:
    return float(market_data.get_klines(symbol, interval="1m", limit=1)["close"].iloc[-1])


try:
    tracking.evaluate_pending(current_price)
except Exception:
    pass  # never block the page on housekeeping

tab_predict, tab_backtest, tab_history = st.tabs(
    ["📈 Prediksi Hari Ini", "🔬 Backtest", "📊 Riwayat & Akurasi"]
)


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
    st.caption("Daftar ini berubah tiap kali dibuka/refresh — diranking dari rentang harga 24 jam yang terus bergerak.")
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
        st.session_state["last_symbol"] = symbol

    if symbol:
        try:
            klines_by_tf, funding, order_book = load_symbol_data(symbol)
        except MarketDataError as exc:
            st.error(str(exc))
            st.stop()

        result = crypto_model.predict_mtf(symbol, klines_by_tf, funding, order_book)
        agree, total_tf = result["alignment"]

        st.divider()
        cols = st.columns(4)
        cols[0].metric("Harga Terakhir", f"${result['last_price']:,.4f}")
        cols[1].metric("Prediksi Arah", result["direction"])
        cols[2].metric("Confidence", f"{result['confidence']*100:.0f}%")
        cols[3].metric("Timeframe Sejalan", f"{agree}/{total_tf}")

        if agree < total_tf:
            st.caption(
                f"⚠️ Cuma {agree} dari {total_tf} timeframe yang sejalan dengan arah prediksi "
                "— sinyalnya campur aduk antar timeframe, confidence-nya jangan ditelan mentah."
            )

        st.line_chart(klines_by_tf["15m"].set_index("open_time")["close"], height=250)

        st.subheader("Level referensi: Entry / Stop Loss / Take Profit")
        levels = result["levels"]
        if levels is None:
            st.caption("Data belum cukup untuk menghitung ATR, level tidak tersedia.")
        else:
            lv_cols = st.columns(4)
            lv_cols[0].metric("Entry", f"${levels['entry']:,.4f}")
            lv_cols[1].metric("Stop Loss", f"${levels['stop_loss']:,.4f}")
            lv_cols[2].metric("Take Profit", f"${levels['take_profit']:,.4f}")
            lv_cols[3].metric("Risk:Reward", f"1:{levels['risk_reward']:.1f}")
            st.caption(
                f"Jarak SL/TP dihitung dari ATR(14) 15m saat ini (${levels['atr']:,.4f}) — "
                f"SL = {crypto_model.SL_ATR_MULT}× ATR, TP = {crypto_model.TP_ATR_MULT}× ATR, "
                "otomatis menyesuaikan volatilitas coin ini, bukan persentase tetap. "
                "**Ini level referensi, bukan sinyal beli/jual** — cek tab Backtest untuk lihat "
                "seberapa sering TP kena duluan dibanding SL secara historis sebelum dipakai."
            )

        st.subheader("Rincian per timeframe")
        st.caption(
            "RSI/EMA/momentum dihitung terpisah di tiap timeframe lalu digabung "
            f"(bobot: {', '.join(f'{tf}={w:.0%}' for tf, w in crypto_model.MTF_WEIGHTS.items())})."
        )
        tf_rows = []
        for tf in MTF_INTERVALS:
            tf_result = result["timeframes"].get(tf)
            if tf_result is None:
                tf_rows.append({"Timeframe": tf, "Status": "data tidak cukup, dilewati"})
                continue
            tf_rows.append({
                "Timeframe": tf,
                "RSI": round(tf_result["rsi"], 1),
                "EMA Signal": round(tf_result["ema_signal"], 2),
                "Momentum": round(tf_result["momentum"], 2),
                "Skor": round(tf_result["score"], 3),
                "Arah": "NAIK" if tf_result["score"] >= 0 else "TURUN",
            })
        st.dataframe(tf_rows, width="stretch", hide_index=True)

        st.subheader("Rincian sinyal gabungan")
        st.caption("Price Action (MTF) = blend dari tabel di atas. Funding & order book dihitung sekali, bukan per timeframe.")
        st.dataframe(
            [{
                "Sinyal": s.name,
                "Nilai Mentah": round(s.raw_value, 4),
                "Skor (-1..1)": round(s.signal, 2),
                "Bobot": round(s.weight, 3),
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


# ------------------------------------------------------------- backtest ----
with tab_backtest:
    st.subheader("Uji model di data historis")
    st.caption(
        "Backtest ini menguji **hanya bagian price-action** (RSI + EMA cross + momentum, "
        "digabung lintas 15m/1h/4h). Funding rate dan order book imbalance **tidak diikutkan** "
        "karena Binance/Gate.io tidak menyediakan histori order book (cuma snapshot live) — "
        "jadi angka di bawah ini adalah batas bawah performa model penuh, bukan gambaran lengkapnya. "
        "Simulasinya berjalan maju di waktu (walk-forward): di tiap titik, model cuma melihat data "
        "yang tersedia sampai titik itu, persis seperti kondisi nyata."
    )

    bt_symbol = st.text_input(
        "Simbol untuk backtest",
        value=st.session_state.get("last_symbol", ""),
        placeholder="Contoh: BTCUSDT (Binance) atau BTC_USDT (Gate.io)",
        help="Format simbol mengikuti provider yang aktif — lihat tabel koin di tab Prediksi.",
    )
    days = st.slider("Rentang data historis (hari)", min_value=3, max_value=15, value=10)

    if st.button("Jalankan backtest", type="primary"):
        if not bt_symbol:
            st.warning("Isi simbol dulu.")
        else:
            with st.spinner(f"Mengambil {days} hari data 15m dan menjalankan simulasi..."):
                try:
                    limit = min(days * 96, 1500)  # 96 candle 15m per hari, dibatasi limit exchange
                    hist_klines = load_backtest_klines(bt_symbol, limit)
                    bt_result = backtest.run_price_action_backtest(hist_klines)
                except MarketDataError as exc:
                    st.error(str(exc))
                    bt_result = None
                except ValueError as exc:
                    st.error(str(exc))
                    bt_result = None

            if bt_result:
                start, end = bt_result["date_range"]
                st.success(f"Simulasi selesai: {bt_result['total']} prediksi historis dari {start:%d %b} sampai {end:%d %b %Y}.")

                ui.accuracy_row(
                    total=bt_result["total"],
                    correct=bt_result["correct"],
                    hit_rate=bt_result["hit_rate"],
                    brier=bt_result["brier"],
                    noun="prediksi historis",
                )

                st.markdown("**Apakah confidence tinggi benar-benar lebih akurat?**")
                st.caption("Model yang terkalibrasi baik harusnya makin akurat di bucket confidence yang makin tinggi.")
                bucket_rows = [
                    {"Bucket Confidence": name, "Jumlah": stat["total"],
                     "Hit Rate": f"{stat['hit_rate']*100:.1f}%" if stat["hit_rate"] is not None else "—"}
                    for name, stat in bt_result["confidence_buckets"].items()
                ]
                st.dataframe(bucket_rows, width="stretch", hide_index=True)

                st.markdown("**Sinyal mana yang beneran nolong?**")
                st.caption("Hit rate tiap sinyal kalau dipakai sendirian (bukan hasil kombinasi bertimbang).")
                signal_rows = sorted(
                    [{"Sinyal": name, "Jumlah": stat["total"], "Hit Rate": f"{stat['hit_rate']*100:.1f}%",
                      "_sort": stat["hit_rate"]}
                     for name, stat in bt_result["signal_hit_rates"].items()],
                    key=lambda r: r["_sort"], reverse=True,
                )
                for row in signal_rows:
                    del row["_sort"]
                st.dataframe(signal_rows, width="stretch", hide_index=True)

                st.markdown("**Apakah TP/SL ala ATR ini beneran untung?**")
                tp_sl = bt_result["tp_sl"]
                st.caption(
                    f"Simulasi: tiap sinyal historis dikasih level TP/SL versi ATR "
                    f"(SL={crypto_model.SL_ATR_MULT}×ATR, TP={crypto_model.TP_ATR_MULT}×ATR), "
                    f"lalu dicek candle demi candle (pakai high/low, bukan cuma close) mana yang "
                    f"kena duluan, sampai {backtest.DEFAULT_TP_SL_WATCH_BARS // 4} jam ke depan. "
                    f"Kalau TP dan SL sama-sama kena dalam satu candle yang sama, dianggap SL "
                    f"(asumsi konservatif, karena data OHLC tidak bisa tahu mana yang duluan)."
                )
                tp_cols = st.columns(4)
                tp_cols[0].metric("TP kena duluan", f"{tp_sl['tp']}×")
                tp_cols[1].metric("SL kena duluan", f"{tp_sl['sl']}×")
                tp_cols[2].metric("Timeout (belum kena)", f"{tp_sl['timeout']}×")
                tp_cols[3].metric(
                    "Win rate",
                    f"{tp_sl['tp_rate']*100:.1f}%" if tp_sl["tp_rate"] is not None else "—",
                    help="Dari trade yang sudah selesai (TP atau SL kena), timeout tidak dihitung.",
                )
                if tp_sl["expectancy_r"] is not None:
                    breakeven_wr = 1 / (1 + crypto_model.TP_ATR_MULT / crypto_model.SL_ATR_MULT)
                    verdict = "✅ Positif" if tp_sl["expectancy_r"] > 0 else "❌ Negatif"
                    st.metric(
                        "Expectancy",
                        f"{tp_sl['expectancy_r']:+.3f} R",
                        help=(
                            f"1R = jarak SL. Butuh win rate > {breakeven_wr*100:.1f}% supaya "
                            f"impas di R:R 1:{crypto_model.TP_ATR_MULT/crypto_model.SL_ATR_MULT:.0f} ini."
                        ),
                    )
                    st.caption(
                        f"{verdict} — expectancy dihitung dari data historis di atas, bukan "
                        "diasumsikan dari rasio R:R di atas kertas. Sample historis terbatas "
                        "(satu coin, beberapa hari), jadi jangan dianggap final."
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
