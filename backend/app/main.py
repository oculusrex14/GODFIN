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
from app.core.local_api_trust import LocalApiPolicy, LocalApiTrustMiddleware
from app.core.request_limits import (
    MAX_REQUEST_BODY_BYTES,
    RequestBodyLimitMiddleware,
)
from app.seed import run_seeds

logger = logging.getLogger(__name__)

DB_PATH = str(settings.database_path)

LOCAL_API_POLICY = LocalApiPolicy.from_environment()


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

    # GODFIN intentionally uses create_all plus the ordered startup registry for
    # its single local SQLite lifecycle. Seeds never mutate schema.
    Base.metadata.create_all(bind=engine)

    # A fresh database (or a legacy database missing a newly introduced table)
    # has nothing for the pre-create migration pass to update. Re-run the
    # restart-safe registry after every declared table exists so indexes,
    # precision columns, and write guards are installed before seeds or API
    # traffic can write to them. The only backup remains the pre-create backup
    # above; this second pass never changes that recovery point.
    apply_additive_schema_updates(DB_PATH)

    # Run database seeds
    db = SessionLocal()
    try:
        run_seeds(db)
        from app.core.startup_migrations import (
            record_schema_revision,
            run_post_create_migrations,
            validate_schema_postconditions,
        )

        run_post_create_migrations(db)
        record_schema_revision(db)
        validate_schema_postconditions(DB_PATH)

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
    scheduler_recovery = None
    try:
        from app.core.scheduler import (
            schedule_scheduler_recovery,
            start_scheduler,
        )

        scheduler_recovery = schedule_scheduler_recovery
        if not start_scheduler(DB_PATH, backup_dir):
            logger.warning("Backup scheduler is degraded and will retry")
    except Exception as exc:
        logger.error("Backup scheduler startup failed (%s)", type(exc).__name__)
        if scheduler_recovery is not None:
            try:
                scheduler_recovery(DB_PATH, backup_dir)
            except Exception as recovery_exc:
                logger.error(
                    "Backup scheduler recovery could not be scheduled (%s)",
                    type(recovery_exc).__name__,
                )

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
    allow_origins=list(LOCAL_API_POLICY.cors_origins),
    allow_origin_regex=LOCAL_API_POLICY.cors_origin_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition", "Retry-After"],
    max_age=600,
)

# Added last so the trust boundary is the outermost HTTP middleware and rejects
# unexpected hosts/origins before any route or CORS preflight is processed.
app.add_middleware(LocalApiTrustMiddleware, policy=LOCAL_API_POLICY)

app.include_router(
    api_v1_router,
    prefix=settings.API_V1_PREFIX,
    responses=STANDARD_ERROR_RESPONSES,
)
