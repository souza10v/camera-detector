from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.sql import func
from app.models.reading import PlateReading, ProcessingStatus
from app.schemas.reading import PlateReadingList, PlateReadingResponse


async def create_reading(
    db: AsyncSession,
    original_filename: str,
    file_type: str,
) -> PlateReading:
    reading = PlateReading(
        original_filename=original_filename,
        file_type=file_type,
        status=ProcessingStatus.pending,
    )
    db.add(reading)
    await db.commit()
    await db.refresh(reading)
    return reading


async def update_reading_completed(
    db: AsyncSession,
    reading_id: int,
    plate_text: str | None,
    confidence: float | None,
    processed_image_path: str | None,
    faces_detected: int,
    plates_detected: int,
) -> PlateReading:
    reading = await db.get(PlateReading, reading_id)
    reading.plate_text = plate_text
    reading.confidence = confidence
    reading.processed_image_path = processed_image_path
    reading.faces_detected = faces_detected
    reading.plates_detected = plates_detected
    reading.status = ProcessingStatus.completed
    await db.commit()
    await db.refresh(reading)
    return reading


async def update_reading_failed(
    db: AsyncSession,
    reading_id: int,
    error_message: str,
) -> PlateReading:
    reading = await db.get(PlateReading, reading_id)
    reading.status = ProcessingStatus.failed
    reading.error_message = error_message
    await db.commit()
    await db.refresh(reading)
    return reading


async def list_readings(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
) -> PlateReadingList:
    count_result = await db.execute(select(func.count(PlateReading.id)))
    total = count_result.scalar()

    result = await db.execute(
        select(PlateReading).order_by(PlateReading.created_at.desc()).offset(skip).limit(limit)
    )
    items = result.scalars().all()
    return PlateReadingList(total=total, items=[PlateReadingResponse.model_validate(i) for i in items])


async def search_by_plate(
    db: AsyncSession,
    plate: str,
    skip: int = 0,
    limit: int = 20,
) -> PlateReadingList:
    query = select(PlateReading).where(
        PlateReading.plate_text.ilike(f"%{plate}%")
    ).order_by(PlateReading.created_at.desc()).offset(skip).limit(limit)

    count_query = select(func.count(PlateReading.id)).where(
        PlateReading.plate_text.ilike(f"%{plate}%")
    )

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    result = await db.execute(query)
    items = result.scalars().all()
    return PlateReadingList(total=total, items=[PlateReadingResponse.model_validate(i) for i in items])


async def get_reading_by_id(db: AsyncSession, reading_id: int) -> PlateReading | None:
    return await db.get(PlateReading, reading_id)
