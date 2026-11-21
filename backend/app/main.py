from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)


@app.on_event("startup")
async def startup() -> None:
    # SQLite-only local bootstrapping is useful for offline mode. Production
    # schema changes are handled exclusively through Alembic.
    if settings.database_url.startswith("sqlite"):
        from app.core.database import engine
        from app.core.models import Base

        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
