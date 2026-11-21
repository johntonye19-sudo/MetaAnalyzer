# MetaAnalyzer development plan

## Architecture decision

- FastAPI provides the HTTP and OpenAPI API boundary.
- SQLAlchemy 2.x is used with async PostgreSQL.
- PostgreSQL is the production database; SQLite is supported by later offline configuration.
- Celery and Redis provide asynchronous evidence processing.
- React/Vite/TypeScript provides the responsive investigation interface.
- Original evidence will be written to immutable storage and never overwritten.

## Phase 1 scope

Implemented incrementally:

- Repository structure
- Application configuration
- Health and readiness endpoints
- Database base and initial migration
- Authentication foundations
- Docker Compose topology
- Backend and frontend test harnesses

## Commands

```bash
cp .env.example .env
docker compose up --build
```
