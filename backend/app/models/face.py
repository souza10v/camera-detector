from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.database.connection import Base


class UniqueFace(Base):
    __tablename__ = "unique_faces"

    id = Column(Integer, primary_key=True, index=True)
    embedding = Column(Text, nullable=False)
    representative_image_path = Column(String(500), nullable=True)
    appearance_count = Column(Integer, default=1, nullable=False)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())


class FaceDetection(Base):
    __tablename__ = "face_detections"

    id = Column(Integer, primary_key=True, index=True)
    # nullable — stream detections have no associated plate reading
    reading_id = Column(Integer, ForeignKey("plate_readings.id"), nullable=True, index=True)
    unique_face_id = Column(Integer, ForeignKey("unique_faces.id"), nullable=False, index=True)
    face_image_path = Column(String(500), nullable=True)
    source = Column(String(20), nullable=False, default="upload")  # "upload" | "stream"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
