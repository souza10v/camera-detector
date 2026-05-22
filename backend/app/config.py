from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/camera_detector"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    @property
    def database_sync_url(self) -> str:
        """URL síncrona para uso no worker Celery (psycopg2 em vez de asyncpg)."""
        return self.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    upload_dir: str = "/app/uploads"
    processed_dir: str = "/app/uploads/processed"
    max_file_size_mb: int = 50
    allowed_image_types: str = "image/jpeg,image/png,image/webp"
    allowed_video_types: str = "video/mp4,video/avi,video/mov"
    ocr_confidence_threshold: float = 0.5
    face_recognition_threshold: float = 0.55
    yolo_confidence_threshold: float = 0.5
    cors_origins: str = "http://localhost:4200"

    @property
    def allowed_image_types_list(self) -> List[str]:
        return [t.strip() for t in self.allowed_image_types.split(",")]

    @property
    def allowed_video_types_list(self) -> List[str]:
        return [t.strip() for t in self.allowed_video_types.split(",")]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
