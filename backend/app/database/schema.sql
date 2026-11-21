-- Drone Video Platform (modul Trimmer) - skema SQLite
-- File video TIDAK disimpan sebagai BLOB; hanya path lokal yang direferensikan.

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location_type TEXT NOT NULL,
    description TEXT,
    route_outbound_json TEXT NOT NULL,
    route_return_json TEXT NOT NULL,
    turnarounds_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS template_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_code TEXT NOT NULL REFERENCES templates(code) ON DELETE CASCADE,
    code TEXT NOT NULL,
    number INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    importance REAL NOT NULL DEFAULT 1.0,
    zone_weight REAL NOT NULL DEFAULT 1.0,
    UNIQUE(template_code, code)
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    template_code TEXT NOT NULL REFERENCES templates(code),
    location_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batch_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    template_code TEXT NOT NULL,
    final_duration INTEGER NOT NULL,
    trip_mode TEXT NOT NULL,
    concurrency INTEGER NOT NULL,
    metadata_mode TEXT NOT NULL DEFAULT 'shared',   -- shared | per_final
    route_json TEXT,                                -- konfigurasi lintasan operator
    status TEXT NOT NULL DEFAULT 'draft',
    recovered INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS location_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER REFERENCES batch_jobs(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    location_name TEXT,
    location_type TEXT,
    traffic_condition TEXT,
    event_date TEXT,       -- YYYY-MM-DD (input operator)
    event_time TEXT,       -- HH:MM (input operator)
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    batch_id INTEGER REFERENCES batch_jobs(id) ON DELETE CASCADE,
    location_group_id INTEGER REFERENCES location_groups(id) ON DELETE SET NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    is_uploaded INTEGER NOT NULL DEFAULT 1,   -- 1 = salinan di data/uploads, 0 = referensi path lokal
    size_bytes INTEGER,
    duration REAL,
    width INTEGER,
    height INTEGER,
    fps REAL,
    codec TEXT,
    audio_codec TEXT,
    creation_time TEXT,      -- ISO dari metadata (jika ada)
    metadata_json TEXT,
    proxy_path TEXT,
    order_index INTEGER NOT NULL DEFAULT 0,
    point_mapping_json TEXT, -- pemetaan manual: daftar titik yang dicakup video
    direction_override TEXT, -- outbound | return | null
    probe_error TEXT,
    uploaded_at TEXT NOT NULL,
    -- informasi video per file (otomatis dari Drone Video Downloader / nama file, dapat dikoreksi)
    location_name TEXT,
    traffic_condition TEXT,
    event_date TEXT,          -- YYYY-MM-DD
    event_time TEXT,          -- HH:MM
    source_origin TEXT,       -- upload | path | downloader
    template_code TEXT,       -- jenis lokasi per video (null = template batch)
    source_meta_json TEXT     -- hasil parsing laporan (lokasi, cuaca, lalin, url, ...)
);

CREATE TABLE IF NOT EXISTS batch_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES batch_jobs(id) ON DELETE CASCADE,
    video_id INTEGER NOT NULL REFERENCES source_videos(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'waiting',
    progress REAL NOT NULL DEFAULT 0,
    stage TEXT,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES source_videos(id) ON DELETE CASCADE,
    batch_item_id INTEGER REFERENCES batch_items(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    device TEXT,
    detector TEXT,
    is_heuristic INTEGER NOT NULL DEFAULT 1,
    result_json TEXT,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS candidate_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES source_videos(id) ON DELETE CASCADE,
    analysis_job_id INTEGER REFERENCES analysis_jobs(id) ON DELETE SET NULL,
    point_code TEXT NOT NULL,
    direction TEXT NOT NULL,            -- outbound | return
    t_start REAL NOT NULL,
    t_end REAL NOT NULL,
    ai_start REAL,
    ai_end REAL,
    ai_point_code TEXT,
    ai_direction TEXT,
    quality_score REAL,
    relevance_score REAL,
    stability_score REAL,
    sharpness_score REAL,
    activity_score REAL,
    object_density REAL,
    confidence REAL,
    recommended_duration REAL,
    reason TEXT,
    features_json TEXT,
    traffic_suggestion TEXT,
    origin TEXT NOT NULL DEFAULT 'ai',  -- ai | operator
    edited INTEGER NOT NULL DEFAULT 0,
    verified INTEGER NOT NULL DEFAULT 0,
    needs_verification INTEGER NOT NULL DEFAULT 1,
    is_turnaround INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS final_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    batch_id INTEGER REFERENCES batch_jobs(id) ON DELETE SET NULL,
    group_ids_json TEXT NOT NULL,
    cross_location INTEGER NOT NULL DEFAULT 0,
    template_code TEXT NOT NULL,
    target_duration INTEGER NOT NULL,
    trip_mode TEXT NOT NULL,
    location_name TEXT,
    location_type TEXT,
    traffic_condition TEXT,
    event_date TEXT,
    event_time TEXT,
    time_source TEXT,            -- metadata | operator | unknown
    custom_filename TEXT,
    status TEXT NOT NULL DEFAULT 'draft',   -- draft | ready | exporting | exported | failed
    approved_duration_mismatch INTEGER NOT NULL DEFAULT 0,
    warnings_json TEXT,
    selection_report_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_video_id INTEGER REFERENCES source_videos(id) ON DELETE CASCADE  -- 1 video sumber = 1 video hasil
);

CREATE TABLE IF NOT EXISTS final_video_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    final_video_id INTEGER NOT NULL REFERENCES final_videos(id) ON DELETE CASCADE,
    candidate_id INTEGER REFERENCES candidate_segments(id) ON DELETE SET NULL,
    video_id INTEGER NOT NULL REFERENCES source_videos(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    point_code TEXT,
    direction TEXT,
    role TEXT NOT NULL DEFAULT 'point',   -- point | support
    t_start REAL NOT NULL,
    t_end REAL NOT NULL,
    ai_start REAL,
    ai_end REAL,
    origin TEXT NOT NULL DEFAULT 'ai',
    edited INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segment_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    final_video_id INTEGER,
    final_segment_id INTEGER,
    candidate_id INTEGER,
    action TEXT NOT NULL,
    old_value_json TEXT,
    new_value_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS export_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    final_video_id INTEGER NOT NULL REFERENCES final_videos(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,            -- final | individual | preview
    status TEXT NOT NULL,          -- queued | running | done | failed
    progress REAL NOT NULL DEFAULT 0,
    mode TEXT,
    encoder TEXT,
    output_path TEXT,
    output_files_json TEXT,
    duration REAL,
    error TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS model_configurations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,          -- detector | scene | traffic
    name TEXT NOT NULL,
    path TEXT,
    enabled INTEGER NOT NULL DEFAULT 0,
    params_json TEXT,
    validated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operator_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    video_id INTEGER,
    candidate_id INTEGER,
    template_code TEXT,
    point_code TEXT,
    direction TEXT,
    t_start REAL,
    t_end REAL,
    is_turnaround INTEGER DEFAULT 0,
    quality_label TEXT,
    traffic_label TEXT,
    visual_features_json TEXT,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_videos_batch ON source_videos(batch_id);
CREATE INDEX IF NOT EXISTS ix_items_batch ON batch_items(batch_id);
CREATE INDEX IF NOT EXISTS ix_cand_video ON candidate_segments(video_id);
CREATE INDEX IF NOT EXISTS ix_fseg_final ON final_video_segments(final_video_id);
CREATE INDEX IF NOT EXISTS ix_export_final ON export_jobs(final_video_id);
