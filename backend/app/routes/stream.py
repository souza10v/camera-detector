import asyncio
import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.database.connection import AsyncSessionLocal
from app.services.face_db_service import load_face_cache, find_or_create_unique_face, create_face_detection
from app.services.stream_processor import decode_frame, process_webcam_frame, RTSPStreamer

router = APIRouter(prefix="/ws", tags=["stream"])

WEBCAM_OCR_INTERVAL = 8
WEBCAM_FACE_INTERVAL = 15
CACHE_REFRESH_SECONDS = 60
FACE_SAVE_COOLDOWN = 30  # seconds between saves of the same unique face


async def _refresh_cache() -> list[dict]:
    async with AsyncSessionLocal() as db:
        return await load_face_cache(db)


async def _persist_faces(faces: list[dict], cooldown: dict[int, float]) -> list[dict]:
    """Save detected faces to DB. Returns the same list stripped of embedding/crop_path."""
    now = time.monotonic()
    to_save = [f for f in faces if f.get("embedding") and f.get("crop_path")]
    if to_save:
        async with AsyncSessionLocal() as db:
            for face in to_save:
                unique_face = await find_or_create_unique_face(
                    db, face["embedding"], face["crop_path"]
                )
                last_saved = cooldown.get(unique_face.id)
                if last_saved is None or now - last_saved > FACE_SAVE_COOLDOWN:
                    await create_face_detection(
                        db, unique_face.id, face["crop_path"],
                        reading_id=None, source="stream",
                    )
                    cooldown[unique_face.id] = now
                    # Update cache with newly created face so it's recognized next interval
                    face["face_id"] = unique_face.id
                    face["label"] = f"Pessoa #{unique_face.id}"

    # Strip internal fields before returning to caller (not sent to browser)
    return [
        {"bbox": f["bbox"], "face_id": f["face_id"], "label": f["label"]}
        for f in faces
    ]


@router.websocket("/webcam")
async def webcam_stream(ws: WebSocket):
    await ws.accept()

    face_cache = await _refresh_cache()
    last_refresh = time.monotonic()
    last_faces: list[dict] = []
    face_cooldown: dict[int, float] = {}
    frame_number = 0
    loop = asyncio.get_event_loop()

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") != "frame":
                continue

            if time.monotonic() - last_refresh > CACHE_REFRESH_SECONDS:
                face_cache = await _refresh_cache()
                last_refresh = time.monotonic()

            run_ocr = (frame_number % WEBCAM_OCR_INTERVAL == 0)
            run_face = (frame_number % WEBCAM_FACE_INTERVAL == 0)
            frame_number += 1

            frame = decode_frame(msg["data"])
            result = await loop.run_in_executor(
                None, process_webcam_frame, frame, run_ocr,
                face_cache if run_face else None,
            )

            if result["faces"] is not None:
                # Persist to DB and strip internal fields
                last_faces = await _persist_faces(result["faces"], face_cooldown)

            result["faces"] = last_faces
            await ws.send_json({"type": "result", **result})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


@router.websocket("/rtsp")
async def rtsp_stream(ws: WebSocket):
    await ws.accept()

    face_cache = await _refresh_cache()
    last_refresh = time.monotonic()
    face_cooldown: dict[int, float] = {}
    streamer: RTSPStreamer | None = None
    loop = asyncio.get_event_loop()

    try:
        init_raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
        init = json.loads(init_raw)

        if init.get("type") != "start" or not init.get("url"):
            await ws.send_json({"type": "error", "message": "Envie {type: 'start', url: 'rtsp://...'}"})
            return

        streamer = RTSPStreamer(url=init["url"])
        await ws.send_json({"type": "connecting", "message": "Abrindo stream, aguarde…"})
        opened, err_msg = await loop.run_in_executor(None, streamer.open)
        if not opened:
            await ws.send_json({"type": "error", "message": err_msg})
            return

        await ws.send_json({"type": "connected", "message": "Stream aberto com sucesso."})

        frame_number = 0
        stop_event = asyncio.Event()

        async def listen_for_stop():
            try:
                while True:
                    msg = await ws.receive_text()
                    if json.loads(msg).get("type") == "stop":
                        stop_event.set()
                        break
            except Exception:
                stop_event.set()

        asyncio.create_task(listen_for_stop())

        last_rtsp_faces: list[dict] = []

        while not stop_event.is_set():
            if time.monotonic() - last_refresh > CACHE_REFRESH_SECONDS:
                face_cache = await _refresh_cache()
                last_refresh = time.monotonic()

            result = await loop.run_in_executor(
                None, streamer.read_and_process, frame_number, face_cache
            )
            if result is None:
                await ws.send_json({"type": "error", "message": "Stream encerrado."})
                break

            frame_number += 1

            # Empty dict means consecutive read failure — skip this frame
            if not result:
                await asyncio.sleep(0.033)
                continue

            if result.get("faces") is not None:
                last_rtsp_faces = await _persist_faces(result["faces"], face_cooldown)
            result["faces"] = last_rtsp_faces

            await ws.send_json({"type": "result", **result})
            await asyncio.sleep(0.067)

    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        await ws.send_json({"type": "error", "message": "Timeout aguardando URL."})
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        if streamer:
            await loop.run_in_executor(None, streamer.close)
