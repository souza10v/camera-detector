import socket
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.connection import get_db
from app.models.camera import Camera

router = APIRouter(prefix="/cameras", tags=["cameras"])


# ── Schemas ────────────────────────────────────────────────────────────────

class CameraIn(BaseModel):
    name: str
    url: str
    description: str | None = None
    enabled: bool = True


class CameraOut(BaseModel):
    id: int
    name: str
    url: str
    description: str | None
    enabled: bool

    class Config:
        from_attributes = True


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse_host_port(url: str) -> tuple[str, int] | None:
    import re
    m = re.match(r"rtsp://(?:[^@]+@)?([^:/]+)(?::(\d+))?", url)
    if not m:
        return None
    return m.group(1), int(m.group(2) or 554)


def _tcp_probe(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[CameraOut])
async def list_cameras(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Camera).order_by(Camera.name))
    return result.scalars().all()


@router.post("/", response_model=CameraOut, status_code=201)
async def create_camera(body: CameraIn, db: AsyncSession = Depends(get_db)):
    cam = Camera(**body.model_dump())
    db.add(cam)
    await db.commit()
    await db.refresh(cam)
    return cam


@router.put("/{camera_id}", response_model=CameraOut)
async def update_camera(camera_id: int, body: CameraIn, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")
    for k, v in body.model_dump().items():
        setattr(cam, k, v)
    await db.commit()
    await db.refresh(cam)
    return cam


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(camera_id: int, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")
    await db.delete(cam)
    await db.commit()


@router.get("/{camera_id}/ping")
async def ping_camera(camera_id: int, db: AsyncSession = Depends(get_db)):
    """Testa conectividade TCP com a câmera. Rápido (~3 s timeout)."""
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")

    parsed = _parse_host_port(cam.url)
    if not parsed:
        return {"online": False, "reason": "URL inválida"}

    host, port = parsed
    online = _tcp_probe(host, port)
    return {"online": online, "host": host, "port": port}
