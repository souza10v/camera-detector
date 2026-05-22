import socket
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from celery.result import AsyncResult
from app.database.connection import get_db
from app.models.camera import Camera
from app.worker import celery_app

router = APIRouter(prefix="/cameras", tags=["cameras"])

# Armazena task_id em memória por camera_id.
# Em produção real, use Redis; para o MVP, memória é suficiente (reiniciar o
# processo perde o mapa, mas auto_start no lifespan repovoar).
_camera_tasks: dict[int, str] = {}   # camera_id → task_id


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


def _task_status(camera_id: int) -> str:
    """Retorna o estado da task Celery associada à câmera.

    Lógica: se existe task_id no dicionário, a task foi despachada e está
    rodando (PENDING = aguardando worker pegar, STARTED = em execução).
    Só marcamos como 'stopped' quando Celery confirma falha/conclusão/revogação.
    """
    task_id = _camera_tasks.get(camera_id)
    if not task_id:
        return "stopped"
    res = AsyncResult(task_id, app=celery_app)
    state = res.state   # PENDING, STARTED, SUCCESS, FAILURE, REVOKED
    if state in ("SUCCESS", "FAILURE", "REVOKED"):
        _camera_tasks.pop(camera_id, None)
        return "stopped"
    # PENDING = despachada mas ainda não confirmada pelo worker
    # STARTED = worker confirmou que está executando
    # Ambos significam "rodando" para o usuário
    return "running"


def start_camera_worker(camera_id: int) -> str:
    """Dispara a task Celery para a câmera. Retorna o task_id."""
    from app.tasks.camera_task import process_camera
    # Revoga task anterior se existir
    old_id = _camera_tasks.get(camera_id)
    if old_id:
        celery_app.control.revoke(old_id, terminate=True)

    result = process_camera.delay(camera_id)
    _camera_tasks[camera_id] = result.id
    return result.id


def stop_camera_worker(camera_id: int) -> None:
    task_id = _camera_tasks.pop(camera_id, None)
    if task_id:
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")


# ── CRUD ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[CameraOut])
async def list_cameras(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Camera).order_by(Camera.name))
    return result.scalars().all()


def _assert_online(url: str) -> None:
    """Lança HTTPException 503 se a câmera não estiver acessível."""
    parsed = _parse_host_port(url)
    if not parsed:
        raise HTTPException(status_code=400, detail="URL da câmera inválida.")
    host, port = parsed
    if not _tcp_probe(host, port):
        raise HTTPException(
            status_code=503,
            detail=f"Câmera offline — não foi possível conectar em {host}:{port}. "
                   "Verifique se a câmera está ligada e acessível na rede."
        )


@router.post("/", response_model=CameraOut, status_code=201)
async def create_camera(body: CameraIn, db: AsyncSession = Depends(get_db)):
    # Se marcada como ativa, valida conectividade antes de salvar
    if body.enabled:
        _assert_online(body.url)

    cam = Camera(**body.model_dump())
    db.add(cam)
    await db.commit()
    await db.refresh(cam)
    if cam.enabled:
        start_camera_worker(cam.id)
    return cam


@router.put("/{camera_id}", response_model=CameraOut)
async def update_camera(camera_id: int, body: CameraIn, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")

    was_enabled = cam.enabled
    for k, v in body.model_dump().items():
        setattr(cam, k, v)
    await db.commit()
    await db.refresh(cam)

    if cam.enabled:
        # Valida conectividade antes de (re)iniciar o worker
        _assert_online(cam.url)
        if _task_status(camera_id) == "stopped":
            start_camera_worker(camera_id)
    else:
        stop_camera_worker(camera_id)

    return cam


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(camera_id: int, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")
    stop_camera_worker(camera_id)
    await db.delete(cam)
    await db.commit()


# ── Status / controle ─────────────────────────────────────────────────────

@router.get("/{camera_id}/ping")
async def ping_camera(camera_id: int, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")
    parsed = _parse_host_port(cam.url)
    if not parsed:
        return {"online": False, "reason": "URL inválida"}
    host, port = parsed
    online = _tcp_probe(host, port)
    return {"online": online, "host": host, "port": port}


@router.get("/{camera_id}/worker-status")
async def worker_status(camera_id: int):
    """Estado atual do worker de processamento desta câmera."""
    status = _task_status(camera_id)
    task_id = _camera_tasks.get(camera_id)
    return {"camera_id": camera_id, "status": status, "task_id": task_id}


@router.post("/{camera_id}/start")
async def start_worker(camera_id: int, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")

    if not cam.enabled:
        raise HTTPException(status_code=400, detail="Câmera está desabilitada. Habilite-a antes de processar.")

    # Valida conectividade antes de despachar o worker
    parsed = _parse_host_port(cam.url)
    if not parsed:
        raise HTTPException(status_code=400, detail="URL da câmera inválida.")
    host, port = parsed
    if not _tcp_probe(host, port):
        raise HTTPException(
            status_code=503,
            detail=f"Câmera offline — não foi possível conectar em {host}:{port}. Verifique se a câmera está ligada e acessível na rede."
        )

    task_id = start_camera_worker(camera_id)
    return {"status": "starting", "task_id": task_id}


@router.post("/{camera_id}/stop")
async def stop_worker(camera_id: int):
    stop_camera_worker(camera_id)
    return {"status": "stopped"}


@router.get("/workers/status")
async def all_workers_status():
    """Retorna status de todos os workers ativos."""
    return {
        cam_id: {"task_id": tid, "status": _task_status(cam_id)}
        for cam_id, tid in list(_camera_tasks.items())
    }
