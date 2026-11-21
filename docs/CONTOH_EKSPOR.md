# Contoh Hasil Ekspor

Format wajib: `Clipped_DD.MM_HH.MM_NamaLokasi_KondisiLalin.mp4`

| Masukan operator | Nama file |
|---|---|
| 18 Nov 07:30, "Terminal Pulogebang", Padat | `Clipped_18.11_07.30_TerminalPulogebang_Padat.mp4` |
| 18 Nov 08:15, "GT Cikampek", Lancar | `Clipped_18.11_08.15_GTCikampek_Lancar.mp4` |
| 18 Nov 09:45, "Stasiun Bandung", Ramai | `Clipped_18.11_09.45_StasiunBandung_Ramai.mp4` |
| 18 Nov 10:20, "Tol Cipularang", Padat Merayap | `Clipped_18.11_10.20_TolCipularang_PadatMerayap.mp4` |
| 18 Nov 11:00, "Rest Area KM 57", Padat | `Clipped_18.11_11.00_RestAreaKM57_Padat.mp4` |
| gabungan lintas lokasi "Pantauan Transportasi Nasional", Ramai | `Clipped_18.11_07.30_PantauanTransportasiNasional_Ramai.mp4` |
| nama sama diekspor ulang | `..._Padat_01.mp4`, `..._Padat_02.mp4` |
| kondisi belum ditetapkan | `..._TidakTeridentifikasi.mp4` |
| `Term:inal <Pulo>/Gebang` | `..._TermInalPuloGebang_...` (karakter tidak valid dihapus) |

Aturan waktu: input operator → metadata `creation_time` video yang valid (dikonversi dari UTC ke zona lokal,
default WIB, ditambah offset segmen pertama) → bila tidak ada, ekspor ditolak sampai operator mengisi tanggal & waktu.
Waktu ekspor tidak pernah dipakai. Durasi tidak dimasukkan ke nama file.

Potongan individual: `<nama final>_segmen\Clipped_18.11_07.30_TerminalPulogebang_Padat_Seg01_T1Pergi.mp4`, … + `segmen.json`.

## File contoh di folder ini

`contoh_ekspor/Clipped_18.11_07.30_TerminalPulogebang_Padat.mp4` — video final 30,0 detik hasil ekspor
aplikasi dari **video uji sintetis** (bukan rekaman drone asli; diperkecil ke 360p agar ringan), dan
`contoh_ekspor/Clipped_18.11_07.30_TerminalPulogebang_Padat.json` — metadata sidecar yang dibuat otomatis
(tanggal, waktu, lokasi, jenis lokasi, kondisi lalin, template, durasi, jumlah video sumber & segmen,
mode ekspor dan daftar segmen beserta timestamp sumber).
