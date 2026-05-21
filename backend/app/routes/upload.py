import asyncio
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.utils.file_utils import save_upload_file, validate_file_type
from app.services import reading_service, face_db_service
from app.services.image_processor import image_processor
from app.schemas.reading import ProcessingResult
from app.models.reading import ProcessingStatus

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/", response_model=ProcessingResult)
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    file_type = validate_file_type(file.content_type, file.filename)

    reading = await reading_service.create_reading(
        db=db,
        original_filename=file.filename,
        file_type=file_type,
    )

    try:
        file_path, _ = await save_upload_file(file)
    except Exception as exc:
        await reading_service.update_reading_failed(db, reading.id, str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    loop = asyncio.get_event_loop()
    try:
        processor = image_processor.process_image if file_type == "image" else image_processor.process_video
        result = await loop.run_in_executor(None, processor, file_path, reading.id)
    except Exception as exc:
        await reading_service.update_reading_failed(db, reading.id, str(exc))
        raise HTTPException(status_code=500, detail=f"Erro no processamento: {exc}")

    reading = await reading_service.update_reading_completed(
        db=db,
        reading_id=reading.id,
        plate_text=result["plate_text"],
        confidence=result["confidence"],
        processed_image_path=result["processed_image_path"],
        faces_detected=len(result["face_data"]),
        plates_detected=result["plates_detected"],
    )

    # Persist each detected face — find or create unique face record
    for face in result["face_data"]:
        unique_face = await face_db_service.find_or_create_unique_face(
            db, face["embedding"], face["crop_path"]
        )
        await face_db_service.create_face_detection(
            db, unique_face.id, face["crop_path"],
            reading_id=reading.id, source="upload",
        )

    image_url = None
    if result["processed_image_path"]:
        image_url = f"/images/{Path(result['processed_image_path']).name}"

    return ProcessingResult(
        reading_id=reading.id,
        plate_text=result["plate_text"],
        confidence=result["confidence"],
        plates_detected=result["plates_detected"],
        faces_detected=len(result["face_data"]),
        processed_image_url=image_url,
        status=ProcessingStatus.completed,
        message="Processamento concluído com sucesso." if result["plate_text"] else "Processamento concluído. Nenhuma placa identificada.",
    )
