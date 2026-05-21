from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class FaceDetectionResponse(BaseModel):
    id: int
    reading_id: Optional[int] = None
    unique_face_id: int
    face_image_path: Optional[str] = None
    source: str = "upload"
    created_at: datetime

    class Config:
        from_attributes = True


class UniqueFaceResponse(BaseModel):
    id: int
    representative_image_path: Optional[str] = None
    appearance_count: int
    first_seen_at: datetime
    last_seen_at: datetime

    class Config:
        from_attributes = True


class UniqueFaceDetail(UniqueFaceResponse):
    detections: list[FaceDetectionResponse] = []


class UniqueFaceList(BaseModel):
    total: int
    items: list[UniqueFaceResponse]
