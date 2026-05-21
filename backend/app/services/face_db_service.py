import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.face import UniqueFace, FaceDetection
from app.services.face_recognition_service import find_best_match
from app.config import settings


async def find_or_create_unique_face(
    db: AsyncSession,
    embedding: list[float],
    crop_path: str | None,
) -> UniqueFace:
    result = await db.execute(select(UniqueFace))
    all_faces = result.scalars().all()

    candidates = [
        {"id": f.id, "embedding": json.loads(f.embedding)}
        for f in all_faces
    ]
    best, dist = find_best_match(embedding, candidates)

    if best and dist < settings.face_recognition_threshold:
        face = await db.get(UniqueFace, best["id"])
        face.appearance_count += 1
        face.last_seen_at = datetime.now(tz=timezone.utc)
        await db.commit()
        await db.refresh(face)
        return face

    new_face = UniqueFace(
        embedding=json.dumps(embedding),
        representative_image_path=crop_path,
        appearance_count=1,
    )
    db.add(new_face)
    await db.commit()
    await db.refresh(new_face)
    return new_face


async def create_face_detection(
    db: AsyncSession,
    unique_face_id: int,
    face_image_path: str | None,
    reading_id: int | None = None,
    source: str = "upload",
) -> FaceDetection:
    detection = FaceDetection(
        reading_id=reading_id,
        unique_face_id=unique_face_id,
        face_image_path=face_image_path,
        source=source,
    )
    db.add(detection)
    await db.commit()
    await db.refresh(detection)
    return detection


async def list_unique_faces(db: AsyncSession, skip: int = 0, limit: int = 20) -> dict:
    count_result = await db.execute(select(func.count(UniqueFace.id)))
    total = count_result.scalar()
    result = await db.execute(
        select(UniqueFace).order_by(UniqueFace.last_seen_at.desc()).offset(skip).limit(limit)
    )
    return {"total": total, "items": result.scalars().all()}


async def get_unique_face(db: AsyncSession, face_id: int) -> UniqueFace | None:
    return await db.get(UniqueFace, face_id)


async def get_detections_for_face(db: AsyncSession, face_id: int) -> list[FaceDetection]:
    result = await db.execute(
        select(FaceDetection)
        .where(FaceDetection.unique_face_id == face_id)
        .order_by(FaceDetection.created_at.desc())
    )
    return result.scalars().all()


async def get_detections_for_reading(db: AsyncSession, reading_id: int) -> list[FaceDetection]:
    result = await db.execute(
        select(FaceDetection).where(FaceDetection.reading_id == reading_id)
    )
    return result.scalars().all()


async def load_face_cache(db: AsyncSession) -> list[dict]:
    """Load all known face embeddings for in-memory matching during live stream."""
    result = await db.execute(select(UniqueFace.id, UniqueFace.embedding))
    return [{"id": row.id, "embedding": json.loads(row.embedding)} for row in result.all()]
