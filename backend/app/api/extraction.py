"""Authenticated on-demand extraction endpoint."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.investigations import authorized_investigation
from app.core.database import get_db
from app.evidence.entities import ChainOfCustodyEvent, Evidence, MetadataRecord
from app.evidence.extraction import ExtractionFailure, extract_metadata
from app.evidence.schemas import EvidenceMetadataResponse
from app.evidence.storage import EvidenceIntegrityError
from app.api.evidence import storage, authorized_evidence
from app.investigations.entities import Investigation

router = APIRouter(prefix="/api/investigations/{investigation_id}/evidence", tags=["analysis"])


@router.post("/{evidence_id}/extract", response_model=EvidenceMetadataResponse)
async def extract_evidence(
    evidence_id: str,
    investigation: Investigation = Depends(authorized_investigation),
    db: AsyncSession = Depends(get_db),
) -> EvidenceMetadataResponse:
    evidence = await authorized_evidence(evidence_id, investigation, db)
    try:
        if not storage.verify(evidence.storage_key, evidence.sha256):
            evidence.extraction_status = "failed"
            await db.commit()
            raise HTTPException(status_code=409, detail="Evidence integrity verification failed")
        path = storage.path_for(evidence.storage_key)
        result = await asyncio.to_thread(extract_metadata, path, evidence.original_filename)
    except (EvidenceIntegrityError, ValueError) as exc:
        evidence.extraction_status = "failed"
        await db.commit()
        raise HTTPException(status_code=409, detail="Evidence could not be verified or accessed") from exc
    except ExtractionFailure as exc:
        evidence.extraction_status = "failed"
        await db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        evidence.extraction_status = "failed"
        await db.commit()
        raise HTTPException(status_code=422, detail="Evidence file could not be read") from exc

    record = MetadataRecord(
        evidence_id=evidence.id,
        category=result["category"],
        source=result["source"],
        tool_version=result["tool_version"],
        values={"values": result["values"], "warnings": result["warnings"], "status": result["status"]},
        recorded_at=datetime.now(timezone.utc),
    )
    evidence.extraction_status = result["status"]
    db.add(record)
    db.add(ChainOfCustodyEvent(
        evidence_id=evidence.id,
        actor_id=evidence.uploaded_by,
        action="metadata_extracted",
        details={"status": result["status"], "recorded_at": datetime.now(timezone.utc).isoformat()},
    ))
    await db.commit()
    await db.refresh(record)
    return EvidenceMetadataResponse(evidence_id=evidence.id, records=[{
        "category": record.category,
        "source": record.source,
        "tool_version": record.tool_version,
        "values": record.values,
        "recorded_at": record.recorded_at,
    }])
