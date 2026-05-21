from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.services import reading_service
from app.schemas.reading import PlateReadingList, PlateReadingResponse

router = APIRouter(prefix="/readings", tags=["readings"])


@router.get("/", response_model=PlateReadingList)
async def list_readings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await reading_service.list_readings(db, skip=skip, limit=limit)


@router.get("/search", response_model=PlateReadingList)
async def search_by_plate(
    plate: str = Query(..., min_length=1, description="Texto parcial ou completo da placa"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await reading_service.search_by_plate(db, plate=plate, skip=skip, limit=limit)


@router.get("/{reading_id}", response_model=PlateReadingResponse)
async def get_reading(
    reading_id: int,
    db: AsyncSession = Depends(get_db),
):
    reading = await reading_service.get_reading_by_id(db, reading_id)
    if not reading:
        raise HTTPException(status_code=404, detail="Leitura não encontrada")
    return reading
