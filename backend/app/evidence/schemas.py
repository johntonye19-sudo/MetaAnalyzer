from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EvidenceResponse(BaseModel):
    id: str
    investigation_id: int
    original_filename: str
    declared_content_type: str | None
    size_bytes: int
    sha256: str
    uploaded_by: int
    uploaded_at: datetime
    extraction_status: str

    model_config = ConfigDict(from_attributes=True)


class EvidenceMetadataResponse(BaseModel):
    evidence_id: str
    records: list[dict[str, Any]]


class EvidenceHashResponse(BaseModel):
    evidence_id: str
    sha256: str
    verified: bool


class EvidenceListResponse(BaseModel):
    items: list[EvidenceResponse]
    total: int
    limit: int
    offset: int
