import asyncio
import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.stream_processor import decode_frame, process_frame, RTSPStreamer

router = APIRouter(prefix="/ws", tags=["stream"])

# How often to run the expensive OCR pipeline (every N frames from webcam)
WEBCAM_OCR_INTERVAL = 8


@router.websocket("/webcam")
async def webcam_stream(ws: WebSocket):
    """
    Client sends: {"type": "frame", "data": "<base64 JPEG>"}
    Server sends: {"type": "result", "frame": "<base64 JPEG>", "plate_text": ...,
                   "confidence": ..., "plates_detected": ..., "faces_detected": ...}
    """
    await ws.accept()
    frame_number = 0
    loop = asyncio.get_event_loop()

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            if msg.get("type") != "frame":
                continue

            frame = decode_frame(msg["data"])
            run_ocr = (frame_number % WEBCAM_OCR_INTERVAL == 0)
            frame_number += 1

            result = await loop.run_in_executor(None, process_frame, frame, run_ocr)
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
    """
    Client sends first: {"type": "start", "url": "rtsp://..."}
    Server streams:     {"type": "result", "frame": ..., "plate_text": ..., ...}
    Client can send:    {"type": "stop"} to end the stream.
    """
    await ws.accept()
    streamer: RTSPStreamer | None = None
    loop = asyncio.get_event_loop()

    try:
        # Wait for the start command with the RTSP URL
        init_raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
        init = json.loads(init_raw)

        if init.get("type") != "start" or not init.get("url"):
            await ws.send_json({"type": "error", "message": "Envie {type: 'start', url: 'rtsp://...'}"})
            return

        streamer = RTSPStreamer(url=init["url"], ocr_interval=10)
        opened = await loop.run_in_executor(None, streamer.open)
        if not opened:
            await ws.send_json({"type": "error", "message": f"Não foi possível abrir o stream: {init['url']}"})
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

        while not stop_event.is_set():
            result = await loop.run_in_executor(None, streamer.read_and_process, frame_number)
            if result is None:
                await ws.send_json({"type": "error", "message": "Stream encerrado ou sem frames."})
                break
            frame_number += 1
            await ws.send_json({"type": "result", **result})
            # ~15 fps cap to avoid overwhelming the client
            await asyncio.sleep(0.067)

    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        await ws.send_json({"type": "error", "message": "Timeout aguardando URL do stream."})
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        if streamer:
            await loop.run_in_executor(None, streamer.close)
