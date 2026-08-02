import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from app.api.v1.router import router as api_v1_router
from app.core.api_errors import (
    STANDARD_ERROR_RESPONSES,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.logging_config import setup_logging
from app.core.request_limits import (
    MAX_REQUEST_BODY_BYTES,
    RequestBodyLimitMiddleware,
)
from app.seed import run_seeds

logger = logging.getLogger(__name__)

DB_PATH = str(settings.database_path)

# Allowed CORS origins (configure based on environment)
ALLOWED_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:5200,http://localhost:5100,"
    "http://127.0.0.1:5200,godfin://app"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("GODFIN_TESTING") == "1":
        yield
        return

    # Initialize structured logging
    setup_logging()
    logger.info("GODFIN starting up")

    # Resolve the stable key before any component attempts to read encrypted
    # Gmail or LLM credentials. A missing historical key is a startup error.
    from app.core.encryption import initialize_encryption
    initialize_encryption()

    backup_dir = os.environ.get("GODFIN_BACKUP_DIR", "./backups")
    from app.core.startup_migrations import (
        apply_additive_schema_updates,
        backup_before_schema_update,
    )

    migration_backup = backup_before_schema_update(DB_PATH, backup_dir)
    if migration_backup:
        logger.info("Created pre-migration backup: %s", migration_backup)
    apply_additive_schema_updates(DB_PATH)

    # GODFIN intentionally uses create_all + idempotent seed migrations for its
    # local SQLite lifecycle. This makes a first launch work with an empty path
    # and keeps packaged builds independent from a separate migration command.
    Base.metadata.create_all(bind=engine)

    # Run database seeds
    db = SessionLocal()
    try:
        run_seeds(db)
        from app.core.startup_migrations import (
            record_schema_revision,
            run_post_create_migrations,
        )

        run_post_create_migrations(db)
        record_schema_revision(db)

        # Load persistent auth token from database
        from app.core.auth import load_token_from_db
        load_token_from_db(db)
    finally:
        db.close()

    # Initialize LLM provider from database
    try:
        from app.core.llm_runtime import initialize_active_llm

        db = SessionLocal()
        try:
            initialize_active_llm(db)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to initialize LLM provider: {e}")

    # Start background scheduler
    try:
        from app.core.scheduler import start_scheduler
        start_scheduler(DB_PATH, backup_dir)
    except Exception as e:
        logger.warning(f"Scheduler not started: {e}")

    yield

    # Shutdown scheduler
    try:
        from app.core.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass

    logger.info("GODFIN shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-augmented personal finance tracker",
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.add_middleware(
    RequestBodyLimitMiddleware,
    max_bytes=MAX_REQUEST_BODY_BYTES,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    api_v1_router,
    prefix=settings.API_V1_PREFIX,
    responses=STANDARD_ERROR_RESPONSES,
)
