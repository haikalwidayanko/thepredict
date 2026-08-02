import streamlit as st

from src import match_model, tracking
from src import polymarket_client as pm

st.set_page_config(page_title="Tennis Predictor", page_icon="🎾", layout="wide")
st.title("🎾 Tennis Match Predictor")
st.caption("Hasil akhir pertandingan · probabilitas dari harga pasar Polymarket · live saat halaman dibuka")


@st.cache_data(ttl=90, show_spinner=False)
def load_events():
    return pm.get_tennis_events()


# Resolve any past predictions first so the track record is current on load.
try:
    tracking.evaluate_pending_matches(pm.get_market_by_slug)
except Exception:
    pass  # never block the page on housekeeping

try:
    events = load_events()
except pm.PolymarketError as exc:
    st.error(str(exc))
    st.caption(
        "Kalau errornya soal DNS, jaringan/ISP kamu kemungkinan memblokir "
        "Polymarket. Halaman ini akan jalan normal saat aplikasi di-deploy ke cloud."
    )
    events = []

if events:
    st.write(f"**{len(events)}** pertandingan tennis aktif, diurutkan dari jadwal terdekat.")

    def event_label(i: int) -> str:
        e = events[i]
        return f"{match_model.format_wib(e['start_date'])}  —  {e['title']}"

    choice = st.selectbox("Pilih pertandingan", range(len(events)), format_func=event_label)
    selected_event = events[choice]

    st.divider()
    st.subheader(selected_event["title"])

    date_cols = st.columns(3)
    date_cols[0].metric("Jadwal mulai", match_model.format_wib(selected_event["start_date"]))
    date_cols[1].metric("Perkiraan selesai", match_model.format_wib(selected_event["end_date"]))
    date_cols[2].metric(
        "Status",
        match_model.match_status(selected_event["start_date"], selected_event["end_date"]),
    )

    # Only the overall match result -- per-set and prop markets are filtered out.
    main_markets = [
        m for m in selected_event["markets"]
        if match_model.is_match_winner_market(m["question"])
    ]
    hidden_count = len(selected_event["markets"]) - len(main_markets)

    if not main_markets:
        st.warning("Tidak ada pasar hasil akhir untuk pertandingan ini (hanya pasar per-set).")

    for market in main_markets:
        analysis = match_model.analyze_market(market)
        with st.container(border=True):
            st.markdown(f"**{analysis['question']}**")

            cols = st.columns(len(analysis["outcomes"]) or 1)
            for col, outcome in zip(cols, analysis["outcomes"]):
                label = outcome.outcome
                if analysis["favorite"] and outcome.outcome == analysis["favorite"].outcome:
                    label += " ⭐"
                col.metric(label, f"{outcome.probability*100:.1f}%")

            info_cols = st.columns(3)
            info_cols[0].metric("Likuiditas", f"${analysis['liquidity']:,.0f}")
            info_cols[1].metric("Volume", f"${analysis['volume']:,.0f}")
            info_cols[2].metric("Confidence (likuiditas)", analysis["confidence_label"])

            fav = analysis["favorite"]
            if fav:
                logged = tracking.already_logged(analysis["slug"], analysis["question"])
                if logged:
                    st.caption("✓ Proyeksi untuk pasar ini sudah dicatat.")
                elif st.button(
                    f"Catat proyeksi: {fav.outcome} ({fav.probability*100:.1f}%)",
                    key=f"log_{analysis['slug']}_{analysis['question'][:30]}",
                ):
                    tracking.log_match_prediction(
                        event_title=selected_event["title"],
                        slug=analysis["slug"],
                        question=analysis["question"],
                        predicted_outcome=fav.outcome,
                        probability=fav.probability,
                        start_date=selected_event["start_date"],
                    )
                    st.rerun()

    if hidden_count:
        st.caption(f"{hidden_count} pasar per-set/prop disembunyikan — halaman ini fokus ke hasil akhir.")

st.divider()
st.subheader("📊 Riwayat proyeksi & ketepatan")

stats = tracking.get_match_accuracy_stats()
history = tracking.get_match_history()

if not history:
    st.caption(
        "Belum ada proyeksi yang dicatat. Klik tombol 'Catat proyeksi' di atas — "
        "hasilnya dicek otomatis setiap kamu buka halaman ini, setelah pertandingan selesai."
    )
else:
    stat_cols = st.columns(3)
    stat_cols[0].metric("Sudah ada hasil", f"{stats['total']} proyeksi")
    stat_cols[1].metric(
        "Ketepatan",
        f"{stats['hit_rate']*100:.0f}%" if stats["hit_rate"] is not None else "—",
        help=f"{stats['correct']} benar dari {stats['total']} yang sudah selesai" if stats["total"] else None,
    )
    stat_cols[2].metric(
        "Brier score",
        f"{stats['brier']:.3f}" if stats["brier"] is not None else "—",
        help="Makin kecil makin baik (0 = sempurna, 0.25 = setara tebak acak)",
    )

    rows = []
    for rec in history:
        if rec["resolved"]:
            hasil = f"{'✅ Benar' if rec['correct'] else '❌ Meleset'} (hasil: {rec['actual_outcome']})"
        else:
            hasil = "⏳ Menunggu hasil"
        rows.append({
            "Pertandingan": rec["event_title"],
            "Proyeksi": rec["predicted_outcome"],
            "Peluang saat dicatat": f"{rec['probability']*100:.1f}%",
            "Jadwal": match_model.format_wib(rec.get("start_date")),
            "Hasil": hasil,
        })
    st.dataframe(rows, width="stretch", hide_index=True)

st.caption(
    "Angka probabilitas adalah harga pasar Polymarket apa adanya (wisdom of the crowd), "
    "bukan model prediksi independen. Confidence dihitung dari likuiditas market. "
    "Riwayat di atas mengukur seberapa sering favorit pasar benar-benar menang. "
    "Semua waktu dalam WIB. Bukan nasihat finansial/taruhan."
)
