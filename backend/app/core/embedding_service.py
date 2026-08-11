from __future__ import annotations

import logging
import os
import struct
import threading
from pathlib import Path
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.background_jobs import (
    JobContext,
    JobExecutionError,
    enqueue_job,
    latest_job,
    request_job_cancel,
)
from app.models.merchant_memory import MerchantMemory

logger = logging.getLogger(__name__)

MODEL_NAME = 'all-MiniLM-L6-v2'
FASTEMBED_MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'
EMBEDDING_DIM = 384
SIMILARITY_THRESHOLD = 0.80
MAX_SETUP_MERCHANTS = 5_000
EMBEDDING_FORMAT_MAGIC = b"GDFEMB01"
EMBEDDING_HEADER = struct.Struct("<8sI")
EMBEDDING_DTYPE = np.dtype("<f4")

# Lazy-loaded model singleton
_model = None
_setup_lock = threading.Lock()
_setup_cancel = threading.Event()
_setup_status = {
    "status": "idle",
    "progress": 0,
    "message": "Embedding classification is disabled.",
    "updated": 0,
    "total": 0,
}


def _get_model():
    global _model
    if _model is None:
        try:
            from fastembed import TextEmbedding

            cache_dir = Path(
                os.environ.get(
                    "GODFIN_MODEL_CACHE_DIR",
                    Path(__file__).resolve().parents[2] / "data" / "models",
                )
            ).expanduser()
            cache_dir.mkdir(parents=True, exist_ok=True)
            _model = TextEmbedding(
                model_name=FASTEMBED_MODEL_NAME,
                cache_dir=str(cache_dir),
                threads=max(1, min(4, os.cpu_count() or 1)),
            )
            logger.info(f"Loaded embedding model: {MODEL_NAME}")
        except Exception as exc:
            logger.error(
                "Failed to load embedding model (%s)",
                type(exc).__name__,
            )
            return None
    return _model


def generate_embedding(text: str) -> Optional[np.ndarray]:
    model = _get_model()
    if model is None:
        return None
    try:
        embedding = next(model.embed([text]))
        return np.asarray(embedding, dtype=np.float32)
    except Exception as exc:
        logger.error(
            "Embedding generation failed (%s)",
            type(exc).__name__,
        )
        return None


def serialize_embedding(embedding: np.ndarray) -> bytes:
    """Serialize one validated embedding without executable object metadata."""
    vector = np.asarray(embedding, dtype=EMBEDDING_DTYPE)
    if vector.ndim != 1 or vector.shape[0] != EMBEDDING_DIM:
        raise ValueError(f"Embedding must contain exactly {EMBEDDING_DIM} values")
    if not np.isfinite(vector).all():
        raise ValueError("Embedding contains non-finite values")
    return EMBEDDING_HEADER.pack(EMBEDDING_FORMAT_MAGIC, EMBEDDING_DIM) + vector.tobytes(
        order="C"
    )


def deserialize_embedding(data: bytes) -> np.ndarray:
    """Read the fixed GODFIN float32 format; legacy pickle is never opened."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError("Embedding payload must be bytes")

    payload = bytes(data)
    expected_size = EMBEDDING_HEADER.size + (EMBEDDING_DIM * EMBEDDING_DTYPE.itemsize)
    if len(payload) != expected_size:
        raise ValueError("Unsupported or malformed embedding payload")

    magic, dimension = EMBEDDING_HEADER.unpack_from(payload)
    if magic != EMBEDDING_FORMAT_MAGIC or dimension != EMBEDDING_DIM:
        raise ValueError("Unsupported or legacy embedding format")

    vector = np.frombuffer(
        payload,
        dtype=EMBEDDING_DTYPE,
        count=dimension,
        offset=EMBEDDING_HEADER.size,
    ).copy()
    if vector.shape != (EMBEDDING_DIM,) or not np.isfinite(vector).all():
        raise ValueError("Embedding payload contains invalid values")
    return vector


def _embedding_needs_refresh(merchant: MerchantMemory) -> bool:
    """Discard legacy/corrupt vectors so an explicit setup can regenerate them."""
    if merchant.embedding_vector is None:
        return True
    try:
        deserialize_embedding(merchant.embedding_vector)
    except (TypeError, ValueError):
        merchant.embedding_vector = None
        merchant.embedding_model_version = None
        return True
    return merchant.embedding_model_version != MODEL_NAME


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    # Vectors are already normalized from sentence-transformers
    return float(np.dot(a, b))


def find_similar_merchant(
    db: Session,
    query_text: str,
    threshold: float = SIMILARITY_THRESHOLD,
) -> Optional[tuple[MerchantMemory, float]]:
    query_embedding = generate_embedding(query_text)
    if query_embedding is None:
        return None

    memories = db.query(MerchantMemory).filter(
        MerchantMemory.embedding_vector.isnot(None)
    ).all()

    if not memories:
        return None

    best_score = 0.0
    best_memory = None

    for memory in memories:
        try:
            stored_embedding = deserialize_embedding(memory.embedding_vector)
            score = cosine_similarity(query_embedding, stored_embedding)
            if score > best_score:
                best_score = score
                best_memory = memory
        except Exception:
            continue

    if best_memory and best_score >= threshold:
        return best_memory, best_score

    return None


def update_merchant_embedding(db: Session, merchant: MerchantMemory) -> bool:
    embedding = generate_embedding(merchant.normalized_name)
    if embedding is None:
        return False

    merchant.embedding_vector = serialize_embedding(embedding)
    merchant.embedding_model_version = MODEL_NAME
    return True


def backfill_embeddings(db: Session) -> int:
    memories = db.query(MerchantMemory).all()

    updated = 0
    for memory in memories:
        if _embedding_needs_refresh(memory) and update_merchant_embedding(db, memory):
            updated += 1

    if db.dirty:
        db.flush()

    return updated


def get_embedding_setup_status() -> dict:
    try:
        job = latest_job(kind="embedding_setup", active_key="embedding-setup")
    except Exception:
        job = None
    if job is not None:
        status_map = {
            "queued": "queued",
            "running": "downloading" if job["progress"] < 25 else "indexing",
            "retry_wait": "failed",
            "cancel_requested": "cancelling",
            "completed": "ready",
            "failed": "failed",
            "cancelled": "cancelled",
            "poisoned": "failed",
        }
        result = job.get("result") or {}
        return {
            "job_id": job["id"],
            "status": status_map[job["status"]],
            "progress": job["progress"],
            "message": job["message"],
            "updated": int(result.get("updated") or 0),
            "total": job["total"],
            "attempt": job["attempt"],
            "retry_at": job["retry_at"],
            "failure_code": job["failure_code"],
        }
    with _setup_lock:
        return dict(_setup_status)


def _set_setup_status(**updates) -> None:
    with _setup_lock:
        _setup_status.update(updates)


def cancel_embedding_setup() -> bool:
    """Request cancellation without exposing worker or filesystem details."""
    try:
        job = latest_job(kind="embedding_setup", active_key="embedding-setup")
    except Exception:
        job = None
    if job is not None and job["status"] in {
        "queued",
        "running",
        "retry_wait",
        "cancel_requested",
    }:
        return request_job_cancel(job["id"])
    with _setup_lock:
        if _setup_status["status"] not in {"queued", "downloading", "indexing"}:
            return False
        _setup_cancel.set()
        _setup_status.update(
            status="cancelling",
            message="Stopping matching setup safely…",
        )
        return True


def start_embedding_setup() -> bool:
    """Queue one durable, single-flight local embedding setup."""
    result = enqueue_job(
        "embedding_setup",
        active_key="embedding-setup",
        max_attempts=3,
        public_message="Preparing similar-description matching…",
    )
    return result.created


def run_embedding_setup_job(
    job_context: JobContext,
    _payload: dict,
) -> dict:
    """Download and generate vectors without holding a database transaction."""
    _setup_cancel.clear()
    _set_setup_status(
        status="downloading",
        progress=5,
        message="Downloading the local model (~100 MB)…",
        updated=0,
        total=0,
    )
    job_context.progress(
        5,
        message="Downloading the local matching model (~100 MB)…",
    )
    if _get_model() is None:
        raise JobExecutionError("EMBEDDING_MODEL_UNAVAILABLE", retryable=True)
    job_context.check_cancelled()

    read_db = SessionLocal()
    try:
        memories = [
            memory
            for memory in read_db.query(MerchantMemory)
            .order_by(MerchantMemory.id)
            .limit(MAX_SETUP_MERCHANTS)
            .all()
            if _embedding_needs_refresh(memory)
        ]
        snapshots = [(memory.id, memory.normalized_name) for memory in memories]
        read_db.rollback()
    finally:
        read_db.close()

    total = len(snapshots)
    _set_setup_status(
        status="indexing",
        progress=25,
        message="Indexing merchant memory locally…",
        total=total,
    )
    job_context.progress(
        25,
        total=total,
        message="Building private merchant matches locally…",
    )

    generated: list[tuple[str, bytes]] = []
    progress_interval = max(1, total // 100)
    for index, (memory_id, normalized_name) in enumerate(snapshots, start=1):
        job_context.check_cancelled()
        embedding = generate_embedding(normalized_name)
        if embedding is None:
            raise JobExecutionError("EMBEDDING_GENERATION_FAILED", retryable=True)
        generated.append((memory_id, serialize_embedding(embedding)))
        if index == total or index % progress_interval == 0:
            progress = 85 if total == 0 else 25 + int((index / total) * 60)
            _set_setup_status(progress=progress, updated=index)
            job_context.progress(
                progress,
                total=total,
                message=f"Prepared {index} of {total} private merchant matches…",
            )

    job_context.check_cancelled()
    write_db = SessionLocal()
    try:
        by_id = {
            memory.id: memory
            for memory in write_db.query(MerchantMemory)
            .filter(MerchantMemory.id.in_([item[0] for item in generated]))
            .all()
        } if generated else {}
        for memory_id, embedding_bytes in generated:
            memory = by_id.get(memory_id)
            if memory is None:
                continue
            memory.embedding_vector = embedding_bytes
            memory.embedding_model_version = MODEL_NAME
        job_context.check_cancelled()
        write_db.commit()
    except Exception:
        write_db.rollback()
        raise
    finally:
        write_db.close()

    updated = len(by_id)
    _set_setup_status(
        status="ready",
        progress=100,
        message="Similar-description matching is ready.",
        updated=updated,
        total=total,
    )
    return {"updated": updated, "total": total}
