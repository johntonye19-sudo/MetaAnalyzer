# MetaAnalyzer development progress

## Evidence management milestone

- Investigation-scoped uploads, persistent evidence and metadata records, SHA-256 integrity verification, immutable local evidence storage, and intake custody logging are implemented.
- Metadata extraction is available on demand via `POST /api/investigations/{investigation_id}/evidence/{evidence_id}/extract`.
- The extraction engine classifies known file signatures, extracts available metadata for images, PDF and Office documents, audio/video (MediaInfo), email, text/JSON/XML/HTML, ZIP archives, and offline PCAP/PCAPNG when dependencies are available.
- Extraction records include tool/source, status, limitations/warnings, and filesystem timestamp context. Original evidence is verified before extraction and never modified.
- Archives are inspected without extracting their contents; HTML is parsed inertly without network fetches; email IP data is not geolocated; the offline network parser does not capture traffic.

Optional parser/tool availability is reported as warnings. Extraction currently runs in a worker thread within the API process, with parser limits/timeouts where applicable; it is not yet isolated in a dedicated sandbox or Celery worker. Treat uploaded files as untrusted and deploy behind suitable resource limits until sandboxed processing is implemented.

## Run and test

```bash
cd backend
python -m pip install -r requirements.txt
pytest -q
```

Apply production migrations from `backend/` with `alembic upgrade head`. Local SQLite startup uses SQLAlchemy metadata creation.
