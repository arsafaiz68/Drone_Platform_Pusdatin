"""Akses SQLite yang aman untuk multi-thread (satu koneksi per thread, mode WAL)."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from ..core.config import DEFAULT_SETTINGS, paths
from ..core.templates_config import all_templates

SCHEMA_VERSION = 2

# Kolom yang ditambahkan setelah versi 1 (database lama dimigrasi otomatis).
_ADDED_COLUMNS = {
    "source_videos": [("location_name", "TEXT"), ("traffic_condition", "TEXT"), ("event_date", "TEXT"),
                      ("event_time", "TEXT"), ("source_origin", "TEXT"), ("source_meta_json", "TEXT"),
                      ("template_code", "TEXT")],
    "final_videos": [("source_video_id", "INTEGER REFERENCES source_videos(id) ON DELETE CASCADE")],
}
_local = threading.local()
_write_lock = threading.RLock()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    paths.database_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(paths.database), timeout=30, check_same_thread=False,
                           isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    db_path = getattr(_local, "db_path", None)
    if conn is None or db_path != str(paths.database):
        conn = _connect()
        _local.conn = conn
        _local.db_path = str(paths.database)
    return conn


def close_thread_conn() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in list(d.keys()):
        if k.endswith("_json"):
            raw = d.pop(k)
            key = k[:-5]
            try:
                d[key] = json.loads(raw) if raw else None
            except (TypeError, ValueError):
                d[key] = None
    return d


def _encode(values: dict) -> dict:
    out = {}
    for k, v in values.items():
        if k.endswith("_json") and not isinstance(v, (str, type(None))):
            v = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, bool):
            v = int(v)
        elif isinstance(v, Path):
            v = str(v)
        out[k] = v
    return out


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    cur = get_conn().execute(sql, tuple(params))
    return [row_to_dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    cur = get_conn().execute(sql, tuple(params))
    return row_to_dict(cur.fetchone())


def scalar(sql: str, params: Iterable[Any] = ()):
    row = get_conn().execute(sql, tuple(params)).fetchone()
    return row[0] if row else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with _write_lock:
        cur = get_conn().execute(sql, tuple(params))
        return cur.lastrowid


def insert(table: str, values: dict) -> int:
    values = _encode(values)
    cols = ", ".join(values.keys())
    ph = ", ".join("?" for _ in values)
    return execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})", values.values())


def update(table: str, row_id: int, values: dict) -> None:
    if not values:
        return
    values = _encode(values)
    sets = ", ".join(f"{k} = ?" for k in values)
    execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*values.values(), row_id])


def get(table: str, row_id: int) -> dict | None:
    return query_one(f"SELECT * FROM {table} WHERE id = ?", (row_id,))


class transaction:
    """Context manager transaksi eksplisit (BEGIN IMMEDIATE)."""

    def __enter__(self):
        _write_lock.acquire()
        self.conn = get_conn()
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.conn.execute("COMMIT")
            else:
                self.conn.execute("ROLLBACK")
        finally:
            _write_lock.release()
        return False


# ----------------------------------------------------------------- init
def init_db() -> None:
    paths.ensure()
    conn = get_conn()
    schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    with _write_lock:
        conn.executescript(schema)
        _migrate(conn)
        if scalar("SELECT COUNT(*) FROM schema_version") == 0:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
        else:
            conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
    sync_templates()
    ensure_default_settings()


def _migrate(conn: sqlite3.Connection) -> None:
    """Tambahkan kolom baru ke database lama (AI Drone Trimmer v1) tanpa menghapus data."""
    for table, cols in _ADDED_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, decl in cols:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_final_source ON final_videos(source_video_id)")


def sync_templates() -> None:
    """Sinkronkan konfigurasi template terpusat ke tabel templates/template_points."""
    ts = now_iso()
    with transaction() as conn:
        for t in all_templates():
            conn.execute(
                """INSERT INTO templates(code, name, location_type, description, route_outbound_json,
                       route_return_json, turnarounds_json, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(code) DO UPDATE SET name=excluded.name,
                       location_type=excluded.location_type, description=excluded.description,
                       route_outbound_json=excluded.route_outbound_json,
                       route_return_json=excluded.route_return_json,
                       turnarounds_json=excluded.turnarounds_json, updated_at=excluded.updated_at""",
                (t["code"], t["name"], t["location_type"], t["description"],
                 json.dumps(t["route_outbound"]), json.dumps(t["route_return"]),
                 json.dumps(t["turnarounds"]), ts))
            for p in t["points"]:
                conn.execute(
                    """INSERT INTO template_points(template_code, code, number, name, description,
                           importance, zone_weight) VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(template_code, code) DO UPDATE SET number=excluded.number,
                           name=excluded.name, description=excluded.description,
                           importance=excluded.importance, zone_weight=excluded.zone_weight""",
                    (t["code"], p["code"], p["number"], p["name"], p["description"],
                     p["importance"], p["zone_weight"]))


def ensure_default_settings() -> None:
    existing = {r["key"] for r in query("SELECT key FROM settings")}
    legacy = bool(existing) and "quality_profile_version" not in existing
    for k, v in DEFAULT_SETTINGS.items():
        if k not in existing:
            execute("INSERT INTO settings(key, value_json) VALUES (?, ?)", (k, json.dumps(v)))
    if legacy:
        _upgrade_export_quality()


def _upgrade_export_quality() -> None:
    """Database lama memakai profil ekspor cepat (CRF 20, preset medium, maks 1080p, NVENC).
    Naikkan ke profil kualitas tinggi sekali saja; nilai yang sudah lebih baik dibiarkan."""
    st = get_settings()
    upd = {}
    if int(st.get("export_crf", 16)) > 18:
        upd["export_crf"] = 16
    if st.get("export_preset") not in ("slow", "slower", "veryslow"):
        upd["export_preset"] = "slow"
    if int(st.get("export_max_height") or 0) in (720, 1080):
        upd["export_max_height"] = 0
    if st.get("use_gpu_encoder"):
        upd["use_gpu_encoder"] = False
    for k, v in upd.items():
        execute("UPDATE settings SET value_json=? WHERE key=?", (json.dumps(v), k))


def get_settings() -> dict:
    out = dict(DEFAULT_SETTINGS)
    for r in get_conn().execute("SELECT key, value_json FROM settings").fetchall():
        try:
            out[r["key"]] = json.loads(r["value_json"])
        except ValueError:
            pass
    return out


def set_settings(values: dict) -> dict:
    for k, v in values.items():
        if k not in DEFAULT_SETTINGS:
            raise KeyError(k)
        execute("INSERT INTO settings(key, value_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                (k, json.dumps(v)))
    return get_settings()
