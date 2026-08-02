import streamlit as st

from src import match_model
from src import polymarket_client as pm

st.set_page_config(page_title="Match Predictor", page_icon="🏆", layout="wide")
st.title("🏆 Match Predictor — Polymarket")
st.caption("Sepakbola & Tennis · probabilitas implisit dari harga pasar Polymarket, live saat halaman dibuka")


@st.cache_data(ttl=90, show_spinner=False)
def load_events(category: str):
    return pm.get_active_events(category)


category = st.radio("Cabang olahraga", list(pm.TAG_IDS.keys()), horizontal=True)

try:
    events = load_events(category)
except pm.PolymarketError as exc:
    st.error(str(exc))
    st.stop()

if not events:
    st.info(f"Tidak ada pertandingan {category} yang aktif di Polymarket saat ini.")
    st.stop()

event_labels = [f"{e['title']} (volume 24h ${e['volume24hr']:,.0f})" for e in events]
choice = st.selectbox("Pilih pertandingan/event", range(len(events)), format_func=lambda i: event_labels[i])
selected_event = events[choice]

st.subheader(selected_event["title"])
if selected_event.get("end_date"):
    st.caption(f"Berakhir: {selected_event['end_date']}")

for market in selected_event["markets"]:
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

st.caption(
    "Angka probabilitas di atas adalah harga pasar Polymarket apa adanya (wisdom of the "
    "crowd), bukan model prediksi independen. Confidence dihitung dari likuiditas market — "
    "makin tipis likuiditasnya, makin gampang harganya meleset/di-manipulasi. Bukan nasihat finansial/taruhan."
)
