# Panduan Drone Video Compiler

Drone Video Compiler adalah editor video sederhana di dalam Drone Video Platform untuk menyusun **satu video
final** dari beberapa video, gambar, teks, dan musik. Buka dari menu utama (kartu nomor 3) atau langsung di
<http://127.0.0.1:8000/compiler/>.

Semua proses berjalan di komputer ini. Preview diputar di browser, dan render memakai FFmpeg lokal.
Tidak ada video yang dikirim ke server luar.

## 1. Proyek

| Aksi | Cara |
|---|---|
| **New Project** | Halaman daftar proyek → isi nama, pilih rasio aspek → *New Project* |
| **Save Project** | Tombol *Save Project* atau `Ctrl+S`. Titik oranye di nama proyek berarti ada perubahan yang belum disimpan |
| **Load Project** | Klik kartu proyek di halaman daftar. *Load dari file…* membuka file `.json` hasil *Simpan ke file* |
| **Simpan ke file** | Menyimpan salinan proyek `.json` ke folder pilihan (File System Access API di Chrome/Edge; browser lain mengunduh file) |
| **Duplicate / Rename / Delete** | Ikon di setiap kartu proyek. Rename juga bisa dengan klik nama proyek di toolbar editor |

Proyek disimpan sebagai JSON di `data/compiler/projects/`. Isinya:
- nama proyek
- resolusi/rasio dan frame rate
- daftar media
- track dan layer
- posisi dan durasi setiap klip
- volume serta fade audio dan video
- pengaturan teks dan efek
- konfigurasi export

Menghapus proyek **tidak** menghapus file asli di komputer Anda.

## 2. Import media

- **Import / drag & drop.** Seret file dari Explorer ke panel *Media Bin*, atau klik **Import**. Banyak file
  sekaligus didukung.
  - Video: MP4, MOV, MKV, AVI, M4V, WEBM, MTS, WMV, dll.
  - Audio: MP3, WAV, AAC, M4A, OGG, FLAC, WMA.
  - Gambar: JPG, JPEG, PNG, WEBP, BMP, GIF, SVG. SVG otomatis dikonversi ke PNG.
  - File disalin ke backend lokal (`data/compiler/media`), tidak ke internet.
- **Path folder (ikon folder).** Tempel path file atau folder, satu per baris. File **tidak disalin**, tetapi
  dibaca langsung dari lokasinya. Cara ini lebih hemat disk untuk video drone berukuran besar.
- **Daftar Media Bin** menampilkan:
  - thumbnail
  - durasi
  - ukuran
  - resolusi
  - fps
  - tipe
- **Proxy preview.** Video yang tidak bisa diputar browser (mis. MKV/AVI/H.265) otomatis dibuatkan proxy
  preview 720p. Render akhir tetap memakai file asli.
- **Hapus media.** Tombol × menghapus media dari daftar proyek. File asli tidak dihapus.

## 3. Workspace

```
┌ Toolbar: Import · Split · Delete · Undo · Redo · Save Project · Simpan ke file ··· Export ┐
│ Media Bin │            Preview Monitor            │ Properti (Inspector) │
├───────────┴───────────────────────────────────────┴──────────────────────┤
│ Timeline: T1 Teks · I1 Gambar · V2 Overlay · V1 Video utama · A1 Audio · A2 Musik │
└───────────────────────────────────────────────────────────────────────────┘
```

- **Tinggi timeline** dapat diubah dengan menyeret garis pemisah.
- **Urutan layer.** Track di bagian atas daftar tampil paling depan. Ubah urutannya dengan ▲▼ di kepala track.
- **Kepala track** berisi:
  - 👁 sembunyikan
  - 🔊 bisukan
  - 🔒 kunci
  - slider volume track (0–200 %)

### Timeline

| Aksi | Cara |
|---|---|
| Menambah klip | Seret media dari Media Bin ke track, atau klik **+** pada media (ditambahkan di playhead; V1/A1 disambung ke akhir bila bertabrakan) |
| Menggeser klip | Seret badan klip ke kiri/kanan. Bisa juga dipindah ke track lain yang sesuai |
| Memotong / mengubah durasi | Seret tepi kiri/kanan klip (trim) |
| Split | Tekan `S` atau tombol *Split* di playhead (klip terpilih; tanpa pilihan = semua klip di playhead) |
| Hapus klip | `Delete` / tombol *Delete* |
| Duplikat klip | `Ctrl+D` |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Y` |
| Zoom | Slider zoom, tombol ±, atau `Ctrl` + scroll; ikon ⤢ untuk memuat seluruh timeline |
| Snapping | Ikon magnet: menempel ke tepi klip lain dan playhead |
| Playhead | Klik/seret ruler; `Spasi` putar/jeda; `←/→` per frame (`Shift` = 1 detik); `Home/End` |
| Panjang timeline | Inspector tanpa klip terpilih → *Panjang timeline*: Otomatis atau Manual (detik) |

**Track mana untuk media apa:**
- **V1/V2** menerima video dan gambar.
- **I1** menerima gambar.
- **T1** menerima teks.
- **A1/A2** menerima audio. File video di track audio hanya dipakai suaranya.

### Inspector (properti klip)

- **Waktu:**
  - mulai
  - durasi
  - titik masuk sumber
  - tombol *Pindah ke playhead* / *Durasi penuh*
- **Visual & posisi:**
  - opacity
  - skala
  - posisi X/Y (juga dengan **menyeret objek langsung di Preview Monitor**)
  - preset posisi (penuh, tengah, pojok)
  - fade in / fade out video atau gambar
- **Transisi.** *Crossfade dengan klip sebelumnya* (track video). Klip sebelumnya diperpanjang di bawah klip
  ini, jadi posisi klip tidak bergeser. Syaratnya, sumber klip sebelumnya masih punya sisa durasi.
- **Audio:**
  - volume 0–200 %
  - fade in / fade out (detik)
  - volume awal fade in dan volume akhir fade out
  - preset *Fade musik standar*

  Garis kuning pada klip audio di timeline menunjukkan amplop volume/fade.
- **Teks:**
  - isi (multi-baris)
  - font dan ukuran
  - warna, bold, italic
  - posisi atas/tengah/bawah dan perataan
  - latar teks (warna + opacity)
  - outline dan bayangan
  - durasi dan posisi teks diatur di track T1

Tanpa klip terpilih, Inspector menampilkan **pengaturan proyek**: rasio aspek (16:9, 9:16, 1:1, 4:3, Original),
warna latar, frame rate, dan panjang timeline.

## 4. Export / Render

Klik **Export**. Proyek disimpan otomatis sebelum render.

| Pengaturan | Pilihan |
|---|---|
| Resolusi | 1080p (1920×1080), 1440p (2560×1440), 2160p (3840×2160), atau ikuti resolusi asli. Ukuran mengikuti rasio aspek proyek, mis. 9:16 1080p = 1080×1920 |
| Frame rate | 24, 25, 30, 50, 60 fps, atau ikuti sumber |
| Format | MP4 H.264 (paling kompatibel) atau MP4 H.265/HEVC (file lebih kecil, bila tersedia) |
| Kualitas | **High** (CRF 18, slow), **Very High** (CRF 16, slow), **Maximum** (CRF 14, veryslow) |

**Spesifikasi output:**
- Audio AAC 320 kbps, 48 kHz stereo.
- Video `yuv420p`, profil High, `+faststart`, sehingga bisa diputar di Windows Media Player, VLC, ponsel, dan
  browser.

**Selama render ditampilkan:**
- progress bar dan persentase
- perkiraan waktu tersisa
- status
- tombol **Cancel render**

**Setelah selesai:**
- **Download hasil**, **Buka folder**, dan preview langsung.
- Informasi resolusi, durasi, format, dan ukuran file.
- File tersimpan di `data/exports/compiler/`.

**Peringatan perangkat.** Muncul bila spesifikasi kurang memadai, mis. 4K dengan RAM < 8 GB atau CPU 2 core.

## 5. Media berpindah folder (panggil ulang)

Saat proyek dibuka, Compiler memeriksa apakah semua file media masih ada. Bila ada file yang dipindah,
diganti nama, atau proyek dibuka di komputer lain, akan muncul dialog **Media tidak ditemukan**. Tombol merah
**"N media hilang"** di toolbar membuka dialog ini lagi kapan saja.

Pilihan di dialog:

- **Cari & sambungkan** — ketik atau **Pilih folder…** lokasi baru. Semua subfolder diperiksa dan file
  dicocokkan berdasarkan nama, lalu disambungkan sekaligus.
- **Panggil ulang** (per file) — pilih file pengganti lewat dialog Windows, atau tempel path-nya.
- **Buka folder** — membuka folder lama di Explorer. Bila folder itu sudah tidak ada, dibuka folder terdekat
  yang masih ada.

Setelah disambungkan:

- Semua klip yang memakai media tersebut di track mana pun langsung tersambung lagi.
- Posisi, durasi, dan pengaturan klip tidak berubah.
- Bila file baru lebih pendek dari file lama, ditampilkan peringatan.

Selama masih ada media hilang yang dipakai klip, Export ditahan. Klip seperti itu ditandai merah bergaris di
timeline.

## 6. Tema terang / gelap

Tombol **Terang | Gelap** ada di toolbar Compiler. Di menu utama, Downloader, dan Trimmer tersedia tombol
bulat mengambang di pojok kanan bawah. Pilihan tema berlaku di semua halaman. Compiler memakai mode gelap
bila tema belum pernah dipilih.

## 7. Keterbatasan

- **Preview vs hasil.** Preview memakai pemutaran browser, jadi di komputer lambat atau dengan banyak video 4K
  sekaligus, preview bisa tersendat. Hasil render tidak terpengaruh. Video non-web memakai proxy 720p untuk preview.
- **Volume di preview.** Di atas 100 % hanya terdengar di hasil render (browser membatasi volume preview pada 100 %).
- **Efek.** Efek dan transisi sengaja dibatasi pada fade, crossfade, dan opacity demi stabilitas render.
- **Durasi render.** Preset *Maximum Quality* (veryslow) dan resolusi 4K memerlukan waktu render jauh lebih lama.
- **Format gambar.** SVG dikonversi ke PNG saat diimpor. GIF dan WEBP animasi dipakai sebagai gambar diam.
- **Proyek yang dibuka di komputer lain.** Media harus ada di pustaka komputer tersebut. Media yang tidak
  ditemukan akan dilaporkan; impor ulang media yang sama.
