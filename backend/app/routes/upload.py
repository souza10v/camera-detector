import asyncio
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.utils.file_utils import save_upload_file, validate_file_type
from app.services import reading_service
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

    # Persist reading record so we can return an ID immediately
    reading = await reading_service.create_reading(
        db=db,
        original_filename=file.filename,
        file_type=file_type,
    )

    # Save raw upload temporarily
    try:
        file_path, _ = await save_upload_file(file)
    except Exception as exc:
        await reading_service.update_reading_failed(db, reading.id, str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    # Run CPU-heavy processing in a thread pool so the event loop stays free
    loop = asyncio.get_event_loop()
    try:
        if file_type == "image":
            result = await loop.run_in_executor(None, image_processor.process_image, file_path)
        else:
            result = await loop.run_in_executor(None, image_processor.process_video, file_path)
    except Exception as exc:
        await reading_service.update_reading_failed(db, reading.id, str(exc))
        raise HTTPException(status_code=500, detail=f"Erro no processamento: {exc}")

    reading = await reading_service.update_reading_completed(
        db=db,
        reading_id=reading.id,
        plate_text=result["plate_text"],
        confidence=result["confidence"],
        processed_image_path=result["processed_image_path"],
        faces_detected=result["faces_detected"],
        plates_detected=result["plates_detected"],
    )

    image_url = None
    if result["processed_image_path"]:
        from pathlib import Path
        fname = Path(result["processed_image_path"]).name
        image_url = f"/images/{fname}"

    return ProcessingResult(
        reading_id=reading.id,
        plate_text=result["plate_text"],
        confidence=result["confidence"],
        faces_detected=result["faces_detected"],
        plates_detected=result["plates_detected"],
        processed_image_url=image_url,
        status=ProcessingStatus.completed,
        message="Processamento concluído com sucesso." if result["plate_text"] else "Processamento concluído. Nenhuma placa identificada.",
    )
