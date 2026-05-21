from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Enum
from sqlalchemy.sql import func
import enum
from app.database.connection import Base


class ProcessingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class PlateReading(Base):
    __tablename__ = "plate_readings"

    id = Column(Integer, primary_key=True, index=True)
    plate_text = Column(String(20), nullable=True, index=True)
    confidence = Column(Float, nullable=True)
    processed_image_path = Column(String(500), nullable=True)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(10), nullable=False)
    status = Column(Enum(ProcessingStatus), default=ProcessingStatus.pending, nullable=False)
    error_message = Column(Text, nullable=True)
    faces_detected = Column(Integer, default=0)
    plates_detected = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
