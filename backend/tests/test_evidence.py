from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.evidence import router as evidence_router
from app.auth.dependencies import get_current_subject
from app.core.database import get_db
from app.core.models import Base
from app.evidence import entities as _evidence_entities  # noqa: F401
from app.evidence.storage import EvidenceStorage
from app.investigations.entities import Investigation, InvestigationMember


@pytest.mark.asyncio
async def test_storage_streams_hash_and_refuses_path_escape(tmp_path: Path) -> None:
    storage = EvidenceStorage(tmp_path / "vault")
    content = b"synthetic forensic fixture\x00"
    async def reader(size: int) -> bytes:
        nonlocal content
        chunk, content = content[:size], content[size:]
        return chunk

    stored = await storage.store(reader, 7, 1024)
    path = storage.path_for(stored.storage_key)
    assert stored.sha256 == hashlib.sha256(b"synthetic forensic fixture\x00").hexdigest()
    assert stored.size_bytes == len(b"synthetic forensic fixture\x00")
    assert path.read_bytes() == b"synthetic forensic fixture\x00"
    assert storage.verify(stored.storage_key, stored.sha256)
    assert path.stat().st_mode & 0o222 == 0
    with pytest.raises(ValueError):
        storage.path_for("../outside")


@pytest.mark.asyncio
async def test_upload_and_hash_api_are_investigation_scoped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.evidence as evidence_api

    monkeypatch.setattr(evidence_api, "storage", EvidenceStorage(tmp_path / "evidence"))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        from app.auth.entities import User
        user = User(id=1, email="investigator@example.test", password_hash="not-used")
        session.add(user)
        await session.flush()
        investigation = Investigation(id=1, title="Synthetic case", owner_id=1)
        session.add(investigation)
        await session.flush()
        session.add(InvestigationMember(investigation_id=1, user_id=1))
        await session.commit()

    async def override_db():
        async with sessions() as session:
            yield session

    app = FastAPI()
    app.include_router(evidence_router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_subject] = lambda: "1"
    with TestClient(app) as client:
        response = client.post(
            "/api/investigations/1/evidence",
            files={"file": ("../../fixture.txt", b"safe synthetic content", "text/plain")},
        )
        assert response.status_code == 201, response.text
        evidence = response.json()
        assert evidence["original_filename"] == "fixture.txt"
        assert evidence["sha256"] == hashlib.sha256(b"safe synthetic content").hexdigest()
        digest_response = client.get(f"/api/investigations/1/evidence/{evidence['id']}/hash")
        assert digest_response.status_code == 200
        assert digest_response.json() == {
            "evidence_id": evidence["id"],
            "sha256": hashlib.sha256(b"safe synthetic content").hexdigest(),
            "verified": True,
        }
        metadata = client.get(f"/api/investigations/1/evidence/{evidence['id']}/metadata")
        assert metadata.status_code == 200
        assert metadata.json()["records"][0]["values"]["sha256"] == evidence["sha256"]
    await engine.dispose()
