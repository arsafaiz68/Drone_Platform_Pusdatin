# Batasan Implementasi & Pengembangan Lanjutan

Dokumen ini menjelaskan secara jujur apa yang sudah dan belum dapat dilakukan AI pada versi 1.0.

## Sudah berfungsi penuh
* Enam template, batch ≤ 24 video, antrean (Menunggu → Sedang dianalisis → Analisis selesai → Sedang diproses →
  Menunggu review → Selesai / Gagal / Dibatalkan), concurrency 1/2/4 dengan batas perangkat, jeda/lanjut/batal,
  isolasi kegagalan per video, pemulihan setelah aplikasi ditutup.
* Analisis visual lokal (kualitas, buram, kestabilan, gerak kamera, perubahan adegan, putar balik).
* Satu video sumber = satu video hasil. Seleksi momen & alokasi durasi agar tiap video hasil tepat 10–60 detik (kelipatan 5)
  (diisi dari bagian lain video yang sama bila kandidat AI kurang; video sumber yang lebih pendek dipakai utuh), keterwakilan titik yang terekam,
  tanpa adegan duplikat; peringatan & persetujuan bila footage kurang.
* Review, timeline editing, koreksi & reset ke hasil AI, penggantian footage, urutan, alokasi.
* Ekspor FFmpeg (stream copy bila kompatibel & selaras keyframe, selain itu re-encode dengan parameter seragam;
  NVENC → fallback libx264), potongan individual, preview, penamaan standar & anti-timpa.

## Memerlukan model atau dataset
| Fitur | Status v1.0 | Yang dibutuhkan |
|---|---|---|
| Identifikasi titik 1/2/3 | **Estimasi temporal**, bukan pengenalan lokasi. Keyakinan ditampilkan rendah. | Dataset berlabel dari koreksi operator + model klasifikasi scene/landmark |
| Deteksi kendaraan/orang | Aktif hanya jika model ONNX dipasang | File YOLO ONNX di `data/models` |
| Kondisi lalu lintas | Default *Tidak Teridentifikasi*; saran berbasis jumlah kendaraan hanya bila detektor ada, ditandai belum tervalidasi | Model/ambang yang divalidasi per jenis lokasi & ketinggian terbang |
| Putar balik | Heuristik visual; pada rekaman dengan jeda panjang, perubahan ketinggian ekstrem, atau rute tidak simetris bisa meleset → ditandai perlu verifikasi | Data berlabel untuk evaluasi/penyetelan |
| Putar balik sekunder (Gerbang Tol titik 4) | Pembalikan arah gerak kamera di zona titik 4 | Verifikasi operator |

## Batasan teknis lain
* Deteksi objek kendaraan dari ketinggian drone dengan model COCO umum kurang akurat; disarankan model yang dilatih
  footage udara.
* OpenCV pip standar tidak memakai CUDA; percepatan GPU analisis memerlukan build OpenCV-CUDA atau backend
  ONNX Runtime GPU (antarmuka `Detector` sudah disiapkan).
* Jeda batch bersifat "selesaikan video yang sedang berjalan lalu berhenti", bukan menghentikan di tengah video.
* Video H.265/4K diputar di browser melalui proxy H.264 480p yang dibuat otomatis (dapat dimatikan di Pengaturan).
* Mode stream copy hanya dipakai bila semua titik potong jatuh pada keyframe; jika tidak, re-encode agar durasi tepat.
* `start.bat` ditujukan untuk Windows; di OS lain jalankan perintah manual di README.

## Saran pengembangan berikutnya
1. Latih klasifikator titik per template dari dataset koreksi (ekspor JSONL sudah tersedia).
2. Model kepadatan kendaraan/penumpang khusus footage udara + validasi ambang kondisi lalu lintas.
3. Penyelarasan beberapa file dari satu penerbangan berdasarkan kemiripan visual tepi-tepi file.
4. Pengolahan audio (mis. mute otomatis bising angin) dan overlay teks lokasi/waktu opsional.
