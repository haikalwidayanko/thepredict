# Predictor — Crypto Perpetual

Web app Streamlit untuk mencari koin perpetual USDT yang sedang bergerak, lalu
mengukur arahnya dengan model yang bisa diaudit.

- Menampilkan koin USDT perpetual yang paling volatile hari ini (berdasarkan
  rentang harga intraday & volume).
- Prediksi arah jangka pendek dari model ensemble rule-based **multi-timeframe**
  (RSI, EMA 9/21 cross, momentum dihitung terpisah di 15m/1h/4h lalu digabung,
  plus funding rate & order book imbalance).
- Level **Entry / Stop Loss / Take Profit** dihitung dari ATR — volatilitas
  nyata koin itu, bukan persentase tetap.
- Tab **Backtest** untuk menguji ulang model di data historis (walk-forward,
  tanpa lookahead bias): sinyal mana yang benar-benar menambah akurasi, dan
  apakah TP benar-benar kena duluan dibanding SL.
- Tab **Riwayat** untuk melacak akurasi prediksi yang kamu catat sendiri.

Sumber data otomatis memilih antara Binance Futures dan Gate.io Futures (lihat
bagian [Sumber data & blokir jaringan](#sumber-data--blokir-jaringan)).

Tidak ada notifikasi atau proses background — semua data diambil live saat
kamu membuka/refresh halaman, dan kamu yang memilih koin mana yang mau dilihat.

## Menjalankan secara lokal

```bash
pip install -r requirements.txt
streamlit run app.py
```

Butuh koneksi internet (memanggil `fapi.binance.com` atau `api.gateio.ws`,
keduanya API publik tanpa API key).

## Struktur proyek

```
app.py                          # halaman utama
pages/
  1_Crypto.py                   # prediksi, backtest, riwayat
src/
  market_data.py                # facade: pilih provider yang bisa dihubungi
  binance_client.py             # provider 1: Binance USDT-M Futures
  gateio_client.py              # provider 2: Gate.io USDT perpetual (fallback)
  errors.py                     # MarketDataError (exception bersama)
  indicators.py                 # RSI, EMA, momentum, ATR, order book imbalance
  crypto_model.py               # ensemble scoring -> arah, confidence, level SL/TP
  backtest.py                   # simulasi walk-forward di data historis
  tracking.py                   # log prediksi lokal + hit-rate & Brier score
  ui.py                         # logo, warna aksen, header halaman
data/
  predictions_log.json          # dibuat otomatis, tidak masuk git
```

## Sumber data & blokir jaringan

Sebagian ISP (termasuk banyak ISP di Indonesia) memblokir domain exchange
kripto di level DNS — query DNS biasa mengembalikan `NXDOMAIN` walaupun
domainnya sebenarnya hidup.

Aplikasi menangani ini otomatis lewat `src/market_data.py`: ia mencoba Binance
dulu, dan kalau tidak bisa dihubungi, otomatis pindah ke Gate.io. Provider yang
aktif ditampilkan di bagian atas halaman. Jadi:

| Lingkungan | Provider aktif |
|---|---|
| Jaringan yang memblokir Binance | Gate.io Futures |
| Streamlit Cloud / jaringan bebas | Binance Futures |

Harga antar exchange berbeda tipis, tapi korelasinya sangat tinggi sehingga
sinyal arah dari model tetap sebanding. Perhatikan bahwa **format simbol
berbeda** antar provider (`BTCUSDT` di Binance, `BTC_USDT` di Gate.io) — ikuti
format yang muncul di tabel koin pada provider yang sedang aktif.

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
menghitung hit-rate) akan ikut reset. Ini cukup untuk melihat track record
berjalan (rolling), bukan pengganti database permanen.

## Metodologi & keterbatasan

- **Model** bersifat rule-based, bukan machine learning terlatih — dipilih
  supaya setiap sinyal dan bobotnya bisa diaudit (lihat tabel "Rincian sinyal"
  di halaman). Ini bukan jaminan akurasi; pasar kripto sangat noisy pada
  horizon pendek.
- **Multi-timeframe (MTF)**: `crypto_model.timeframe_score()` menghitung
  RSI/EMA-cross/momentum secara independen untuk tiap timeframe (15m/1h/4h),
  lalu digabung berbobot (`MTF_WEIGHTS`, default 15m=25%/1h=40%/4h=35% —
  timeframe lebih tinggi diberi bobot lebih besar karena less noisy, tapi ini
  asumsi awal, bukan kesimpulan tervalidasi). Funding rate & order book
  imbalance dihitung sekali di level gabungan, bukan per timeframe, karena
  keduanya snapshot pasar yang sama untuk semua timeframe.
- **Backtest** (`src/backtest.py`) menguji ulang **hanya bagian price-action**
  dari model (RSI+EMA+momentum lintas 15m/1h/4h) memakai data historis nyata,
  secara walk-forward — di tiap titik waktu simulasi, model cuma melihat data
  yang tersedia sampai titik itu (diverifikasi lewat test regresi khusus yang
  memotong data masa depan dan memastikan skor historis tidak berubah).
  Funding rate dan order book imbalance **sengaja tidak diikutkan**: Binance
  dan Gate.io tidak menyediakan histori kedalaman order book (cuma snapshot
  live), jadi menyertakan salah satu tapi tidak yang lain akan menguji
  ensemble yang berbeda dari yang benar-benar berjalan live. Hasil backtest
  karena itu adalah **batas bawah** performa model penuh, bukan angka final.
  Output-nya termasuk breakdown per bucket confidence (mengecek apakah
  confidence tinggi memang lebih akurat) dan hit rate tiap sinyal individual
  per timeframe (mengecek komponen mana yang benar-benar menambah nilai).
- **Entry/SL/TP** (`crypto_model.compute_levels()`) dihitung dari ATR(14)
  15m: SL = 1.5×ATR, TP = 3×ATR (risk:reward 1:2 — bar minimum umum dalam
  trading, bukan hasil optimasi). Backtest menguji level ini secara historis
  dengan menelusuri high/low tiap candle ke depan (sampai 16 jam) untuk lihat
  TP atau SL yang kena duluan; kalau satu candle menyentuh keduanya sekaligus
  (candle lebar/gap), diasumsikan SL yang menang (konservatif, karena data
  OHLC tidak bisa memastikan urutan sebenarnya dalam candle itu). Expectancy
  dilaporkan dalam satuan R (1R = jarak SL) berdasarkan win rate historis,
  bukan diasumsikan otomatis untung dari rasio R:R di atas kertas.
- **Daftar koin berubah-ubah** setiap halaman dibuka: peringkatnya berasal dari
  rentang harga 24 jam yang terus bergerak, dengan cache 60 detik.
- Ini bukan nasihat finansial. Level Entry/SL/TP adalah referensi berbasis
  volatilitas, bukan sinyal beli/jual. Gunakan sebagai salah satu input riset,
  bukan satu-satunya dasar keputusan.
- Perhatikan aspek legal di yurisdiksi kamu: di Indonesia, Binance tidak
  terdaftar di Bappebti. Aplikasi ini hanya membaca data pasar publik dan
  tidak melakukan transaksi apa pun.

## Ide pengembangan lanjutan

- Ganti scoring rule-based dengan model terlatih (logistic regression/gradient
  boosting) di atas data historis, lalu bandingkan hasil backtest-nya dengan
  model rule-based sekarang.
- Pakai hasil backtest untuk menyetel ulang bobot sinyal (`WEIGHTS` dan
  `MTF_WEIGHTS`) secara empiris, bukan asumsi — misalnya menurunkan bobot RSI
  yang sering di bawah 50% hit rate pada pasar trending.
- Pindahkan `predictions_log.json` ke database persisten (mis. Supabase/
  SQLite eksternal) supaya track record tidak reset saat redeploy.
