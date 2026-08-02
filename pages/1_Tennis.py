import streamlit as st

from src import match_model, tracking, ui
from src import polymarket_client as pm

st.set_page_config(page_title="Tennis · Predictor", page_icon="🎾", layout="wide")
ui.show_logo()
ui.page_header(
    "tennis",
    "🎾 Tennis",
    "Jadwal pertandingan hari ini dari Polymarket, dengan peluang menang tiap pemain.",
)


@st.cache_data(ttl=90, show_spinner=False)
def load_events(_day_key: str):
    # _day_key is part of the cache key so the cache drops at midnight WIB
    # instead of serving yesterday's schedule.
    return pm.get_tennis_events(only_today=True)


# Resolve past projections first so the history tab is current on load.
try:
    tracking.evaluate_pending_matches(pm.get_market_by_slug)
except Exception:
    pass  # never block the page on housekeeping

tab_today, tab_history = st.tabs(["📅 Pertandingan Hari Ini", "📊 Riwayat & Akurasi"])


# ---------------------------------------------------------------- today ----
with tab_today:
    st.caption(f"Hari ini — **{match_model.format_today_wib()}** (WIB)")

    events = []
    fetch_failed = False
    try:
        events = load_events(str(match_model.today_wib()))
    except pm.PolymarketError as exc:
        fetch_failed = True
        st.error(str(exc))
        st.caption(
            "Kalau errornya soal DNS, jaringan/ISP kamu kemungkinan memblokir "
            "Polymarket. Halaman ini jalan normal saat aplikasi di-deploy ke cloud."
        )

    if not events and not fetch_failed:
        st.warning(
            "Tidak ada pertandingan tennis di Polymarket untuk hari ini. "
            "Coba lagi nanti — daftar diperbarui setiap kali halaman dibuka."
        )

    hidden_by_filter = 0
    if events:
        total_today = len(events)

        tier_label = st.select_slider(
            "Saring berdasarkan likuiditas",
            options=list(match_model.LIQUIDITY_TIERS.keys()),
            value="≥ $10.000 (tebal)",
            help=(
                "Likuiditas = kedalaman order book. Makin tipis, makin gampang "
                "harganya digerakkan satu order kecil, jadi probabilitasnya "
                "kurang bisa dipercaya."
            ),
        )
        # .get() with a floor default: a stale widget value (e.g. options
        # changed between deploys) would otherwise raise a bare KeyError.
        min_liquidity = match_model.LIQUIDITY_TIERS.get(tier_label, match_model.LIQUIDITY_LOW)

        events = [e for e in events if match_model.max_winner_liquidity(e) >= min_liquidity]
        hidden_by_filter = total_today - len(events)

        if not events:
            st.warning(
                f"Semua {total_today} pertandingan hari ini punya likuiditas di bawah "
                "ambang ini. Geser filter di atas ke kiri untuk melihatnya."
            )

    if events:
        note = f" ({hidden_by_filter} disaring karena likuiditas tipis)" if hidden_by_filter else ""
        st.write(f"**{len(events)}** pertandingan hari ini{note}, diurutkan dari jam main paling awal.")

        def event_label(i: int) -> str:
            e = events[i]
            # All entries are today, so the date would just be noise.
            return f"{match_model.format_time_wib(e['start_date'])}  —  {e['title']}"

        choice = st.selectbox("Pilih pertandingan", range(len(events)), format_func=event_label)
        selected_event = events[choice]

        st.divider()
        st.subheader(selected_event["title"])

        # Plain markdown rather than st.metric: metric values are single-line
        # and get truncated with an ellipsis, which hid the actual kick-off time.
        st.markdown(
            f"<div class='match-schedule'>"
            f"<span class='time'>🕐 {match_model.format_time_wib(selected_event['start_date'])}</span>"
            f"<span class='status'>{match_model.match_status(selected_event['start_date'])}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if selected_event.get("start_field") == "startDate":
            st.caption(
                "⚠️ Polymarket tidak memberi jam pertandingan untuk event ini — "
                "waktu di atas adalah tanggal pembukaan market, jadi bisa meleset."
            )

        schedule_link = match_model.external_schedule_link(selected_event["title"])
        st.caption(f"🔗 [Cek jadwal & skor asli di Flashscore]({schedule_link})")

        # Only the overall match result, and only markets meeting the chosen
        # liquidity bar. Polymarket sometimes carries a stale duplicate market
        # ($1 liquidity, $0 volume) alongside the real one for the same
        # question -- the liquidity floor filters that out too.
        main_markets = [
            m for m in selected_event["markets"]
            if match_model.is_match_winner_market(m["question"], m["outcomes"])
            and float(m.get("liquidity") or 0) >= min_liquidity
        ]
        hidden_count = len(selected_event["markets"]) - len(main_markets)

        if not main_markets:
            st.warning("Tidak ada pasar hasil akhir dengan likuiditas cukup untuk pertandingan ini.")

        for market in main_markets:
            analysis = match_model.analyze_market(market, selected_event["title"])
            with st.container(border=True):
                cols = st.columns(len(analysis["outcomes"]) or 1)
                for col, outcome in zip(cols, analysis["outcomes"]):
                    label = outcome.outcome
                    if analysis["favorite"] and outcome.outcome == analysis["favorite"].outcome:
                        label += " ⭐"
                    col.metric(label, f"{outcome.probability*100:.1f}%")

                meta = st.columns(3)
                meta[0].metric("Likuiditas", f"${analysis['liquidity']:,.0f}")
                meta[1].metric("Volume", f"${analysis['volume']:,.0f}")
                meta[2].metric("Confidence", analysis["confidence_label"])

                fav = analysis["favorite"]
                if fav:
                    if tracking.already_logged(analysis["slug"], analysis["question"]):
                        st.caption("✓ Proyeksi untuk pertandingan ini sudah dicatat.")
                    elif st.button(
                        f"Catat proyeksi: {fav.outcome} ({fav.probability*100:.1f}%)",
                        key=f"log_{analysis['slug']}_{analysis['question'][:30]}",
                    ):
                        tracking.log_match_prediction(
                            event_title=selected_event["title"],
                            slug=analysis["slug"],
                            question=analysis["question"],
                            predicted_outcome=fav.outcome,
                            raw_outcome=fav.raw_outcome,
                            probability=fav.probability,
                            start_date=selected_event["start_date"],
                        )
                        st.rerun()

        if hidden_count:
            st.caption(
                f"{hidden_count} pasar disembunyikan — pasar per-set/total, atau "
                "likuiditasnya di bawah ambang filter."
            )


# -------------------------------------------------------------- history ----
with tab_history:
    stats = tracking.get_match_accuracy_stats()
    history = tracking.get_match_history()

    if not history:
        st.info(
            "Belum ada proyeksi yang dicatat. Buka tab **Pertandingan Hari Ini**, "
            "lalu klik *Catat proyeksi* pada pertandingan yang kamu ikuti. "
            "Hasilnya dicek otomatis setelah pertandingan selesai."
        )
    else:
        ui.accuracy_row(
            total=stats["total"],
            correct=stats["correct"],
            hit_rate=stats["hit_rate"],
            brier=stats["brier"],
            noun="pertandingan",
        )
        st.caption(
            f"{stats['total']} pertandingan sudah ada hasilnya, "
            f"{len(history) - stats['total']} masih menunggu."
        )
        st.divider()

        rows = []
        for rec in history:
            if rec["resolved"]:
                hasil = "✅ Tepat" if rec["correct"] else "❌ Meleset"
                pemenang = rec.get("actual_outcome") or "—"
            else:
                hasil = "⏳ Menunggu"
                pemenang = "—"
            rows.append({
                "Pertandingan": rec["event_title"],
                "Jadwal": match_model.format_wib(rec.get("start_date")),
                "Proyeksi": rec["predicted_outcome"],
                "Peluang": f"{rec['probability']*100:.1f}%",
                "Hasil": hasil,
                "Pemenang": pemenang,
            })
        st.dataframe(rows, width="stretch", hide_index=True)

st.caption(
    "Probabilitas di atas adalah harga pasar Polymarket apa adanya (wisdom of the crowd), "
    "bukan model prediksi independen. Confidence dihitung dari likuiditas market. "
    "Semua waktu dalam WIB. Bukan nasihat finansial/taruhan."
)
