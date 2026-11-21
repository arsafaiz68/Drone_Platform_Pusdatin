"""Skema validasi input API (Pydantic v2)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

TripMode = Literal["outbound", "round_trip"]
Direction = Literal["outbound", "return"]
FinalDuration = Literal[10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]  # kelipatan 5 dtk


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    template_code: str
    description: Optional[str] = None
    location_name: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    template_code: Optional[str] = None
    description: Optional[str] = None
    location_name: Optional[str] = None


class BatchCreate(BaseModel):
    project_id: int
    name: Optional[str] = None
    final_duration: FinalDuration = 30
    trip_mode: TripMode = "round_trip"
    concurrency: Literal[1, 2, 4] = 2
    metadata_mode: Literal["shared", "per_final"] = "shared"
    template_code: Optional[str] = None
    route: Optional[dict] = None


class BatchUpdate(BaseModel):
    name: Optional[str] = None
    final_duration: Optional[FinalDuration] = None
    trip_mode: Optional[TripMode] = None
    concurrency: Optional[Literal[1, 2, 4]] = None
    metadata_mode: Optional[Literal["shared", "per_final"]] = None
    route: Optional[dict] = None


class LocalPaths(BaseModel):
    paths: list[str]


class OrderIds(BaseModel):
    ids: list[int]


class VideoUpdate(BaseModel):
    location_group_id: Optional[int] = None
    point_mapping: Optional[list[str]] = None
    direction_override: Optional[str] = None
    creation_time: Optional[str] = None
    # informasi video (otomatis dari Drone Video Downloader, dapat dikoreksi)
    location_name: Optional[str] = None
    traffic_condition: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    template_code: Optional[str] = None   # jenis lokasi per video (pelabuhan, terminal, stasiun, ...)


class ImportItem(BaseModel):
    path: str
    info: Optional[dict] = None


class ImportRequest(BaseModel):
    """Impor video hasil unduhan ke batch: dari riwayat downloader atau daftar path."""
    downloader_batch_id: Optional[str] = None
    job_ids: Optional[list[str]] = None
    items: Optional[list[ImportItem]] = None


class BatchFromDownload(BaseModel):
    project_id: int
    downloader_batch_id: Optional[str] = None
    job_ids: Optional[list[str]] = None
    items: Optional[list[ImportItem]] = None
    name: Optional[str] = None
    final_duration: FinalDuration = 30
    trip_mode: TripMode = "round_trip"
    concurrency: Literal[1, 2, 4] = 2
    start: bool = False


class GroupCreate(BaseModel):
    batch_id: int
    name: str = "Lokasi"
    location_name: Optional[str] = None
    traffic_condition: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    location_name: Optional[str] = None
    traffic_condition: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None


class CandidateCreate(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    point_code: str
    direction: Direction
    traffic: Optional[str] = None


class CandidateUpdate(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    point_code: Optional[str] = None
    direction: Optional[Direction] = None
    traffic_suggestion: Optional[str] = None
    verified: Optional[bool] = None
    is_turnaround: Optional[bool] = None
    quality_label: Optional[str] = None


class FinalCreate(BaseModel):
    project_id: int
    group_ids: list[int] = []
    source_video_id: Optional[int] = None
    target_duration: FinalDuration = 30
    trip_mode: TripMode = "round_trip"
    batch_id: Optional[int] = None
    cross_location: bool = False
    location_name: Optional[str] = None
    traffic_condition: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    auto_select: bool = True


class FinalUpdate(BaseModel):
    location_name: Optional[str] = None
    traffic_condition: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    custom_filename: Optional[str] = None
    target_duration: Optional[FinalDuration] = None
    trip_mode: Optional[TripMode] = None
    approved_duration_mismatch: Optional[bool] = None


class SegmentCreate(BaseModel):
    candidate_id: Optional[int] = None
    video_id: Optional[int] = None
    start: Optional[float] = None
    end: Optional[float] = None
    point_code: Optional[str] = None
    direction: Optional[Direction] = None
    position: Optional[int] = None
    role: Literal["point", "support"] = "point"


class SegmentUpdate(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    allocated: Optional[float] = Field(default=None, gt=0)
    point_code: Optional[str] = None
    direction: Optional[Direction] = None
    role: Optional[Literal["point", "support"]] = None


class SegmentReplace(BaseModel):
    candidate_id: int
    keep_duration: bool = True


class Allocations(BaseModel):
    allocations: dict[str, float]

    @field_validator("allocations")
    @classmethod
    def positive(cls, v):
        for k, s in v.items():
            if s <= 0:
                raise ValueError(f"Alokasi segmen {k} harus > 0")
        return v


class ExportRequest(BaseModel):
    kind: Literal["final", "individual", "preview"] = "final"


class SettingsUpdate(BaseModel):
    values: dict


class ModelConfigCreate(BaseModel):
    kind: Literal["detector", "scene", "traffic"] = "detector"
    name: str
    path: str
    enabled: bool = True
    params: Optional[dict] = None
    validated: bool = False


class ModelConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    params: Optional[dict] = None
    validated: Optional[bool] = None


def dump(m: BaseModel) -> dict:
    """Hanya field yang benar-benar dikirim klien."""
    return m.model_dump(exclude_unset=True)
