"""
Task Celery que processa uma câmera RTSP indefinidamente em background.
Cada câmera habilitada roda em uma task separada (um processo do worker).
"""
import json
import logging
import time
from datetime import datetime, timezone

from app.worker import celery_app
from app.config import settings

# ── Importa TODOS os models aqui para garantir que o metadata do SQLAlchemy ──
# esteja completo antes do primeiro uso de sessão. Sem isso, FK entre tabelas
# pode falhar ao ser resolvida (ex: face_detections.reading_id → plate_readings).
from app.models.camera import Camera          # noqa: F401
from app.models.reading import PlateReading, ProcessingStatus  # noqa: F401
from app.models.face import UniqueFace, FaceDetection  # noqa: F401

logger = logging.getLogger(__name__)

FACE_CACHE_TTL   = 60    # segundos entre recarregamentos do cache de faces
PLATE_COOLDOWN   = 30    # segundos entre saves da mesma placa
FACE_COOLDOWN    = 30    # segundos entre saves do mesmo rosto
STOP_CHECK_EVERY = 50    # frames entre verificações de "câmera ainda ativa?"


# ── Helpers síncronos (não podem usar async/await) ───────────────────────────
# Todos os models são importados no topo do módulo — não repetir aqui.

from sqlalchemy import select
from app.services.face_recognition_service import find_best_match
from app.database.sync_connection import SyncSessionLocal
from app.services.stream_processor import RTSPStreamer


def _load_face_cache_sync(db) -> list[dict]:
    rows = db.execute(select(UniqueFace.id, UniqueFace.embedding)).all()
    return [{"id": r.id, "embedding": json.loads(r.embedding)} for r in rows]


def _find_or_create_face_sync(db, embedding: list, crop_path: str | None):
    rows = db.execute(select(UniqueFace)).scalars().all()
    candidates = [{"id": f.id, "embedding": json.loads(f.embedding)} for f in rows]
    best, dist = find_best_match(embedding, candidates)

    if best and dist < settings.face_recognition_threshold:
        face = db.get(UniqueFace, best["id"])
        face.appearance_count += 1
        face.last_seen_at = datetime.now(tz=timezone.utc)
        db.commit()
        return face

    face = UniqueFace(
        embedding=json.dumps(embedding),
        representative_image_path=crop_path,
        appearance_count=1,
    )
    db.add(face)
    db.commit()
    db.refresh(face)
    return face


def _save_plate_sync(db, result: dict, source_label: str):
    reading = PlateReading(
        original_filename=f"[worker:{source_label}]",
        file_type="stream",
        plate_text=result["plate_text"],
        confidence=result.get("confidence") or 0.0,
        plates_detected=result.get("plates_detected", 1),
        faces_detected=0,
        status=ProcessingStatus.completed,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


def _save_face_sync(db, unique_face, crop_path, reading_id, source_label):
    det = FaceDetection(
        reading_id=reading_id,
        unique_face_id=unique_face.id,
        face_image_path=crop_path,
        source=f"worker:{source_label}",
    )
    db.add(det)
    db.commit()


# ── Task principal ───────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="tasks.process_camera", max_retries=3)
def process_camera(self, camera_id: int):
    """Processa uma câmera RTSP em loop até ser revogada ou câmera desabilitada."""
    logger.info("[worker] camera_id=%d  task_id=%s  iniciando", camera_id, self.request.id)

    # ── Carrega dados da câmera ──────────────────────────────────────────────
    with SyncSessionLocal() as db:
        cam = db.get(Camera, camera_id)
        if not cam or not cam.enabled:
            logger.info("[worker] camera_id=%d desabilitada, encerrando", camera_id)
            return {"status": "skipped", "reason": "disabled"}
        cam_url   = cam.url
        cam_label = cam.name

    # ── Abre stream ──────────────────────────────────────────────────────────
    streamer = RTSPStreamer(url=cam_url, ocr_interval=15, face_interval=30)
    opened, err = streamer.open()
    if not opened:
        logger.error("[worker] camera_id=%d  falha ao abrir: %s", camera_id, err)
        raise self.retry(countdown=30, exc=RuntimeError(err))

    logger.info("[worker] camera_id=%d  stream aberto: %s", camera_id, cam_label)

    # ── Estado do loop ───────────────────────────────────────────────────────
    face_cache: list[dict] = []
    last_cache_refresh = 0.0
    plate_cooldown: dict[str, float] = {}
    face_cooldown:  dict[int, float]  = {}
    frame_number = 0

    try:
        while True:
            now = time.monotonic()

            # Recarrega cache de faces periodicamente
            if now - last_cache_refresh > FACE_CACHE_TTL:
                with SyncSessionLocal() as db:
                    face_cache = _load_face_cache_sync(db)
                last_cache_refresh = now

            # Verifica se câmera ainda está habilitada (a cada N frames)
            if frame_number > 0 and frame_number % STOP_CHECK_EVERY == 0:
                with SyncSessionLocal() as db:
                    cam = db.get(Camera, camera_id)
                    if not cam or not cam.enabled:
                        logger.info("[worker] camera_id=%d desabilitada, encerrando loop", camera_id)
                        break

            result = streamer.read_and_process(frame_number, face_cache)

            if result is None:
                logger.error("[worker] camera_id=%d  stream encerrado", camera_id)
                break

            frame_number += 1

            if not result:          # frame falhado temporariamente
                time.sleep(0.1)
                continue

            plate_text = result.get("plate_text")
            faces      = result.get("faces") or []

            # ── Persiste placa ────────────────────────────────────────────────
            reading_id = None
            if plate_text:
                last_plate = plate_cooldown.get(plate_text, 0)
                if now - last_plate >= PLATE_COOLDOWN:
                    with SyncSessionLocal() as db:
                        reading = _save_plate_sync(db, result, cam_label)
                        reading_id = reading.id
                    plate_cooldown[plate_text] = now
                    logger.info("[worker] camera_id=%d  placa=%s  reading_id=%d",
                                camera_id, plate_text, reading_id)

            # ── Persiste rostos ───────────────────────────────────────────────
            for face in faces:
                if not face.get("embedding") or not face.get("crop_path"):
                    continue
                with SyncSessionLocal() as db:
                    unique_face = _find_or_create_face_sync(db, face["embedding"], face["crop_path"])
                    last_face = face_cooldown.get(unique_face.id, 0)
                    if now - last_face >= FACE_COOLDOWN:
                        _save_face_sync(db, unique_face, face["crop_path"], reading_id, cam_label)
                        face_cooldown[unique_face.id] = now
                        logger.info("[worker] camera_id=%d  rosto=%d salvo", camera_id, unique_face.id)

            time.sleep(0.067)   # ~15 fps de processamento

    except Exception as exc:
        logger.exception("[worker] camera_id=%d  erro inesperado: %s", camera_id, exc)
        raise
    finally:
        streamer.close()
        logger.info("[worker] camera_id=%d  task encerrada  frames=%d", camera_id, frame_number)

    return {"status": "done", "frames": frame_number}
