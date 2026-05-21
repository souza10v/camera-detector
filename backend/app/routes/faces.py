from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.services import face_db_service
from app.schemas.face import UniqueFaceList, UniqueFaceDetail, UniqueFaceResponse, FaceDetectionResponse

router = APIRouter(prefix="/faces", tags=["faces"])


@router.get("/", response_model=UniqueFaceList)
async def list_faces(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await face_db_service.list_unique_faces(db, skip=skip, limit=limit)
    return UniqueFaceList(
        total=result["total"],
        items=[UniqueFaceResponse.model_validate(f) for f in result["items"]],
    )


@router.get("/{face_id}", response_model=UniqueFaceDetail)
async def get_face(face_id: int, db: AsyncSession = Depends(get_db)):
    face = await face_db_service.get_unique_face(db, face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Rosto não encontrado")
    detections = await face_db_service.get_detections_for_face(db, face_id)
    return UniqueFaceDetail(
        **UniqueFaceResponse.model_validate(face).model_dump(),
        detections=[FaceDetectionResponse.model_validate(d) for d in detections],
    )
