# Drone Video Platform

Satu aplikasi web **lokal** untuk pengolahan video drone pemantauan simpul & jaringan transportasi.
Di **menu utama** pilih salah satu modul:

| Modul | Alamat | Fungsi |
|---|---|---|
| **Drone Video Downloader** | <http://127.0.0.1:8000/downloader/> | Tempel laporan pemantauan WhatsApp → parsing → unduh video YouTube (maks. 1080p) ke folder pilihan dengan nama `DD.MM_HH.MM_Lokasi_Lalin.mp4` |
| **Drone Video Trimmer** | <http://127.0.0.1:8000/trimmer/> | Analisis AI lokal & pemotongan otomatis. Maks. **24 video** per batch; **setiap video sumber menjadi satu video hasil** berdurasi **10–60 detik (kelipatan 5, diatur dengan slider)**. Ekspor kualitas tinggi: resolusi & fps asli, H.264 CRF 16 preset slow (atau H.265), AAC 320 kbps, stream copy bila memungkinkan |
| **Drone Video Compiler** | <http://127.0.0.1:8000/compiler/> | Editor video multi-track sederhana (gaya Premiere Pro): Media Bin, Preview Monitor, timeline V1/V2/I1/T1/A1/A2, teks, fade audio/video, crossfade, proyek JSON, render MP4 H.264/H.265 hingga 4K. Panduan: [docs/PANDUAN_VIDEO_COMPILER.md](docs/PANDUAN_VIDEO_COMPILER.md) |

```
Laporan WhatsApp ─► Downloader (parsing + unduh) ─► folder video + _info_video_drone.json
                                                         │  (lokasi, tanggal, waktu, lalin, cuaca, URL)
                                                         ▼
                         Trimmer: impor → informasi video terisi otomatis → analisis AI
                                  → 1 video sumber = 1 video hasil (10–60 dtk)
                                  → Clipped_DD.MM_HH.MM_Lokasi_Lalin.mp4  (+ .json metadata)
```

* Satu backend **FastAPI** (127.0.0.1:8000) untuk kedua modul, satu frontend **React + Vite** multi-halaman,
  database **SQLite**, analisis **OpenCV**, pemrosesan video **FFmpeg**, unduhan **yt-dlp**.
* Seluruh analisis dan pemrosesan video berjalan di komputer ini (internet hanya untuk mengunduh dari YouTube
  dan untuk instalasi pertama).

---

## 1. Aturan durasi Trimmer (penting)

* **24 video = batas maksimal input** satu batch, bukan jumlah video yang digabung.
* **24 video masuk → 24 video hasil.** Video tidak digabung satu sama lain.
* Durasi **10–60 detik (kelipatan 5)** adalah durasi **setiap** video hasil, diambil dari video sumbernya sendiri:
  1. momen terbaik hasil analisis AI (titik pemantauan, kualitas, aktivitas lalu lintas);
  2. bila kurang, sisa durasi diambil dari bagian lain video yang sama — tersebar merata, tidak tumpang tindih,
     tanpa adegan berulang;
  3. bila video sumber lebih pendek dari target, seluruh video dipakai (perlu persetujuan durasi sebelum ekspor).
* Potongan disusun kronologis (urutan terbang drone). Operator tetap bisa mengubah, mengganti, dan mengurutkan
  potongan di halaman **Review dan Editing → Video hasil & timeline**.

## 2. Informasi video otomatis (tanpa isi satu-satu)

Setiap video yang berhasil diunduh dicatat di **`_info_video_drone.json`** di folder tujuan (lokasi, tanggal, waktu,
zona waktu, cuaca, kondisi lalin, rekayasa lalin, URL). Trimmer membaca informasi ini otomatis:

| Cara memasukkan video ke Trimmer | Sumber informasi |
|---|---|
| Tombol **“Proses di Trimmer”** di ringkasan batch Downloader | riwayat batch Downloader |
| **Batch Processing → Batch dari hasil unduhan** | riwayat batch Downloader atau folder |
| **Detail batch → Impor dari Downloader** | riwayat batch Downloader atau folder |
| **Tambah dari path lokal** | manifest di folder file, lalu pola nama file |
| **Tambah Video** (unggah) | pola nama file `DD.MM_HH.MM_Lokasi_Lalin.mp4` |

Informasi per video tampil di tabel **Daftar video** dan dapat dikoreksi (tombol **Ubah**); perubahan langsung
memperbarui nama file & metadata video hasilnya. Kelompok lokasi hanya menjadi **cadangan** untuk video yang belum
punya informasi sendiri.

## 3. Jenis lokasi (template pemantauan)

Tujuh template, masing-masing dengan urutan titik & putar balik sendiri:

| Template | Titik pemantauan | Contoh nama lokasi yang dikenali otomatis |
|---|---|---|
| **Pelabuhan** | jalan akses/antrean → gerbang/loket → area parkir/kantong penyangga → dermaga | `Pel. Merak`, `Pelabuhan Bakauheni` |
| **Terminal** | jalan akses → area penyangga/halaman → jalan keluar | `Terminal Pulo Gebang` |
| **Stasiun** | jalan akses → drop-off/halaman → jalan keluar | `Stasiun Gambir`, `St. Pasar Senen` |
| **Gerbang Tol** | persimpangan → gerbang → simpang susun → simpang kiri/kanan (putar balik di 4 & 5) | `GT Cikatama` |
| **Jalan Tol** | ekor antrean → kepala antrean/bottleneck | `Tol Jakarta-Cikampek KM 47` |
| **Tempat Istirahat (Rest Area)** | ±500 m sebelum masuk → area rest area → ±500 m akses keluar | `RA KM 57`, `Rest Area 207A` |
| **Jalan Arteri** | ekor kemacetan → kepala kemacetan/persimpangan/pasar | `Jl. Raya Puncak`, `Simpang Jomin` |

Jenis lokasi ditentukan **per video** dari nama lokasi hasil parsing, sehingga satu batch boleh berisi campuran
pelabuhan, gerbang tol, rest area, dst. Bila nama tidak dikenali, dipakai template batch/proyek. Jenis lokasi dapat
diubah di **Daftar video → Ubah** (kandidat lama dihapus dan video perlu dianalisis ulang).

## 4. Kebutuhan

| Komponen | Versi | Catatan |
|---|---|---|
| Windows | 10/11 64-bit | `start.bat` |
| Python | 3.10 – 3.13 | centang **Add python.exe to PATH**; biarkan *tcl/tk* tercentang (dialog “Pilih folder”) |
| Node.js | 18 LTS atau lebih baru | untuk build frontend |
| FFmpeg + FFprobe | 5.x – 7.x | letakkan di `tools\ffmpeg\bin\` atau di PATH (dipakai kedua modul) |
| GPU NVIDIA (opsional) | driver terbaru | NVENC dipakai untuk encoding bila tersedia |

## 5. Instalasi & menjalankan

1. Pastikan `tools\ffmpeg\bin\ffmpeg.exe` dan `ffprobe.exe` ada (lihat `tools\ffmpeg\LETAKKAN_FFMPEG_DI_SINI.txt`).
2. Double-click **`start.bat`**.

`start.bat` memeriksa Python/Node/FFmpeg → membuat `backend\.venv` → memasang dependensi Python → `npm install`
dan build frontend → menyiapkan database & folder `data\` → menjalankan backend → membuka **menu utama**
<http://127.0.0.1:8000>. Tutup jendela start.bat untuk menghentikan aplikasi.

Mode pengembangan (hot reload): `start-dev.bat` → <http://localhost:5173>.

> yt-dlp perlu diperbarui berkala bila YouTube berubah:
> `backend\.venv\Scripts\python -m pip install -U yt-dlp`

## 6. Struktur proyek

```
Drone_Video_Platform/
├── backend/app/
│   ├── downloader/      modul Downloader: router (/api/downloader), parser, jobs, ytdlp, localfs, manifest
│   ├── compiler/        modul Compiler: router (/api/compiler), store (proyek & pustaka media JSON), media, render
│   ├── api/             routes Trimmer (core, batch, final, media) + routes_integration (/api/integration)
│   ├── services/        video, ai, batch, selection, timeline, export, naming, hardware, integration
│   ├── core/ database/ schemas/ workers/
│   └── main.py          satu aplikasi FastAPI untuk kedua modul + penyaji frontend
├── frontend/
│   ├── index.html       menu utama          (src/menu)
│   ├── downloader/      halaman Downloader  (src/downloader, React + TS + Tailwind)
│   ├── trimmer/         halaman Trimmer     (src/trimmer, React)
│   └── compiler/        halaman Compiler    (src/compiler, React, tema gelap editor)
├── data/                database, uploads, exports, temporary, models, downloader/history (otomatis)
├── docs/  tests/  tests/downloader/  tools/ffmpeg/
└── start.bat  start-dev.bat  run-tests.bat
```

## 7. API

* Downloader — `/api/downloader/...`: `health`, `parse`, `naming/preview`, `local/*`, `batches`,
  `batches/{id}` (+ `cancel`, `retry`, `jobs/{job}/cancel|retry`), WebSocket `batches/{id}/ws`.
* Integrasi — `/api/integration/...`: `GET downloads`, `GET downloads/{dl_id}`, `GET folder?path=`,
  `POST batches/{id}/import`, `POST batch-from-download`.
* Trimmer — `/api/...` (sama seperti AI Drone Trimmer) dengan perubahan:
  `POST /api/batches/{id}/final-videos` membuat **satu video hasil per video sumber**;
  `POST /api/final-videos` menerima `source_video_id`; `PATCH /api/videos/{id}` menerima `location_name`,
  `traffic_condition`, `event_date`, `event_time`; durasi valid 10–60 detik (kelipatan 5).

* Trimmer — `GET /api/final-videos/{id}/export-info`: resolusi/fps/durasi sumber, parameter output, mode
  (stream copy / re-encode), dan perkiraan ukuran file sebelum ekspor.
* Compiler — `/api/compiler/...`: `system`, `media` (`upload?filename=`, `register`, `status`, `{id}/file|thumb|wave`),
  `projects` (CRUD, `import`, `{id}/rename|duplicate|estimate|render|renders`), `renders/{id}` (+ `cancel`,
  `download`, `stream`).

Dokumentasi interaktif: <http://127.0.0.1:8000/docs>.

## 8. Pengujian

```bat
run-tests.bat
```
Mencakup modul Trimmer (`tests/`), modul Downloader (`tests/downloader/`), dan integrasi
(`tests/test_platform_integration.py`). Daftar skenario: [docs/PANDUAN_PENGUJIAN_BATCH.md](docs/PANDUAN_PENGUJIAN_BATCH.md).

## 9. Dari aplikasi lama

* Folder **AI_Drone_Trimmer** dan **local batch-youtube-downloader** tidak diubah dan masih bisa dipakai.
* Riwayat batch Downloader lama sudah disalin ke `data\downloader\history`, sehingga hasil unduhan lama
  langsung bisa diimpor ke Trimmer.
* Database Trimmer lama (`data\database\ai_drone_trimmer.db`) bisa disalin ke folder `data\database\` platform
  ini saat aplikasi tidak berjalan; kolom baru ditambahkan otomatis (migrasi) tanpa menghapus data.
