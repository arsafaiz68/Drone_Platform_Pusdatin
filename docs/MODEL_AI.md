# Menambahkan Model AI Lokal

## Yang berjalan tanpa model (aktif sekarang)

| Fitur | Teknik |
|---|---|
| Sampling frame | OpenCV `VideoCapture` (akselerasi HW bila tersedia), fallback pipe FFmpeg |
| Ketajaman / buram | varians Laplacian (peringkat persentil per video) |
| Eksposur & kontras | rata-rata dan simpangan intensitas |
| Kestabilan & arah gerak kamera | `cv2.phaseCorrelate` antarframe (dx, dy, respons) + jitter |
| Perubahan adegan & kemiripan | histogram HSV (jarak Bhattacharyya) |
| Aktivitas objek (heuristik) | gerak residual setelah kompensasi gerak kamera + kepadatan tepi Canny |
| Putar balik | kemiripan "cermin" frame sebelum/sesudah + pembalikan vektor gerak kamera |
| Estimasi titik | pembagian temporal sesuai urutan & bobot zona template, dirapikan ke batas perubahan adegan |

Hasil ini **kandidat awal**: keyakinan label titik sengaja rendah (±35%) dan setiap kandidat bertanda
"perlu verifikasi operator". Kondisi lalu lintas default **Tidak Teridentifikasi**.

## Detektor objek (kendaraan, bus, orang)

Aplikasi memuat model **YOLOv8 / YOLO11 format ONNX** melalui OpenCV DNN (target CUDA bila OpenCV dibangun
dengan CUDA, selain itu CPU). Kelas COCO yang dipakai: person, bicycle, car, motorcycle, bus, truck.

Langkah (dilakukan sekali di komputer yang terhubung internet, lalu salin filenya):

```bash
pip install ultralytics
yolo export model=yolov8n.pt format=onnx imgsz=640 opset=12
```

1. Salin `yolov8n.onnx` ke `data\models\`.
2. Buka **Model AI** → model otomatis terdeteksi; atau daftarkan path & ambang keyakinan di form, lalu aktifkan.
3. Analisis ulang video. Skor aktivitas kini dari jumlah objek; saran kondisi lalu lintas muncul dengan tanda `*`
   (belum tervalidasi). Operator tetap menetapkan kondisi akhir.

Model kustom (mis. dilatih khusus footage drone/top-down) dapat dipakai selama keluaran ONNX berformat
`(1, 4+C, N)` gaya YOLOv8 dengan indeks kelas COCO di atas; ubah `COCO_RELEVANT`/`VEHICLE_IDS` di
`backend/app/services/ai_service.py` bila indeks kelas berbeda.

Untuk mengaktifkan CUDA pada OpenCV DNN diperlukan build OpenCV dengan CUDA (paket pip standar `opencv-python`
hanya CPU). Encoding NVENC di FFmpeg tetap berfungsi tanpa itu. Status ditampilkan di Pengaturan → Perangkat.

## Antarmuka integrasi untuk model lain

* `ai_service.Detector` — kelas dasar `detect(frame_bgr) -> [(class_id, conf)]`. Buat subkelas (mis. ONNX Runtime,
  TensorRT, PyTorch) lalu kembalikan dari `load_detector()`.
* **Pengenalan titik/landmark** (belum ada model): titik saat ini ditetapkan di `split_leg()`. Model klasifikasi
  scene dapat menggantikan langkah ini dengan memberi label per sampel frame lalu menyusun zona dari label tsb.
* **Klasifikasi lalu lintas**: ganti `suggest_traffic()` dengan model terlatih dan tandai `validated=1`
  pada konfigurasi model setelah diuji.

## Dataset dari koreksi operator

Tabel `operator_feedback` merekam setiap verifikasi, koreksi timestamp/titik/arah, penolakan kandidat, pemilihan
kandidat ke video final, dan penetapan kondisi lalu lintas, lengkap dengan: template, titik, arah, timestamp awal
& akhir, label putar balik, fitur visual (kualitas, kecerahan, porsi buram), proyek & video sumber, label kualitas,
label lalu lintas. Ekspor melalui **Model AI → Ekspor dataset (JSONL)** ke `data\models\dataset\`.

Alur yang disarankan: kumpulkan ≥ beberapa ratus segmen terverifikasi per template → ekstrak frame dari
`video_path` + timestamp → latih klasifikator titik/scene dan klasifikator kepadatan → ekspor ONNX → validasi
pada data uji terpisah → daftarkan dengan centang "sudah divalidasi".
