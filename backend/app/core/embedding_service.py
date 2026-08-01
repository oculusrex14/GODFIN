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
from app.models.merchant_memory import MerchantMemory

logger = logging.getLogger(__name__)

MODEL_NAME = 'all-MiniLM-L6-v2'
FASTEMBED_MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'
EMBEDDING_DIM = 384
SIMILARITY_THRESHOLD = 0.80
EMBEDDING_FORMAT_MAGIC = b"GDFEMB01"
EMBEDDING_HEADER = struct.Struct("<8sI")
EMBEDDING_DTYPE = np.dtype("<f4")

# Lazy-loaded model singleton
_model = None
_setup_lock = threading.Lock()
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
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            return None
    return _model


def generate_embedding(text: str) -> Optional[np.ndarray]:
    model = _get_model()
    if model is None:
        return None
    try:
        embedding = next(model.embed([text]))
        return np.asarray(embedding, dtype=np.float32)
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
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
    with _setup_lock:
        return dict(_setup_status)


def _set_setup_status(**updates) -> None:
    with _setup_lock:
        _setup_status.update(updates)


def start_embedding_setup() -> bool:
    """Download the model and index merchants in a background thread."""
    with _setup_lock:
        if _setup_status["status"] in {"queued", "downloading", "indexing"}:
            return False
        _setup_status.update(
            status="queued",
            progress=1,
            message="Preparing the local embedding model…",
            updated=0,
            total=0,
        )

    def worker() -> None:
        db = None
        try:
            _set_setup_status(
                status="downloading",
                progress=5,
                message="Downloading the local model (~100 MB)…",
            )
            if _get_model() is None:
                raise RuntimeError("The embedding model could not be downloaded.")

            db = SessionLocal()
            memories = [
                memory
                for memory in db.query(MerchantMemory).all()
                if _embedding_needs_refresh(memory)
            ]
            total = len(memories)
            _set_setup_status(
                status="indexing",
                progress=25,
                message="Indexing merchant memory locally…",
                total=total,
            )

            updated = 0
            for index, memory in enumerate(memories, start=1):
                if update_merchant_embedding(db, memory):
                    updated += 1
                progress = 100 if total == 0 else 25 + int((index / total) * 75)
                _set_setup_status(progress=progress, updated=updated)

            db.commit()
            _set_setup_status(
                status="ready",
                progress=100,
                message="Embedding classification is ready.",
                updated=updated,
                total=total,
            )
        except Exception as exc:
            if db is not None:
                db.rollback()
            logger.exception("Embedding setup failed")
            _set_setup_status(
                status="failed",
                progress=0,
                message=str(exc),
            )
        finally:
            if db is not None:
                db.close()

    threading.Thread(
        target=worker,
        name="godfin-embedding-setup",
        daemon=True,
    ).start()
    return True
