import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database.connection import create_tables
from app.routes import upload, readings
from app.utils.file_utils import ensure_dirs


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    await create_tables()
    yield


app = FastAPI(
    title="Camera Detector API",
    description="Leitura automática de placas com anonimização de rostos",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve processed images — raw uploads are deleted after processing
app.mount("/images", StaticFiles(directory=settings.processed_dir), name="images")

app.include_router(upload.router, prefix="/api/v1")
app.include_router(readings.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
