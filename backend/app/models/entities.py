"""Daftar entitas/tabel dan konstanta status.

Aplikasi memakai ``sqlite3`` standar (tanpa ORM) agar ringan dan sepenuhnya lokal.
Skema lengkap ada di ``app/database/schema.sql``.
"""

TABLES = {
    "projects": "Projects",
    "templates": "Templates",
    "template_points": "Template Points",
    "source_videos": "Source Videos",
    "batch_jobs": "Batch Jobs",
    "batch_items": "Batch Items",
    "location_groups": "Location Groups",
    "analysis_jobs": "Analysis Jobs",
    "candidate_segments": "Candidate Segments",
    "final_videos": "Final Video Projects",
    "final_video_segments": "Final Video Segments",
    "segment_edits": "Segment Edits",
    "export_jobs": "Export Jobs",
    "model_configurations": "Model Configurations",
    "operator_feedback": "Operator Feedback",
}

ITEM_ACTIVE = ("analyzing", "processing")
ITEM_TERMINAL = ("review", "done", "failed", "cancelled")
BATCH_ACTIVE = ("queued", "running")

DIRECTIONS = {"outbound": "Pergi", "return": "Kembali"}
