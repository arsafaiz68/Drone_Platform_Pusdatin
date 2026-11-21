import logging
from logging.handlers import RotatingFileHandler

from .config import paths

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    paths.ensure()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    try:
        fh = RotatingFileHandler(paths.logs / "app.log", maxBytes=5_000_000, backupCount=3,
                                 encoding="utf-8")
        fh.setFormatter(fmt)
    except OSError:
        fh = None
    # "adt" = modul Trimmer, "app" = modul Downloader
    for name in ("adt", "app"):
        root = logging.getLogger(name)
        root.setLevel(level)
        root.addHandler(sh)
        if fh:
            root.addHandler(fh)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"adt.{name}")
