from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_subject
from app.core.database import get_db
from app.investigations.entities import Investigation, InvestigationMember
from app.investigations.schemas import InvestigationCreate, InvestigationResponse

router = APIRouter(prefix="/api/investigations", tags=["investigations"])


async def authorized_investigation(
    investigation_id: int,
    subject: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_db),
) -> Investigation:
    result = await db.execute(
        select(Investigation)
        .join(InvestigationMember, InvestigationMember.investigation_id == Investigation.id)
        .where(Investigation.id == investigation_id, InvestigationMember.user_id == int(subject))
    )
    investigation = result.scalar_one_or_none()
    if investigation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")
    return investigation


@router.post("", response_model=InvestigationResponse, status_code=status.HTTP_201_CREATED)
async def create_investigation(
    payload: InvestigationCreate,
    subject: str = Depends(get_current_subject),
    db: AsyncSession = Depends(get_db),
) -> Investigation:
    investigation = Investigation(title=payload.title, description=payload.description, owner_id=int(subject))
    db.add(investigation)
    await db.flush()
    db.add(InvestigationMember(investigation_id=investigation.id, user_id=int(subject)))
    await db.commit()
    await db.refresh(investigation)
    return investigation


@router.get("/{investigation_id}", response_model=InvestigationResponse)
async def get_investigation(investigation: Investigation = Depends(authorized_investigation)) -> Investigation:
    return investigation
