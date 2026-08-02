# Predictor Hub

Web app Streamlit dengan dua fitur:

1. **Crypto Predictor** — menampilkan koin USDT perpetual yang paling volatile
   hari ini (berdasarkan rentang harga intraday & volume), lalu memberi prediksi
   arah jangka pendek dari model ensemble rule-based (RSI, EMA 9/21 cross,
   momentum, funding rate, order book imbalance). Sumber data otomatis memilih
   antara Binance Futures dan Gate.io Futures (lihat bagian
   [Sumber data & blokir jaringan](#sumber-data--blokir-jaringan)).
2. **Match Predictor** — menampilkan pertandingan sepakbola & tennis yang
   sedang aktif di Polymarket, dengan probabilitas implisit dari harga pasar
   dan label confidence berdasarkan likuiditas.

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
  polymarket_client.py          # fetch data Polymarket Gamma API
  indicators.py                 # RSI, EMA, momentum, order book imbalance
  crypto_model.py               # ensemble scoring -> arah + confidence
  match_model.py                # probabilitas implisit + confidence likuiditas
  tracking.py                   # log prediksi lokal + hit-rate rolling
data/
  predictions_log.json          # dibuat otomatis, tidak masuk git
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
- **Match predictor** sengaja menampilkan harga Polymarket apa adanya
  (implied probability), bukan model independen yang "mengalahkan" pasar —
  mengklaim edge atas market tanpa model independen yang tervalidasi akan
  menyesatkan. Label confidence dari likuiditas membantu menilai seberapa
  bisa diandalkan harga tersebut.
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
