# Predictor Hub

Web app Streamlit dengan dua fitur:

1. **Crypto Predictor** — menampilkan koin USDT perpetual yang paling volatile
   hari ini (berdasarkan rentang harga intraday & volume), lalu memberi prediksi
   arah jangka pendek dari model ensemble rule-based (RSI, EMA 9/21 cross,
   momentum, funding rate, order book imbalance). Sumber data otomatis memilih
   antara Binance Futures dan Gate.io Futures (lihat bagian
   [Sumber data & blokir jaringan](#sumber-data--blokir-jaringan)).
2. **Tennis Predictor** — menampilkan pertandingan tennis **hari ini** (tanggal
   WIB) dari Polymarket beserta jam mainnya, dengan probabilitas menang dari
   harga pasar dan label confidence berdasarkan likuiditas. Hanya menampilkan
   pasar **hasil akhir pertandingan** — pasar per-set, total games, dan prop
   lain disaring keluar. Dilengkapi riwayat proyeksi dengan hit rate dan
   Brier score.

Tidak ada notifikasi atau proses background — semua data diambil live saat
kamu membuka/refresh halaman, dan kamu yang memilih coin/pertandingan mana
yang mau dilihat.

## Menjalankan secara lokal

```bash
pip install -r requirements.txt
streamlit run app.py
```

Butuh koneksi internet (memanggil `fapi.binance.com` dan
`gamma-api.polymarket.com`, keduanya API publik tanpa API key).

## Struktur proyek

```
app.py                          # halaman utama
pages/
  1_Crypto_Predictor.py
  2_Match_Predictor.py
src/
  market_data.py                # facade: pilih provider yang bisa dihubungi
  binance_client.py             # provider 1: Binance USDT-M Futures
  gateio_client.py              # provider 2: Gate.io USDT perpetual (fallback)
  errors.py                     # MarketDataError (exception bersama)
  polymarket_client.py          # fetch data Polymarket Gamma API (tennis)
  indicators.py                 # RSI, EMA, momentum, order book imbalance
  crypto_model.py               # ensemble scoring -> arah + confidence
  match_model.py                # probabilitas, jadwal WIB, filter pasar per-set
  tracking.py                   # log prediksi lokal + hit-rate & Brier score
data/
  predictions_log.json          # dibuat otomatis, tidak masuk git
  match_predictions_log.json    # dibuat otomatis, tidak masuk git
```

## Sumber data & blokir jaringan

Sebagian ISP (termasuk banyak ISP di Indonesia) memblokir domain exchange
kripto dan Polymarket di level DNS — query DNS biasa mengembalikan `NXDOMAIN`
walaupun domainnya sebenarnya hidup.

**Crypto Predictor** menangani ini otomatis lewat `src/market_data.py`: ia
mencoba Binance dulu, dan kalau tidak bisa dihubungi, otomatis pindah ke
Gate.io. Provider yang aktif ditampilkan di bagian atas halaman. Jadi:

| Lingkungan | Provider aktif |
|---|---|
| Jaringan yang memblokir Binance | Gate.io Futures |
| Streamlit Cloud / jaringan bebas | Binance Futures |

Harga antar exchange berbeda tipis, tapi korelasinya sangat tinggi sehingga
sinyal arah dari model tetap sebanding.

**Match Predictor** tidak punya fallback — datanya hanya ada di Polymarket.
Kalau domainnya diblokir, halaman ini akan menampilkan pesan error dan fiturnya
baru hidup saat aplikasi di-deploy ke cloud (server cloud tidak berada di balik
ISP kamu).

Untuk mengecek sendiri apakah sebuah domain diblokir DNS:

```bash
nslookup fapi.binance.com
```

Kalau hasilnya `Non-existent domain` padahal situs lain normal, itu blokir DNS,
bukan domain mati.

## Deploy ke Streamlit Community Cloud

1. Push repo ini ke GitHub.
2. Buka [share.streamlit.io](https://share.streamlit.io), connect ke repo,
   set **Main file path** ke `app.py`.
3. Deploy. Tidak ada secrets/API key yang perlu diisi karena semua endpoint
   yang dipakai bersifat publik.

> Kalau muncul error **"You do not have access to this app or it does not
> exist"**, lihat [DEPLOY.md](DEPLOY.md) — itu masalah otorisasi GitHub, bukan
> masalah kode, dan ada langkah perbaikan resminya di sana.

Catatan: filesystem di Streamlit Community Cloud bersifat sementara (reset
saat app restart/redeploy), jadi `data/predictions_log.json` (dipakai untuk
menghitung hit-rate crypto predictor) akan ikut reset. Ini cukup untuk
melihat track record berjalan (rolling), bukan pengganti database permanen.

## Metodologi & keterbatasan

- **Crypto model** bersifat rule-based, bukan machine learning terlatih —
  dipilih supaya setiap sinyal dan bobotnya bisa diaudit (lihat tabel
  "Rincian sinyal" di halaman). Ini bukan jaminan akurasi; pasar kripto
  sangat noisy pada horizon pendek.
- **Tennis predictor** sengaja menampilkan harga Polymarket apa adanya
  (implied probability), bukan model independen yang "mengalahkan" pasar —
  mengklaim edge atas market tanpa model independen yang tervalidasi akan
  menyesatkan. Label confidence dari likuiditas membantu menilai seberapa
  bisa diandalkan harga tersebut. Riwayat proyeksi mengukur seberapa sering
  favorit pasar benar-benar menang (hit rate) dan seberapa terkalibrasi
  probabilitasnya (Brier score: 0 = sempurna, 0.25 = setara tebak acak).
- Filter pasar per-set memakai **dua lapis** di
  `match_model.is_match_winner_market()`: blocklist kata kunci (`set`,
  `total games`, `o/u`, `handicap`, dll) **dan** pengecekan label outcome —
  pasar dengan outcome `Over`/`Under` selalu ditolak. Lapis kedua ini penting
  karena judul seperti `Match O/U 21.5` bisa lolos dari kata kunci.
- Daftar dibatasi ke pertandingan yang **mulai pada tanggal WIB hari ini**
  (`match_model.is_today_wib()`). Perbandingan sengaja dilakukan di WIB, bukan
  UTC — pertandingan jam 06:30 WIB masih tercatat "kemarin" menurut UTC dan
  akan hilang kalau difilter pakai UTC. Cache halaman memakai tanggal sebagai
  bagian dari key supaya otomatis berganti saat lewat tengah malam.
- Ambang likuiditas (`Tinggi`/`Sedang`/`Rendah`/`Sangat rendah`) dikalibrasi
  khusus untuk market tennis: **≥ $10.000** Tinggi, **≥ $1.000** Sedang,
  **≥ $100** Rendah, di bawah itu Sangat rendah. Angka lama (50k/5k) dipakai
  untuk market politik besar dan membuat hampir semua pertandingan tennis
  terlihat "Rendah" padahal likuiditasnya wajar untuk cabang ini. Ada filter
  di halaman (`st.select_slider`, default **≥ $10.000**) yang membuang *market*
  (bukan cuma event) di bawah ambang pilihan — ini juga menyingkirkan duplikat
  market nyaris mati ($1 likuiditas) yang kadang muncul berdampingan dengan
  market asli untuk pertanyaan yang sama.
- Pertandingan yang diperkirakan sudah selesai (>5 jam sejak jadwal mulai)
  dibuang total dari daftar, bukan cuma dilabeli "Selesai" — lihat
  `match_model.is_likely_finished()`. Ini estimasi berbasis waktu, **bukan**
  skor langsung, karena tidak ada sumber live-score yang terhubung; buffer
  5 jam sengaja longgar supaya pertandingan best-of-5 Grand Slam yang panjang
  tidak ikut terbuang saat masih berlangsung.
- "Perkiraan selesai" dihapus dari tampilan karena nilainya berasal dari
  `endDate` Polymarket (batas resolusi market, kadang lebih dari seminggu
  setelah pertandingan), bukan jam selesai pertandingan asli.
- Tiap pertandingan punya link pencarian Google yang di-scope ke Flashscore
  (`match_model.external_schedule_link()`) untuk verifikasi jadwal/skor asli.
  Ini sengaja pakai link pencarian, bukan URL match Flashscore langsung —
  kita tidak punya ID match Flashscore untuk suatu event Polymarket, dan
  menebak URL berisiko link mati/salah.
- Outcome `Yes`/`No` dari Polymarket diterjemahkan jadi **nama pemain** oleh
  `match_model.label_outcomes()` (misal "Will Norrie win?" → `Cameron Norrie`
  vs `Mariano Navone`). Kalau pemetaannya tidak yakin, label asli dibiarkan
  daripada menebak. Nilai mentahnya tetap disimpan di log prediksi supaya
  pencocokan hasil saat market settle tidak rusak.
- Ini bukan nasihat finansial maupun ajakan berjudi. Gunakan sebagai salah
  satu input riset, bukan satu-satunya dasar keputusan.
- Perhatikan aspek legal di yurisdiksi kamu: di Indonesia, Binance tidak
  terdaftar di Bappebti, dan prediction market seperti Polymarket termasuk
  kategori yang dilarang. Aplikasi ini hanya membaca data pasar publik dan
  tidak melakukan transaksi apa pun.

## Ide pengembangan lanjutan

- Tambah model independen (mis. Elo rating dari histori pertandingan) untuk
  match predictor supaya bisa membandingkan estimasi sendiri vs harga pasar
  dan mendeteksi mispricing.
- Ganti scoring rule-based crypto dengan model terlatih (logistic
  regression/gradient boosting) di atas data historis Binance, lalu
  backtest dan tampilkan metrik seperti Brier score.
- Pindahkan `predictions_log.json` ke database persisten (mis. Supabase/
  SQLite eksternal) supaya track record tidak reset saat redeploy.
