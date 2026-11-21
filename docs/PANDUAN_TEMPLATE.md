# Panduan Enam Template Pemantauan

Template disimpan terpusat di `backend/app/core/templates_config.py` dan disinkronkan ke tabel `templates`
dan `template_points` setiap aplikasi dijalankan. Setiap titik memiliki:

* **importance (bobot)** — menentukan porsi durasi pada video final (lebih besar = lebih lama).
* **zone_weight** — panjang relatif zona waktu saat titik diestimasi tanpa GPS (Home Point 0,5; titik lain 1,0).

`H` = Home Point (titik awal penerbangan). Secara default footage H **tidak** dimasukkan ke video final
(dapat diaktifkan di Pengaturan → "Sertakan footage Home Point").

| # | Template | Pergi | Kembali | Putar balik |
|---|---|---|---|---|
| 1 | Terminal | H → 1 → 2 → 3 | 3 → 2 → 1 → H | titik 3 |
| 2 | Stasiun | H → 1 → 2 → 3 | 3 → 2 → 1 → H | titik 3 |
| 3 | Gerbang Tol | H → 1 → 2 → 3 → 4 → 5 | 5 → 4 → 3 → 2 → 1 → H | **titik 4 dan titik 5** |
| 4 | Jalan Tol | H → 1 → 2 | 2 → 1 → H | titik 2 |
| 5 | Jalan Arteri | H → 1 → 2 | 2 → 1 → H | titik 2 |
| 6 | Tempat Istirahat Jalan Tol | H → 1 → 2 → 3 | 3 → 2 → 1 → H | titik 3 |

## Template 1 — Terminal
1. **Jalan akses terminal** (bobot 1,0) — kendaraan yang bergerak menuju terminal.
2. **Area penyangga / halaman** (1,6) — bus, kendaraan, kepadatan penumpang.
3. **Jalan keluar terminal** (1,2) — arus kendaraan meninggalkan terminal. Drone putar balik di sini.

## Template 2 — Stasiun
1. **Jalan akses stasiun** (1,0). 2. **Area drop-off dan halaman** (1,6) — aktivitas penumpang & kendaraan.
3. **Jalan keluar stasiun** (1,2). Putar balik setelah titik 3.

## Template 3 — Gerbang Tol
1. **Persimpangan menuju gerbang tol** (1,0). 2. **Area gerbang tol** (1,6). 3. **Simpang susun / interchange** (1,2).
4. **Jalan simpang kiri ±500 m** (1,0) — **putar balik**. 5. **Jalan simpang kanan ±500 m** (1,0) — **putar balik**.

Dua instruksi putar balik dipertahankan: putar balik utama (setelah titik 5) memisahkan pergi/kembali; putar balik
di titik 4 dideteksi sebagai pembalikan arah gerak kamera di dalam zona titik 4 dan ditandai `↻` pada kandidat.
Bila lintasan aktual berbeda (mis. H→1→2→3→4→3→5), ubah di **Batch → Konfigurasi lintasan**.

## Template 4 — Jalan Tol
1. **Ekor antrean / kemacetan** (1,2). 2. **Kepala antrean / bottleneck** (1,5). Putar balik setelah titik 2.

## Template 5 — Jalan Arteri
1. **Ekor kemacetan** (1,2). 2. **Kepala kemacetan / persimpangan / pasar** (1,5). Putar balik setelah titik 2.

## Template 6 — Tempat Istirahat Jalan Tol
1. **±500 m sebelum pintu masuk** (1,1) — antrean. 2. **Area tempat istirahat** (1,6) — okupansi parkir & fasilitas.
3. **±500 m dari akses keluar** (1,1) — arus kembali ke tol. Putar balik setelah titik 3.

## Cara kerja dengan rekaman

* **Satu video panjang** berisi seluruh lintasan → biarkan pemetaan "Otomatis". Lintasan dibagi menurut urutan
  template; pada mode *pergi dan kembali* batas pergi/kembali ditentukan dari deteksi putar balik.
* **Beberapa video pendek** per bagian lintasan → klik kolom **Titik** pada tiap video dan pilih titik yang
  dicakup sesuai urutan kemunculan (mis. video A = `1→2`, video B = `3`), serta arah bila perlu. Urutan file
  tidak diasumsikan sama dengan urutan titik.
* **Beberapa lokasi dalam satu batch** → buat kelompok lokasi dan tetapkan kelompok tiap video. Setiap kelompok
  menjadi informasi cadangan; setiap video sumber menghasilkan satu video hasil sendiri (tidak digabung).

## Menambah template baru

Tambahkan entri pada daftar `TEMPLATES` di `templates_config.py` (kode unik, titik, rute pergi/kembali, putar balik),
lalu jalankan ulang aplikasi. Tidak perlu migrasi database.
