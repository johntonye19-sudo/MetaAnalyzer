# MetaAnalyzer development progress

## Current milestone: evidence-management foundation

Implemented in this milestone:

- Investigation-scoped evidence upload and listing APIs.
- Generated storage identifiers; client filenames are display metadata only.
- Streamed SHA-256 calculation with a configured hard upload-size limit.
- Atomic no-clobber local storage, restrictive directory/file permissions, and hash verification before download.
- Persistent evidence, intake metadata, and chain-of-custody records.
- Alembic migration `0003` and SQLite model bootstrapping.
- API tests for upload, filename path sanitization, metadata intake, and hash verification.

Evidence content is not executed. The stored MIME type is client-declared or filename-guessed and is explicitly not a content validation result. Extraction is pending; this milestone does not claim metadata extraction support.

## Run and test

```bash
cd backend
python -m pip install -r requirements.txt
pytest -q
```

Apply production migrations from `backend/` with `alembic upgrade head`. Local SQLite startup uses SQLAlchemy metadata creation.
