"""Authenticated evidence intake and integrity endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
import mimetypes
import re

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_subject
from app.core.config import get_settings
from app.core.database import get_db
from app.evidence.entities import ChainOfCustodyEvent, Evidence, MetadataRecord
from app.evidence.schemas import (
    EvidenceHashResponse,
    EvidenceListResponse,
    EvidenceMetadataResponse,
    EvidenceResponse,
)
from app.evidence.storage import EvidenceIntegrityError, EvidenceStorage, UploadTooLarge
from app.investigations.entities import Investigation
from app.api.investigations import authorized_investigation

router = APIRouter(prefix="/api/investigations/{investigation_id}/evidence", tags=["evidence"])
settings = get_settings()
storage = EvidenceStorage(settings.storage_root)


def clean_filename(filename: str | None) -> str:
    # Normalize both POSIX and Windows separators; the result is display-only.
    normalized = (filename or "upload.bin").replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1].strip()
    if not name or len(name) > 255 or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise HTTPException(status_code=400, detail="Invalid evidence filename")
    return name


@router.post("", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    investigation_id: int,
    file: UploadFile = File(...),
    subject: str = Depends(get_current_subject),
    investigation: Investigation = Depends(authorized_investigation),
    db: AsyncSession = Depends(get_db),
) -> Evidence:
    filename = clean_filename(file.filename)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    try:
        stored = await storage.store(file.read, investigation.id, max_bytes)
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    finally:
        await file.close()

    content_type = file.content_type
    if content_type and len(content_type) > 255:
        storage.remove(stored.storage_key)
        raise HTTPException(status_code=400, detail="Invalid content type")
    evidence = Evidence(
        id=stored.evidence_id,
        investigation_id=investigation.id,
        original_filename=filename,
        declared_content_type=content_type or mimetypes.guess_type(filename)[0],
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        storage_key=stored.storage_key,
        uploaded_by=int(subject),
        uploaded_at=datetime.now(timezone.utc),
        extraction_status="pending",
    )
    db.add(evidence)
    db.add(MetadataRecord(
        evidence_id=evidence.id,
        category="intake",
        source="MetaAnalyzer evidence intake",
        tool_version="0.1.0",
        values={
            "original_filename": filename,
            "declared_content_type": evidence.declared_content_type,
            "size_bytes": stored.size_bytes,
            "sha256": stored.sha256,
            "note": "Client-provided content type and filename are unverified; content was not executed.",
        },
    ))
    db.add(ChainOfCustodyEvent(
        evidence_id=evidence.id,
        actor_id=int(subject),
        action="uploaded",
        details={"sha256": stored.sha256, "size_bytes": stored.size_bytes},
    ))
    try:
        await db.commit()
        await db.refresh(evidence)
    except Exception:
        await db.rollback()
        storage.remove(stored.storage_key)
        raise
    return evidence


@router.get("", response_model=EvidenceListResponse)
async def list_evidence(
    investigation_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    investigation: Investigation = Depends(authorized_investigation),
    db: AsyncSession = Depends(get_db),
) -> EvidenceListResponse:
    base = select(Evidence).where(Evidence.investigation_id == investigation.id)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = (await db.scalars(base.order_by(Evidence.uploaded_at.desc()).limit(limit).offset(offset))).all()
    return EvidenceListResponse(items=list(items), total=total, limit=limit, offset=offset)


async def authorized_evidence(
    evidence_id: str,
    investigation: Investigation,
    db: AsyncSession,
) -> Evidence:
    evidence = await db.scalar(select(Evidence).where(
        Evidence.id == evidence_id, Evidence.investigation_id == investigation.id
    ))
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return evidence


@router.get("/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(
    evidence_id: str,
    investigation: Investigation = Depends(authorized_investigation),
    db: AsyncSession = Depends(get_db),
) -> Evidence:
    return await authorized_evidence(evidence_id, investigation, db)


@router.get("/{evidence_id}/metadata", response_model=EvidenceMetadataResponse)
async def get_metadata(
    evidence_id: str,
    investigation: Investigation = Depends(authorized_investigation),
    db: AsyncSession = Depends(get_db),
) -> EvidenceMetadataResponse:
    evidence = await authorized_evidence(evidence_id, investigation, db)
    records = (await db.scalars(select(MetadataRecord).where(
        MetadataRecord.evidence_id == evidence.id
    ).order_by(MetadataRecord.recorded_at))).all()
    return EvidenceMetadataResponse(evidence_id=evidence.id, records=[{
        "category": item.category,
        "source": item.source,
        "tool_version": item.tool_version,
        "values": item.values,
        "recorded_at": item.recorded_at,
    } for item in records])


@router.get("/{evidence_id}/hash", response_model=EvidenceHashResponse)
async def get_evidence_hash(
    evidence_id: str,
    investigation: Investigation = Depends(authorized_investigation),
    db: AsyncSession = Depends(get_db),
) -> EvidenceHashResponse:
    evidence = await authorized_evidence(evidence_id, investigation, db)
    verified = storage.verify(evidence.storage_key, evidence.sha256)
    return EvidenceHashResponse(evidence_id=evidence.id, sha256=evidence.sha256, verified=verified)


@router.get("/{evidence_id}/download")
async def download_evidence(
    evidence_id: str,
    investigation: Investigation = Depends(authorized_investigation),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    evidence = await authorized_evidence(evidence_id, investigation, db)
    try:
        verified = storage.verify(evidence.storage_key, evidence.sha256)
        path = storage.path_for(evidence.storage_key)
    except (EvidenceIntegrityError, ValueError):
        raise HTTPException(status_code=409, detail="Evidence integrity verification failed")
    if not verified:
        raise HTTPException(status_code=409, detail="Evidence integrity verification failed")
    return FileResponse(path, filename=evidence.original_filename, media_type="application/octet-stream")
