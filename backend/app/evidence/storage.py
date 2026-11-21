"""Evidence storage helpers: streamed hashing and no-clobber immutable writes."""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Awaitable, Callable


class UploadTooLarge(Exception):
    pass


class EvidenceIntegrityError(Exception):
    pass


@dataclass(frozen=True)
class StoredEvidence:
    evidence_id: str
    storage_key: str
    sha256: str
    size_bytes: int


class EvidenceStorage:
    """Stores evidence under generated keys, never using a client path as a path."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass

    async def store(self, reader: Callable[[int], Awaitable[bytes]], investigation_id: int,
                    max_bytes: int) -> StoredEvidence:
        evidence_id = str(uuid.uuid4())
        temporary_path: Path | None = None
        digest = hashlib.sha256()
        size = 0
        try:
            fd, raw_path = tempfile.mkstemp(prefix=".incoming-", dir=self.root)
            temporary_path = Path(raw_path)
            with os.fdopen(fd, "wb") as target:
                while True:
                    chunk = await reader(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise UploadTooLarge(f"Upload exceeds the configured {max_bytes}-byte limit")
                    digest.update(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            target_path = self.root / str(investigation_id) / f"{evidence_id}.bin"
            target_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                target_path.parent.chmod(0o700)
            except OSError:
                pass
            # A hard link is atomic and refuses to replace an existing destination.
            os.chmod(temporary_path, 0o400)
            os.link(temporary_path, target_path)
            key = PurePosixPath(str(investigation_id), f"{evidence_id}.bin").as_posix()
            return StoredEvidence(evidence_id, key, digest.hexdigest(), size)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def path_for(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if candidate == self.root or self.root not in candidate.parents:
            raise ValueError("Invalid evidence storage key")
        return candidate

    def verify(self, storage_key: str, expected_sha256: str) -> bool:
        path = self.path_for(storage_key)
        digest = hashlib.sha256()
        try:
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise EvidenceIntegrityError("Evidence file is unavailable") from exc
        return digest.hexdigest() == expected_sha256

    def remove(self, storage_key: str) -> None:
        path = self.path_for(storage_key)
        path.unlink(missing_ok=True)
