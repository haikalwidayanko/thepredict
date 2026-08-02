# Panduan Deploy & Troubleshooting

## Deploy normal

1. Buka [share.streamlit.io](https://share.streamlit.io), login dengan GitHub.
2. Klik **Create app** → **Deploy a public app from GitHub**.
3. Isi:
   - Repository: `haikalwidayanko/thepredict`
   - Branch: `main`
   - Main file path: `app.py`
4. Klik **Deploy**.

Tidak ada secrets/API key yang perlu diisi — semua endpoint yang dipakai publik.

---

## Error: "You do not have access to this app or it does not exist"

Ini error paling umum di Streamlit Community Cloud dan **hampir selalu soal
otorisasi GitHub**, bukan soal kode.

### Penyebabnya

Community Cloud mengidentifikasi app lewat **GitHub coordinates**: kombinasi
`owner + repository + branch + entrypoint file path`. Kalau salah satu dari
empat itu berubah setelah app pernah dideploy — atau kalau token OAuth
Streamlit ke GitHub sudah kedaluwarsa/kurang izin — kamu kehilangan hak admin
atas app tersebut, dan Streamlit menampilkan pesan "you do not have access".

### Solusi resmi: revoke & re-authorize OAuth

Langkah ini memaksa Streamlit meminta izin GitHub dari awal.

1. **Sign out** dari Community Cloud
   (klik nama workspace di pojok kanan atas → **Sign out**).

2. Buka **<https://github.com/settings/applications>**

3. Cari aplikasi bernama **`Streamlit`** → klik menu titik tiga → **Revoke**.

   > ⚠️ **Penting:** revoke yang namanya **`Streamlit`** saja.
   > Aplikasi **`Streamlit Community Cloud`** itu beda — fungsinya cuma
   > mengelola identitas/email, dan **tidak perlu** disentuh.

4. Konfirmasi dengan **"I understand, revoke access"**.

5. Kembali ke [share.streamlit.io](https://share.streamlit.io) dan login lagi.
   Sekarang GitHub akan memunculkan halaman izin — klik **Authorize streamlit**.

6. Hapus app lama yang gagal/nyangkut (kalau ada) dari dashboard, lalu
   **Create app** ulang dengan koordinat di bagian atas dokumen ini.

### Kalau masih gagal

- Pastikan kamu punya **admin permission** atas repo (otomatis terpenuhi kalau
  repo itu milik akun kamu sendiri).
- Pastikan repo **public**, branch **`main`**, dan `app.py` ada di **root**.
- Hindari **spasi dan karakter non-ASCII (termasuk emoji)** pada nama file/folder
  di repo — ini pernah memicu error yang sama. Semua path di repo ini sudah ASCII.
- Kalau repo milik organisasi, owner organisasi harus mengizinkan OAuth app
  Streamlit di setting GitHub organisasi.

---

## Alternatif hosting

Kalau Streamlit Community Cloud tetap bermasalah, app ini bisa dijalankan di
platform lain tanpa perubahan kode:

| Platform | Catatan |
|---|---|
| [Hugging Face Spaces](https://huggingface.co/spaces) | Pilih SDK **Streamlit**, gratis, tidak perlu OAuth GitHub — bisa upload/push langsung ke repo Space |
| [Render](https://render.com) | Start command: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0` |
| [Railway](https://railway.app) | Sama seperti Render |

Catatan: fitur **Match Predictor** butuh akses ke `gamma-api.polymarket.com`.
Kalau platform hosting-nya memblokir domain itu, halaman tersebut akan
menampilkan error sementara halaman Crypto Predictor tetap jalan.
