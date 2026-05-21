from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.reading import ProcessingStatus


class PlateReadingBase(BaseModel):
    plate_text: Optional[str] = None
    confidence: Optional[float] = None
    original_filename: str
    file_type: str
    status: ProcessingStatus
    plates_detected: int = 0
    faces_detected: int = 0


class PlateReadingCreate(PlateReadingBase):
    pass


class PlateReadingResponse(PlateReadingBase):
    id: int
    processed_image_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlateReadingList(BaseModel):
    total: int
    items: list[PlateReadingResponse]


class ProcessingResult(BaseModel):
    reading_id: int
    plate_text: Optional[str]
    confidence: Optional[float]
    plates_detected: int
    faces_detected: int
    processed_image_url: Optional[str]
    status: ProcessingStatus
    message: str
