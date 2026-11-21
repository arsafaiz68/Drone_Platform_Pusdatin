"""Deteksi perangkat: GPU NVIDIA / CUDA dengan fallback CPU otomatis."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
import time

from ..core.config import CONCURRENCY_OPTIONS
from ..core.logging_setup import get_logger

log = get_logger("hardware")
_cache: dict | None = None
_cache_ts = 0.0
_lock = threading.Lock()


def _run(cmd: list[str], timeout: float = 5.0) -> str | None:
    try:
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
        if out.returncode == 0:
            return out.stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def _nvidia_smi() -> list[dict]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    out = _run([exe, "--query-gpu=name,memory.total,memory.used,utilization.gpu,driver_version",
                "--format=csv,noheader,nounits"])
    gpus = []
    for line in (out or "").strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 5:
            def num(x):
                try:
                    return float(x)
                except ValueError:
                    return None
            gpus.append({"name": parts[0], "memory_total_mb": num(parts[1]),
                         "memory_used_mb": num(parts[2]), "utilization_pct": num(parts[3]),
                         "driver": parts[4]})
    return gpus


def _opencv_cuda() -> int:
    try:
        import cv2
        return int(cv2.cuda.getCudaEnabledDeviceCount())
    except Exception:  # noqa: BLE001 - modul cuda bisa tidak ada
        return 0


def _onnx_cuda() -> bool:
    try:
        import onnxruntime as ort  # opsional
        return "CUDAExecutionProvider" in ort.get_available_providers()
    except Exception:  # noqa: BLE001
        return False


def _torch_cuda() -> tuple[bool, str | None]:
    try:
        import torch  # opsional
        if torch.cuda.is_available():
            return True, torch.cuda.get_device_name(0)
    except Exception:  # noqa: BLE001
        pass
    return False, None


def _ffmpeg_encoders() -> set[str]:
    exe = shutil.which("ffmpeg")
    if not exe:
        return set()
    out = _run([exe, "-hide_banner", "-encoders"], timeout=10) or ""
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6:
            names.add(parts[1])
    return names


def _ram() -> tuple[float | None, float | None]:
    try:
        import psutil
        vm = psutil.virtual_memory()
        return vm.total / 2**30, vm.available / 2**30
    except Exception:  # noqa: BLE001
        return None, None


def recommended_concurrency(info: dict) -> tuple[int, int]:
    """(rekomendasi, maksimum yang diizinkan) berdasarkan RAM, CPU, dan GPU."""
    ram = info.get("ram_total_gb") or 8
    cores = info.get("cpu_cores") or 2
    max_allowed = 4
    if ram < 8 or cores < 4:
        max_allowed = 2
    if ram < 6 or cores < 2:
        max_allowed = 1
    gpu_mem = None
    if info.get("gpus"):
        gpu_mem = info["gpus"][0].get("memory_total_mb")
    if info["mode"] == "cuda" and gpu_mem and gpu_mem < 4000:
        max_allowed = min(max_allowed, 2)
    rec = min(2, max_allowed)
    return rec, max_allowed


def detect(force: bool = False) -> dict:
    global _cache, _cache_ts
    with _lock:
        if _cache and not force and time.time() - _cache_ts < 30:
            return dict(_cache)
        gpus = _nvidia_smi()
        cv_cuda = _opencv_cuda()
        ort_cuda = _onnx_cuda()
        torch_cuda, torch_name = _torch_cuda()
        encoders = _ffmpeg_encoders()
        cuda_available = bool(gpus) and (cv_cuda > 0 or ort_cuda or torch_cuda)
        nvenc = bool(gpus) and "h264_nvenc" in encoders
        ram_total, ram_avail = _ram()
        cpu_name = platform.processor() or platform.machine()
        info = {
            "mode": "cuda" if cuda_available else "cpu",
            "device_name": (gpus[0]["name"] if cuda_available and gpus else (torch_name or cpu_name or "CPU")),
            "cuda_available": cuda_available,
            "cuda_status": ("CUDA aktif" if cuda_available else
                            ("GPU NVIDIA terdeteksi, tetapi runtime CUDA (OpenCV/ONNX/PyTorch) tidak tersedia"
                             if gpus else "GPU NVIDIA tidak terdeteksi — memakai CPU")),
            "gpus": gpus,
            "opencv_cuda_devices": cv_cuda,
            "onnxruntime_cuda": ort_cuda,
            "torch_cuda": torch_cuda,
            "nvenc_available": nvenc,
            "ffmpeg_available": bool(shutil.which("ffmpeg")),
            "ffprobe_available": bool(shutil.which("ffprobe")),
            "cpu_name": cpu_name,
            "cpu_cores": os.cpu_count(),
            "ram_total_gb": round(ram_total, 1) if ram_total else None,
            "ram_available_gb": round(ram_avail, 1) if ram_avail else None,
            "platform": f"{platform.system()} {platform.release()}",
        }
        rec, max_allowed = recommended_concurrency(info)
        info["recommended_concurrency"] = rec
        info["max_concurrency"] = max_allowed
        info["concurrency_options"] = [c for c in CONCURRENCY_OPTIONS]
        _cache, _cache_ts = info, time.time()
        log.info("Perangkat: mode=%s, perangkat=%s", info["mode"], info["device_name"])
        return dict(info)


def clamp_concurrency(requested: int) -> tuple[int, str | None]:
    info = detect()
    if requested not in CONCURRENCY_OPTIONS:
        raise ValueError("Concurrency harus 1, 2, atau 4.")
    if requested > info["max_concurrency"]:
        return info["max_concurrency"], (
            f"Concurrency {requested} melebihi kemampuan perangkat; dibatasi menjadi {info['max_concurrency']}.")
    return requested, None


def usage() -> dict:
    out = {"cpu_percent": None, "ram_percent": None, "gpu": []}
    try:
        import psutil
        out["cpu_percent"] = psutil.cpu_percent(interval=None)
        out["ram_percent"] = psutil.virtual_memory().percent
    except Exception:  # noqa: BLE001
        pass
    out["gpu"] = _nvidia_smi()
    return out
