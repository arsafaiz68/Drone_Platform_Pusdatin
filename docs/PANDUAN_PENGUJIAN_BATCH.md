# Panduan Pengujian Batch Processing

## Pengujian otomatis

```bat
run-tests.bat
```
Video uji dibuat sekali di `tests\.assets\` (butuh FFmpeg). Seluruh tes memakai folder data sementara,
sehingga data kerja di `data\` tidak tersentuh.

| # | Skenario | Tes |
|---|---|---|
| 1 | Upload satu video | `test_batch.py::test_upload_single_video`, `test_api.py::test_full_flow` |
| 2 | Upload 24 video sekaligus | `test_batch.py::test_upload_24_and_reject_25` |
| 3 | Penolakan 25 video | idem + `test_api.py` (HTTP 400, tidak ada file tersimpan) |
| 4 | Video durasi pendek (3 dtk) | `test_analysis.py::test_short_video` |
| 5 | Video durasi panjang (4 menit) | `test_analysis.py::test_long_video` |
| 6 | Resolusi berbeda (640×480 + 1280×720, dengan/tanpa audio) | `test_analysis.py::test_different_resolution_video`, `test_timeline_export.py` |
| 7 | Video final 30 dtk | `test_selection.py::test_total_duration_matches_target[*-30-*]` |
| 8 | Video final 60 dtk | `test_selection.py::test_total_duration_matches_target[*-60-*]` |
| 9 | Validasi total durasi | `test_selection.py`, `test_timeline_export.py::test_replace_reorder_allocation` |
| 10 | Concurrency 1, 2, 4 | `test_batch.py::test_concurrency_limit[1/2/4]` (puncak paralel ≤ setelan) |
| 11 | Satu video gagal, lainnya lanjut | `test_batch.py::test_failure_isolation` |
| 12 | Jeda & lanjutkan | `test_batch.py::test_pause_and_resume` |
| 13 | Pembatalan batch | `test_batch.py::test_cancel_batch` |
| 14 | Pemulihan status setelah restart | `test_batch.py::test_recovery_after_restart` |
| 15 | Ubah timestamp manual | `test_timeline_export.py::test_manual_timestamp_edit` |
| 16 | Ganti kandidat segmen | `test_timeline_export.py::test_replace_reorder_allocation` |
| 17 | Ubah urutan segmen | idem |
| 18 | Ubah alokasi durasi | idem |
| 19 | Ekspor potongan individual | `test_timeline_export.py::test_export_final_and_individual` |
| 20 | Ekspor video gabungan | idem (durasi hasil 30 ± 0,25 dtk) |
| 21 | Pergi saja | `test_analysis.py::test_outbound_only_mode` |
| 22 | Pergi dan kembali | `test_analysis.py::test_round_trip_turnaround_detected`, `test_gerbang_tol_round_trip_zones` |
| 23 | CPU fallback | `test_batch.py::test_cpu_fallback_and_cuda_detection` |
| 24 | Deteksi CUDA | idem (simulasi nvidia-smi + OpenCV CUDA) |
| 25 | Pengelompokan beberapa lokasi | `test_batch.py::test_location_grouping_not_mixed` |
| 26 | Penamaan sesuai format | `test_templates_naming.py::test_filename_format` |
| 27 | Nama duplikat | `test_templates_naming.py::test_duplicate_suffix`, `test_export_final_and_individual` |
| 28 | Metadata waktu tidak tersedia | `test_templates_naming.py::test_event_time_resolution`, `test_no_time_metadata_requires_operator_input` |
| 29 | Metadata lokasi & lalin diubah operator | `test_timeline_export.py::test_final_duration_and_metadata`, `test_location_grouping_not_mixed` |
| 30 | Karakter nama file tidak valid | `test_templates_naming.py::test_invalid_characters_removed`, `test_custom_filename_validation` |

Tambahan: file sumber tidak berubah (`test_source_files_untouched`), koreksi operator tersimpan sebagai dataset
(`test_candidate_correction_saved_as_feedback`), preview video final (`test_preview_render`), streaming HTTP Range.

## Pengujian manual dengan rekaman drone asli (checklist)

1. Buat proyek Terminal → batch 30 dtk, pergi & kembali, concurrency 2.
2. Tambah 1 video panjang satu penerbangan → Mulai Batch. Pastikan status berpindah Menunggu → Sedang dianalisis →
   Analisis selesai → Sedang diproses → Menunggu review, dan progres/ETA bergerak.
3. Review: cek garis merah putar balik pada grafik; bila meleset, koreksi arah kandidat. Verifikasi kandidat yang benar.
4. Tambah 25 file sekaligus pada batch baru → muncul peringatan, tombol unggah nonaktif.
5. Tambah 6 video ke batch → klik Jeda saat 2 berjalan → keduanya selesai, sisanya tetap Menunggu → Lanjutkan.
6. Tutup jendela start.bat saat analisis berjalan → jalankan lagi → batch berstatus Dijeda (dipulihkan) → Lanjutkan.
7. Masukkan satu file rusak (mis. rename .txt → .mp4) → hanya file itu Gagal.
8. Buat 2 kelompok lokasi, tetapkan video ke masing-masing → Buat Video Final → dua video final terpisah.
9. Timeline: seret blok, ubah alokasi satu segmen menjadi 2 dtk → muncul "kurang x dtk" + rekomendasi; tambahkan.
10. Ekspor final dua kali → file kedua berakhiran `_01`. Ekspor potongan individual → folder `_segmen`.
11. Ganti Pengaturan → Mode ekspor "Selalu re-encode" dan matikan NVENC → ekspor tetap berhasil (CPU).
12. Putus internet → jalankan start.bat → aplikasi tetap berjalan dan memproses video.

## Tambahan Drone Video Platform (v2)

| Skenario | Tes |
|---|---|
| 24 video masuk → 24 video hasil (1 hasil per video, 10–60 dtk) | `test_platform_integration.py::test_each_source_video_gets_its_own_output[*]` |
| Pengisian durasi dari video sumber yang sama, tanpa tumpang tindih | `test_platform_integration.py::test_fill_from_source_spreads_without_overlap` |
| Ekspor satu file per video sumber | `test_platform_integration.py::test_export_one_output_per_video` |
| Informasi video otomatis dari manifest Downloader / nama file | `test_platform_integration.py::test_manifest_and_filename_guess`, `::test_local_path_reads_info_automatically` |
| Impor dari riwayat Downloader (maks. 24, tanpa duplikat) | `test_platform_integration.py::test_import_from_downloader_history` |
| Migrasi database AI Drone Trimmer v1 | `test_platform_integration.py::test_migrates_v1_database` |
| Modul downloader (parser, penamaan, antrean, yt-dlp tiruan) | `tests/downloader/` |
