export interface Entry {
  id: string;
  index: number;
  location: string | null;
  date: string | null; // YYYY-MM-DD
  time: string | null; // HH:MM
  timezone: string | null;
  weather: string | null;
  wave_height: string | null;
  wave_direction: string | null;
  traffic: string | null;
  traffic_engineering: string | null;
  notes: string[];
  url_original: string;
  url: string | null;
  video_id: string | null;
  url_valid: boolean;
  url_error: string | null;
  filename: string;
  filename_manual: boolean;
  warnings: string[];
  raw_block: string;
}

export interface ParseResponse {
  entries: Entry[];
  warnings: string[];
  report_date: string | null;
  report_hours: string | null;
  summary: {
    total_urls: number;
    valid_urls: number;
    invalid_urls: number;
    entries_with_warnings: number;
  };
}

export interface Health {
  status: string;
  version: string;
  ffmpeg: boolean;
  ffmpeg_path: string | null;
  yt_dlp_version: string | null;
  max_parallel: number;
  default_quality: number;
  default_output_dir: string;
  log_dir: string;
}

export interface LocalRoot {
  name: string;
  path: string;
  kind: "shortcut" | "home" | "drive";
  free_bytes?: number | null;
}

export interface LocalFolderChild {
  name: string;
  path: string;
}

export interface LocalFolder {
  path: string;
  name: string;
  parent: string | null;
  children: LocalFolderChild[];
  truncated: boolean;
  writable: boolean;
  free_bytes: number | null;
  video_count: number;
  error: string | null;
}

export type JobStatus =
  | "pending"
  | "downloading"
  | "processing"
  | "success"
  | "skipped"
  | "failed"
  | "cancelled";

export interface Job {
  id: string;
  batch_id: string;
  index: number;
  url: string;
  base_name: string;
  metadata: Partial<Entry>;
  status: JobStatus;
  download_progress: number;
  downloaded_bytes: number | null;
  total_bytes: number | null;
  speed: number | null;
  eta: number | null;
  file_size: number | null;
  ext: string | null;
  output_path: string | null;
  final_filename: string | null;
  note: string | null;
  error: string | null;
  attempts: number;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface BatchSummaryData {
  total: number;
  success: number;
  skipped: number;
  failed: number;
  cancelled: number;
  pending: number;
  in_progress: number;
  total_bytes: number;
  finished: boolean;
}

export type BatchStatus = "running" | "completed" | "partial" | "failed" | "cancelled";
export type ConflictBehavior = "rename" | "skip" | "replace";

export interface Batch {
  id: string;
  created_at: string;
  quality: number;
  parallel: number;
  output_dir: string;
  conflict_behavior: ConflictBehavior;
  report_date: string | null;
  note: string | null;
  cancel_requested: boolean;
  status: BatchStatus;
  summary: BatchSummaryData;
  jobs?: Job[];
}

export interface DownloadOptions {
  quality: 480 | 720 | 1080;
  parallel: 1 | 2 | 3;
  conflict_behavior: ConflictBehavior;
}

export type WsMessage =
  | { type: "snapshot"; batch: Batch }
  | { type: "job"; batch_id: string; job: Job; summary: BatchSummaryData; status: BatchStatus }
  | { type: "batch"; batch_id: string; summary: BatchSummaryData; status: BatchStatus }
  | { type: "pong" };
