"""Analisis video drone secara lokal.

PENTING — batas kemampuan (ditampilkan juga di UI):
* Tanpa GPS, identifikasi titik pemantauan (1, 2, 3, ...) adalah ESTIMASI TEMPORAL:
  lintasan dibagi menurut urutan template dan dirapikan ke batas perubahan adegan.
  Ini bukan pengenalan lokasi oleh model terlatih, sehingga setiap kandidat
  ditandai "perlu verifikasi operator".
* Deteksi putar balik memakai dua sinyal visual yang benar-benar dihitung:
  (1) kemiripan cermin (frame sebelum dan sesudah putar balik saling mirip karena
  drone melewati area yang sama) dan (2) pembalikan arah gerak kamera (phase
  correlation antarframe).
* Deteksi objek (kendaraan/orang) hanya aktif bila model ONNX (mis. YOLOv8) ada di
  ``data/models``. Tanpa model, skor aktivitas memakai heuristik gerak residual dan
  kepadatan tepi, dan rekomendasi kondisi lalu lintas TIDAK dibuat.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from ..core.config import paths
from ..core.logging_setup import get_logger
from ..core.templates_config import point_map

log = get_logger("ai")

COCO_RELEVANT = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
VEHICLE_IDS = {1, 2, 3, 5, 7}


# ====================================================================== detektor
class Detector:
    name = "none"
    available = False
    validated = False

    def detect(self, frame_bgr) -> list[tuple[int, float]]:
        return []


class YoloOnnxDetector(Detector):
    """Detektor YOLOv8/YOLO11 format ONNX via OpenCV DNN (CUDA bila tersedia)."""

    def __init__(self, model_path: str, use_cuda: bool, conf: float = 0.3, input_size: int = 640):
        import cv2
        self.cv2 = cv2
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.device = "cpu"
        if use_cuda:
            try:
                self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                self.device = "cuda"
            except Exception:  # noqa: BLE001
                self.device = "cpu"
        self.conf = conf
        self.size = input_size
        self.name = f"YOLO-ONNX ({Path(model_path).name})"
        self.available = True

    def detect(self, frame_bgr):
        cv2 = self.cv2
        blob = cv2.dnn.blobFromImage(frame_bgr, 1 / 255.0, (self.size, self.size), swapRB=True)
        self.net.setInput(blob)
        out = self.net.forward()
        out = np.squeeze(out)
        if out.ndim != 2:
            return []
        if out.shape[0] < out.shape[1]:
            out = out.T  # (N, 4+C)
        scores = out[:, 4:]
        cls = scores.argmax(axis=1)
        conf = scores[np.arange(len(cls)), cls]
        keep = conf >= self.conf
        boxes = out[keep, :4]
        cls, conf = cls[keep], conf[keep]
        if len(cls) == 0:
            return []
        b = [[float(x - w / 2), float(y - h / 2), float(w), float(h)] for x, y, w, h in boxes]
        idx = cv2.dnn.NMSBoxes(b, conf.astype(float).tolist(), self.conf, 0.45)
        idx = np.array(idx).flatten() if len(idx) else []
        return [(int(cls[i]), float(conf[i])) for i in idx if int(cls[i]) in COCO_RELEVANT]


def load_detector(model_cfg: dict | None, use_cuda: bool) -> Detector:
    """Muat detektor dari konfigurasi model; kembali ke Detector() kosong bila gagal."""
    candidates = []
    if model_cfg and model_cfg.get("path"):
        candidates.append(model_cfg["path"])
    candidates += [str(p) for p in sorted(paths.models.glob("*.onnx"))]
    for p in candidates:
        if Path(p).is_file():
            try:
                params = (model_cfg or {}).get("params") or {}
                det = YoloOnnxDetector(p, use_cuda, conf=float(params.get("conf", 0.3)),
                                       input_size=int(params.get("input_size", 640)))
                det.validated = bool(model_cfg and model_cfg.get("validated"))
                return det
            except Exception as e:  # noqa: BLE001
                log.warning("Gagal memuat model %s: %s", p, e)
    return Detector()


# ====================================================================== fitur frame
@dataclass
class Samples:
    t: list = field(default_factory=list)
    sharp: list = field(default_factory=list)
    bright: list = field(default_factory=list)
    contrast: list = field(default_factory=list)
    edge: list = field(default_factory=list)
    dx: list = field(default_factory=list)
    dy: list = field(default_factory=list)
    resp: list = field(default_factory=list)
    resid: list = field(default_factory=list)
    hist: list = field(default_factory=list)
    obj_t: list = field(default_factory=list)
    obj_vehicle: list = field(default_factory=list)
    obj_person: list = field(default_factory=list)


def extract_features(frames, detector: Detector, detector_every: float,
                     progress: Callable[[float], None] | None, duration: float,
                     should_stop: Callable[[], bool] | None) -> Samples:
    import cv2
    s = Samples()
    prev_gray = None
    win = None
    last_det = -1e9
    for t, frame in frames:
        if should_stop and should_stop():
            raise InterruptedError("Analisis dihentikan")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        g = gray.astype(np.float32)
        if win is None:
            win = cv2.createHanningWindow(gray.shape[::-1], cv2.CV_32F)
        s.t.append(float(t))
        s.sharp.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
        s.bright.append(float(g.mean() / 255.0))
        s.contrast.append(float(g.std() / 128.0))
        s.edge.append(float((cv2.Canny(gray, 80, 160) > 0).mean()))
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256]).flatten()
        h = h / (h.sum() + 1e-9)
        s.hist.append(h.astype(np.float32))
        if prev_gray is not None:
            (dx, dy), resp = cv2.phaseCorrelate(prev_gray, g, win)
            s.dx.append(float(dx))
            s.dy.append(float(dy))
            s.resp.append(float(resp))
            m = np.float32([[1, 0, dx], [0, 1, dy]])
            warped = cv2.warpAffine(prev_gray, m, gray.shape[::-1])
            diff = np.abs(warped - g)
            bh, bw = int(abs(dy)) + 2, int(abs(dx)) + 2
            core = diff[bh:-bh or None, bw:-bw or None] if diff.shape[0] > 2 * bh and diff.shape[1] > 2 * bw else diff
            s.resid.append(float((core > 25).mean()))
        else:
            s.dx.append(0.0)
            s.dy.append(0.0)
            s.resp.append(1.0)
            s.resid.append(0.0)
        prev_gray = g
        if detector.available and t - last_det >= detector_every:
            last_det = t
            dets = detector.detect(frame)
            s.obj_t.append(float(t))
            s.obj_vehicle.append(sum(1 for c, _ in dets if c in VEHICLE_IDS))
            s.obj_person.append(sum(1 for c, _ in dets if c == 0))
        if progress and duration:
            progress(min(1.0, t / duration))
    return s


# ====================================================================== utilitas
def _smooth(x: np.ndarray, k: int) -> np.ndarray:
    if len(x) == 0 or k <= 1:
        return x
    k = min(k, len(x))
    kernel = np.ones(k) / k
    pad = k // 2
    xp = np.pad(x, (pad, k - 1 - pad), mode="edge")
    return np.convolve(xp, kernel, mode="valid")


def _rank(x: np.ndarray) -> np.ndarray:
    """Normalisasi peringkat persentil 0..1 (tahan terhadap outlier)."""
    if len(x) == 0:
        return x
    order = x.argsort().argsort().astype(float)
    return order / max(1, len(x) - 1)


def _robust01(x: np.ndarray) -> np.ndarray:
    if len(x) == 0:
        return x
    lo, hi = np.percentile(x, 5), np.percentile(x, 95)
    if hi - lo < 1e-9:
        return np.full_like(x, 0.5, dtype=float)
    return np.clip((x - lo) / (hi - lo), 0, 1)


def hist_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Kemiripan histogram (1 - jarak Bhattacharyya)."""
    bc = float(np.sum(np.sqrt(np.clip(a, 0, None) * np.clip(b, 0, None))))
    return max(0.0, min(1.0, bc))


# ====================================================================== putar balik
def detect_turnaround(s: Samples, sample_fps: float) -> dict:
    """Cari waktu putar balik utama memakai kemiripan cermin + pembalikan gerak."""
    n = len(s.t)
    result = {"found": False, "time": None, "index": None, "confidence": 0.0,
              "mirror_score": None, "motion_reversal": False, "method": "mirror+motion"}
    if n < max(12, int(8 * sample_fps)):
        result["note"] = "Video terlalu pendek untuk deteksi putar balik."
        return result
    H = np.stack(s.hist)
    H = np.sqrt(H)  # sim = dot product (Bhattacharyya coefficient)
    lo, hi = int(n * 0.2), int(n * 0.9)
    scores = np.full(n, np.nan)
    for c in range(lo, hi):
        K = min(c, n - 1 - c)
        if K < 4:
            continue
        ks = np.arange(max(2, K // 4), K + 1, max(1, K // 40))
        mirror = np.einsum("ij,ij->i", H[c - ks], H[c + ks]).mean()
        # pembanding: pasangan berjarak sama tetapi searah waktu (tidak cermin)
        back = np.clip(c - 2 * ks, 0, n - 1)
        baseline = 0.5 * (np.einsum("ij,ij->i", H[back], H[c - ks]).mean() +
                          np.einsum("ij,ij->i", H[c + ks], H[np.clip(c + 2 * ks, 0, n - 1)]).mean())
        scores[c] = mirror - baseline * 0.5
    valid = ~np.isnan(scores)
    if not valid.any():
        return result
    sm = scores.copy()
    sm[valid] = _smooth(scores[valid], max(3, int(sample_fps * 3)))
    c = int(np.nanargmax(sm))
    best = float(sm[c])
    med = float(np.nanmedian(sm))
    spread = float(np.nanstd(sm)) + 1e-6
    z = (best - med) / spread

    # pembalikan arah gerak kamera
    v = np.stack([np.array(s.dx), np.array(s.dy)], axis=1)
    vs = np.stack([_smooth(v[:, 0], int(sample_fps * 4) or 1), _smooth(v[:, 1], int(sample_fps * 4) or 1)], 1)
    before = vs[max(0, c - int(15 * sample_fps)):c].mean(axis=0) if c > 2 else np.zeros(2)
    after = vs[c:min(n, c + int(15 * sample_fps))].mean(axis=0)
    nb, na = np.linalg.norm(before), np.linalg.norm(after)
    reversal = bool(nb > 0.3 and na > 0.3 and float(np.dot(before, after)) / (nb * na) < -0.3)

    conf = 1 / (1 + math.exp(-(z - 2.0)))  # z-score 2 -> 0.5
    if reversal:
        conf = min(1.0, conf + 0.25)
    result.update({"found": conf >= 0.35, "time": float(s.t[c]), "index": c,
                   "confidence": round(float(conf), 3), "mirror_score": round(best, 4),
                   "zscore": round(float(z), 2), "motion_reversal": reversal})
    return result


def motion_reversals(s: Samples, sample_fps: float, i0: int, i1: int) -> list[float]:
    """Waktu-waktu pembalikan arah gerak kamera dalam rentang indeks (untuk putar balik sekunder)."""
    if i1 - i0 < int(6 * sample_fps):
        return []
    v = np.stack([np.array(s.dx[i0:i1]), np.array(s.dy[i0:i1])], 1)
    k = max(3, int(sample_fps * 3))
    vs = np.stack([_smooth(v[:, 0], k), _smooth(v[:, 1], k)], 1)
    dom = vs[: max(2, len(vs) // 3)].mean(axis=0)
    if np.linalg.norm(dom) < 0.3:
        return []
    proj = vs @ (dom / np.linalg.norm(dom))
    out = []
    for i in range(1, len(proj)):
        if proj[i - 1] > 0.2 and proj[i] <= -0.2:
            out.append(float(s.t[i0 + i]))
    return out


# ====================================================================== zona titik
def scene_change_curve(s: Samples) -> np.ndarray:
    H = np.sqrt(np.stack(s.hist))
    sim = np.einsum("ij,ij->i", H[1:], H[:-1])
    d = np.concatenate([[0.0], 1 - sim])
    return _smooth(d, 3)


def split_leg(t0: float, t1: float, leg: list[str], pmap: dict, s: Samples,
              change: np.ndarray, times: np.ndarray) -> list[dict]:
    """Bagi rentang waktu satu arah perjalanan menjadi zona titik berurutan."""
    weights = np.array([pmap[c].get("zone_weight", 1.0) for c in leg], float)
    span = t1 - t0
    cum = np.concatenate([[0], np.cumsum(weights) / weights.sum()])
    nominal = [t0 + span * c for c in cum]
    bounds = list(nominal)
    for i in range(1, len(bounds) - 1):
        # batas boleh bergeser ke perubahan adegan terdekat, tetapi tiap zona
        # minimal mempertahankan 80% panjang nominalnya
        tol = min(span * 0.12, 0.2 * (nominal[i] - nominal[i - 1]), 0.2 * (nominal[i + 1] - nominal[i]))
        lo, hi = nominal[i] - tol, nominal[i] + tol
        mask = (times >= max(lo, bounds[i - 1] + 1)) & (times <= hi)
        if mask.any():
            idx = np.where(mask)[0]
            j = idx[int(np.argmax(change[idx]))]
            if change[j] > np.percentile(change, 75):
                bounds[i] = float(times[j])
    zones = []
    for i, code in enumerate(leg):
        zones.append({"point_code": code, "start": round(float(bounds[i]), 3),
                      "end": round(float(bounds[i + 1]), 3)})
    return zones


# ====================================================================== analisis utama
@dataclass
class AnalysisInput:
    video_id: int
    path: str
    duration: float
    template: dict
    route: dict
    trip_mode: str
    point_mapping: list[str] | None = None
    direction_override: str | None = None
    settings: dict = field(default_factory=dict)


def analyze_video(inp: AnalysisInput, detector: Detector,
                  progress: Callable[[float, str], None] | None = None,
                  should_stop: Callable[[], bool] | None = None) -> dict:
    from .video_service import iter_frames

    st = inp.settings
    sample_fps = float(st.get("analysis_sample_fps", 2.0))
    width = int(st.get("analysis_width", 320))
    t_start = time.time()
    pmap = point_map(inp.template)

    def prog(frac, stage):
        if progress:
            progress(frac, stage)

    frames = iter_frames(inp.path, sample_fps, width, should_stop)
    s = extract_features(frames, detector, 1.0 / float(st.get("detector_sample_fps", 1.0)),
                         (lambda f: prog(0.05 + 0.8 * f, "Ekstraksi fitur frame")), inp.duration,
                         should_stop)
    if len(s.t) < 2:
        raise RuntimeError("Frame video tidak dapat dibaca (file rusak atau codec tidak didukung).")
    prog(0.86, "Analisis urutan perjalanan")
    times = np.array(s.t)
    duration = max(inp.duration, float(times[-1]))
    warnings: list[str] = []

    # --------------------------------------------------- skor per sampel
    sharp = _rank(np.log1p(np.array(s.sharp)))
    sharp_abs = np.array(s.sharp)
    speed = np.hypot(np.array(s.dx), np.array(s.dy))
    jitter = np.abs(np.diff(speed, prepend=speed[0]))
    resp = np.array(s.resp)
    stability = 1 - _robust01(jitter + 2 * _robust01(speed) * 0.5) * 0.7 - (1 - np.clip(resp * 3, 0, 1)) * 0.3
    stability = np.clip(stability, 0, 1)
    bright = np.array(s.bright)
    exposure = np.clip(1 - np.abs(bright - 0.5) * 2, 0, 1) * np.clip(np.array(s.contrast) * 2, 0, 1)
    quality = np.clip(0.45 * sharp + 0.35 * stability + 0.20 * exposure, 0, 1)
    blurry = (sharp < 0.1) | (sharp_abs < 15)

    if detector.available and s.obj_t:
        veh = np.interp(times, s.obj_t, s.obj_vehicle)
        per = np.interp(times, s.obj_t, s.obj_person)
        obj = veh + 0.5 * per
        activity = _robust01(obj)
        object_density = obj
        activity_method = "deteksi objek"
    else:
        activity = np.clip(0.6 * _robust01(np.array(s.resid)) + 0.4 * _robust01(np.array(s.edge)), 0, 1)
        object_density = None
        activity_method = "heuristik gerak residual + kepadatan tepi (tanpa model)"

    # --------------------------------------------------- arah & zona
    mapping = inp.point_mapping
    turn = {"found": False}
    legs: list[tuple[str, float, float, list[str]]] = []
    manual = bool(mapping)
    if manual:
        direction = inp.direction_override or "outbound"
        legs.append((direction, 0.0, duration, [str(m) for m in mapping]))
    else:
        turn = detect_turnaround(s, sample_fps)
        if inp.trip_mode == "round_trip":
            if turn.get("time") is None:
                warnings.append("Putar balik tidak terdeteksi; video dibagi dua secara temporal. Perlu verifikasi.")
                tt = duration / 2
            else:
                tt = turn["time"]
                if not turn["found"]:
                    warnings.append("Keyakinan deteksi putar balik rendah; periksa batas pergi/kembali.")
            legs.append(("outbound", 0.0, tt, inp.route["outbound"]))
            legs.append(("return", tt, duration, inp.route["return"]))
        else:
            end = duration
            if turn.get("found") and turn["time"] < duration * 0.95:
                end = turn["time"]
                warnings.append(f"Terdeteksi kemungkinan putar balik pada {end:.1f} dtk; "
                                "bagian setelahnya diabaikan (mode pergi saja).")
            legs.append(("outbound", 0.0, end, inp.route["outbound"]))

    change = scene_change_curve(s)
    zones = []
    for direction, a, b, leg in legs:
        for z in split_leg(a, b, leg, pmap, s, change, times):
            z["direction"] = direction
            zones.append(z)

    # putar balik sekunder (mis. Gerbang Tol titik 4)
    events = []
    if turn.get("time") is not None and inp.trip_mode == "round_trip" and not manual:
        events.append({"type": "turnaround", "time": turn["time"], "point_code": inp.route["outbound"][-1],
                       "confidence": turn["confidence"], "main": True})
    for code in inp.route.get("turnarounds", [])[:-1]:
        for z in zones:
            if z["point_code"] == code and z["direction"] == "outbound":
                i0 = int(np.searchsorted(times, z["start"]))
                i1 = int(np.searchsorted(times, z["end"]))
                for tr in motion_reversals(s, sample_fps, i0, i1):
                    events.append({"type": "turnaround", "time": tr, "point_code": code,
                                   "confidence": 0.4, "main": False})

    # --------------------------------------------------- kandidat
    prog(0.92, "Membuat kandidat segmen")
    min_len = float(st.get("min_segment_seconds", 3.0))
    max_len = float(st.get("max_segment_seconds", 20.0))
    if manual:
        base_conf = 1.0
    elif inp.trip_mode == "round_trip":
        base_conf = 0.35 * (0.6 + 0.4 * float(turn.get("confidence") or 0.5))
    else:
        base_conf = 0.4
    candidates = []
    H = np.sqrt(np.stack(s.hist))
    for z in zones:
        if z["point_code"] == "H" and not st.get("include_home_point", False):
            continue
        i0 = int(np.searchsorted(times, z["start"]))
        i1 = int(np.searchsorted(times, z["end"]))
        if i1 - i0 < 2:
            continue
        zlen = z["end"] - z["start"]
        pos = (times[i0:i1] - z["start"]) / max(zlen, 1e-6)
        centrality = 1 - np.abs(pos - 0.5) * 1.2
        rel = np.clip(0.65 * activity[i0:i1] + 0.35 * np.clip(centrality, 0, 1), 0, 1)
        q = quality[i0:i1]
        score = 0.5 * q + 0.5 * rel
        win = max(2, int(round(min(min_len * 1.5, zlen) * sample_fps)))
        if i1 - i0 < win:
            win = i1 - i0
        cums = np.concatenate([[0], np.cumsum(score)])
        wscore = (cums[win:] - cums[:-win]) / win
        used = np.zeros(i1 - i0, bool)
        picked = []
        for _ in range(4):
            ws = wscore.copy()
            for j in range(len(ws)):
                if used[j:j + win].any():
                    ws[j] = -1
            if len(ws) == 0 or ws.max() < 0:
                break
            j = int(ws.argmax())
            a, b = j, j + win
            mean = ws[j]
            # perluas selama skor tetap baik
            while b < len(score) and (b - a) / sample_fps < max_len and score[b] >= 0.8 * mean and not used[b]:
                b += 1
            while a > 0 and (b - a) / sample_fps < max_len and score[a - 1] >= 0.8 * mean and not used[a - 1]:
                a -= 1
            gap = int(sample_fps)
            used[max(0, a - gap):min(len(used), b + gap)] = True
            picked.append((a, b))
        zone_cands = []
        for a, b in picked:
            ga, gb = i0 + a, i0 + b
            t_a = float(times[ga])
            t_b = float(times[gb - 1]) + 1.0 / sample_fps
            t_b = min(t_b, z["end"], duration)
            if t_b - t_a < 1.0:
                continue
            qm = float(quality[ga:gb].mean())
            rm = float(rel[a:b].mean())
            mh = H[ga:gb].mean(axis=0)
            mh = mh / (np.linalg.norm(mh) + 1e-9)
            if any(float(np.dot(mh, c["_hist"])) > 0.985 for c in zone_cands):
                continue  # adegan hampir identik dengan kandidat lain
            blur_frac = float(blurry[ga:gb].mean())
            reasons = [f"kualitas visual {qm:.2f}", f"stabilitas {float(stability[ga:gb].mean()):.2f}",
                       f"aktivitas {float(activity[ga:gb].mean()):.2f} ({activity_method})"]
            if blur_frac > 0.5:
                reasons.append("PERINGATAN: sebagian besar frame buram")
            reasons.append("titik diestimasi dari urutan temporal template" if not manual
                           else "titik dari pemetaan manual operator")
            od = float(object_density[ga:gb].mean()) if object_density is not None else None
            traffic = suggest_traffic(od) if od is not None else None
            imp = pmap[z["point_code"]].get("importance", 1.0)
            rec = float(np.clip((t_b - t_a), min_len, min(max_len, 4 + 4 * imp)))
            zone_cands.append({
                "point_code": z["point_code"], "direction": z["direction"],
                "start": round(t_a, 3), "end": round(t_b, 3),
                "quality_score": round(qm, 4), "relevance_score": round(rm, 4),
                "stability_score": round(float(stability[ga:gb].mean()), 4),
                "sharpness_score": round(float(sharp[ga:gb].mean()), 4),
                "activity_score": round(float(activity[ga:gb].mean()), 4),
                "object_density": round(od, 3) if od is not None else None,
                "confidence": round(float(base_conf), 3),
                "recommended_duration": round(min(rec, t_b - t_a), 2),
                "reason": "; ".join(reasons),
                "traffic_suggestion": traffic,
                "needs_verification": not manual,
                "is_turnaround": any(e["point_code"] == z["point_code"] and t_a <= e["time"] <= t_b
                                     for e in events),
                "features": {"blur_fraction": round(blur_frac, 3), "mean_brightness": round(float(bright[ga:gb].mean()), 3),
                             "hist": [round(float(x), 5) for x in mh]},
                "_hist": mh,
            })
        candidates.extend(zone_cands)
    for c in candidates:
        c.pop("_hist", None)

    covered = {(c["point_code"], c["direction"]) for c in candidates}
    missing = [f"{z['point_code']} ({'pergi' if z['direction'] == 'outbound' else 'kembali'})"
               for z in zones if (z["point_code"], z["direction"]) not in covered
               and (z["point_code"] != "H" or st.get("include_home_point"))]
    if missing:
        warnings.append("Titik tanpa footage layak: " + ", ".join(missing))

    # kurva skor (ringkas, untuk grafik UI)
    stepc = max(1, len(times) // 600)
    curve = {"t": [round(float(x), 2) for x in times[::stepc]],
             "quality": [round(float(x), 3) for x in quality[::stepc]],
             "activity": [round(float(x), 3) for x in activity[::stepc]]}
    prog(1.0, "Selesai")
    return {
        "video_id": inp.video_id,
        "duration": duration,
        "samples": len(times),
        "sample_fps": sample_fps,
        "elapsed_sec": round(time.time() - t_start, 2),
        "detector": detector.name,
        "detector_available": detector.available,
        "is_heuristic": not detector.available,
        "point_identification": "manual" if manual else "estimasi temporal (belum ada model titik terlatih)",
        "activity_method": activity_method,
        "turnaround": turn,
        "events": events,
        "zones": zones,
        "candidates": candidates,
        "warnings": warnings,
        "blurry_fraction": round(float(blurry.mean()), 3),
        "curve": curve,
    }


def suggest_traffic(vehicles_per_frame: float | None) -> str | None:
    """Saran kondisi lalu lintas dari rata-rata jumlah kendaraan per frame.

    Ambang ini BELUM tervalidasi dan hanya ditampilkan sebagai saran; operator
    tetap menentukan kondisi akhir. Tanpa detektor, fungsi tidak dipanggil.
    """
    if vehicles_per_frame is None:
        return None
    v = vehicles_per_frame
    if v < 5:
        return "Lancar"
    if v < 12:
        return "Ramai Lancar"
    if v < 20:
        return "Ramai"
    if v < 30:
        return "Padat"
    if v < 45:
        return "Padat Merayap"
    return "Macet"
