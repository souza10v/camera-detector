import cv2
import numpy as np
import base64
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from app.services.plate_detector import plate_detector
from app.services.face_recognition_service import (
    detect_and_encode_faces, find_best_match, save_face_crop_stream
)
from app.config import settings

logger = logging.getLogger(__name__)


def decode_frame(b64: str) -> np.ndarray:
    data = base64.b64decode(b64)
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def encode_frame(frame: np.ndarray, quality: int = 80) -> str:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf).decode()


def _recognize_faces(frame: np.ndarray, face_cache: list[dict]) -> list[dict]:
    """Detect faces, match against cache, save crops. Returns full data for DB + overlay."""
    detected = detect_and_encode_faces(frame)
    results = []
    for det in detected:
        best, dist = find_best_match(det["embedding"], face_cache)
        matched = best and dist < settings.face_recognition_threshold
        crop_path = save_face_crop_stream(frame, det["bbox"])
        results.append({
            "bbox": list(det["bbox"]),
            "face_id": best["id"] if matched else None,
            "label": f"Pessoa #{best['id']}" if matched else "Desconhecido",
            # included for DB persistence in the route — stripped before sending to browser
            "embedding": det["embedding"],
            "crop_path": crop_path,
        })
    return results


def process_webcam_frame(
    frame: np.ndarray,
    run_ocr: bool = True,
    face_cache: list[dict] | None = None,
) -> dict:
    """Returns annotation data only — no frame encoding.
    face_cache=None skips face recognition for this frame."""
    plates = plate_detector.detect_plates(frame) if run_ocr else []
    best = plates[0] if plates else None

    faces = _recognize_faces(frame, face_cache) if face_cache is not None else None

    return {
        "plate_text": best["plate_text"] if best else None,
        "confidence": best["confidence"] if best else None,
        "plates_detected": len(plates),
        "plates": [
            {"text": p["plate_text"], "confidence": p["confidence"], "bbox": list(p["bbox"])}
            for p in plates
        ],
        "faces": faces,  # None = reuse last result on client
    }


def _draw_faces(frame: np.ndarray, faces: list[dict]) -> np.ndarray:
    for face in faces:
        x, y, w, h = face["bbox"]
        color = (0, 165, 255) if face["face_id"] is None else (255, 140, 0)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        label = face["label"]
        cv2.putText(frame, label, (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return frame


def process_rtsp_frame(
    frame: np.ndarray,
    plates_override: list[dict] | None = None,
    face_cache: list[dict] | None = None,
) -> dict:
    """Codifica o frame com anotações de placa e rosto.

    plates_override: resultado de OCR externo (background thread).
                     Se None, não anota placas neste frame.
    face_cache: cache de rostos para reconhecimento. None = pular face recognition.
    """
    plates = plates_override if plates_override is not None else []
    annotated = plate_detector.annotate_image(frame, plates)

    faces = []
    if face_cache is not None:
        faces = _recognize_faces(frame, face_cache)
        _draw_faces(annotated, faces)

    best = plates[0] if plates else None
    return {
        "frame_b64": encode_frame(annotated),
        "plate_text": best["plate_text"] if best else None,
        "confidence": best["confidence"] if best else None,
        "plates_detected": len(plates),
        "plates": [
            {"text": p["plate_text"], "confidence": p["confidence"], "bbox": list(p["bbox"])}
            for p in plates
        ],
        "faces": faces,
    }


class RTSPStreamer:
    def __init__(self, url: str, ocr_interval: int = 15, face_interval: int = 30):
        self.url = url
        self.ocr_interval = ocr_interval
        self.face_interval = face_interval
        self._cap: cv2.VideoCapture | None = None
        self._consecutive_failures = 0

        # ── OCR em background ───────────────────────────────────────────────
        # O OCR pode levar vários segundos por frame — rodamos em um thread
        # dedicado para não bloquear o loop de leitura do stream.
        self._ocr_lock = threading.Lock()
        self._ocr_busy = False
        self._last_plates: list[dict] = []
        self._ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rtsp_ocr")

    @staticmethod
    def _check_tcp(host: str, port: int, timeout: float = 5.0) -> bool:
        """Quick TCP probe — fails fast if the camera is unreachable."""
        import socket
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    def _parse_host_port(url: str) -> tuple[str, int] | None:
        """Extract host and port from an rtsp:// URL."""
        import re
        m = re.match(r"rtsp://(?:[^@]+@)?([^:/]+)(?::(\d+))?", url)
        if not m:
            return None
        host = m.group(1)
        port = int(m.group(2)) if m.group(2) else 554
        return host, port

    def open(self) -> tuple[bool, str]:
        """Open RTSP stream. Forces FFMPEG backend with TCP transport.
        Returns (success, error_message)."""
        import os
        logger.info("RTSPStreamer: opening %s", self.url)

        # Pre-flight TCP probe — gives a fast, clear error if camera is unreachable
        parsed = self._parse_host_port(self.url)
        if parsed:
            host, port = parsed
            logger.info("RTSPStreamer: TCP probe %s:%d …", host, port)
            if not self._check_tcp(host, port):
                err = (
                    f"Não foi possível conectar ao host {host}:{port}. "
                    "Verifique se a câmera está ligada e acessível na rede."
                )
                logger.error("RTSPStreamer: TCP probe failed — %s", err)
                return False, err
            logger.info("RTSPStreamer: TCP probe OK")

        # Force TCP transport + fast socket timeout (stimeout = microseconds)
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"

        logger.info("RTSPStreamer: trying CAP_FFMPEG backend…")
        self._cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)

        if not self._cap.isOpened():
            logger.warning("RTSPStreamer: CAP_FFMPEG failed, trying default backend…")
            self._cap.release()
            self._cap = cv2.VideoCapture(self.url)

        if not self._cap.isOpened():
            err = f"Não foi possível abrir o stream RTSP. Verifique a URL e as credenciais: {self.url}"
            logger.error("RTSPStreamer: %s", err)
            return False, err

        # Reduce internal buffer to 1 frame — avoids accumulating stale frames
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Log resolution reported by the stream headers
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        logger.info("RTSPStreamer: stream headers  %dx%d @ %.1f fps", w, h, fps)

        # Warmup: many cameras take 1-3 s before sending the first I-frame.
        # Try reading for up to 5 s before declaring success (or failure).
        import time as _time
        deadline = _time.monotonic() + 5.0
        warmup_ok = False
        while _time.monotonic() < deadline:
            ret, frame = self._cap.read()
            if ret and frame is not None:
                warmup_ok = True
                logger.info("RTSPStreamer: first frame received  shape=%s", frame.shape)
                break
            logger.debug("RTSPStreamer: warmup read failed, retrying…")
            _time.sleep(0.1)

        if not warmup_ok:
            self._cap.release()
            self._cap = None
            err = (
                "Stream aberto mas nenhum frame recebido em 5 s. "
                "Verifique o caminho RTSP, codec e credenciais."
            )
            logger.error("RTSPStreamer: %s", err)
            return False, err

        return True, ""

    def _ocr_worker(self, frame: np.ndarray) -> None:
        """Roda detect_plates em background e atualiza _last_plates ao concluir."""
        try:
            plates = plate_detector.detect_plates(frame)
            with self._ocr_lock:
                self._last_plates = plates
            if plates:
                logger.info(
                    "RTSPStreamer: OCR detectou %d placa(s): %s",
                    len(plates),
                    [p["plate_text"] for p in plates],
                )
        except Exception as exc:
            logger.warning("RTSPStreamer: OCR error: %s", exc)
        finally:
            with self._ocr_lock:
                self._ocr_busy = False

    def read_and_process(self, frame_number: int, face_cache: list[dict]) -> dict | None:
        if self._cap is None or not self._cap.isOpened():
            logger.error("RTSPStreamer: capture is not open")
            return None

        ret, frame = self._cap.read()

        if not ret:
            self._consecutive_failures += 1
            logger.warning(
                "RTSPStreamer: read failed (consecutive=%d)", self._consecutive_failures
            )
            # Allow up to 30 consecutive failures (~2 s at 15 fps) before giving up
            if self._consecutive_failures >= 30:
                logger.error("RTSPStreamer: 30 consecutive failures — closing stream")
                return None
            return {}  # empty dict = skip frame, keep trying

        self._consecutive_failures = 0

        # ── Dispara OCR em background (sem bloquear o loop de stream) ─────────
        # OCR só é disparado quando não há OCR em andamento e chegou o intervalo.
        should_run_ocr = (frame_number % self.ocr_interval == 0)
        if should_run_ocr:
            with self._ocr_lock:
                if not self._ocr_busy:
                    self._ocr_busy = True
                    self._ocr_executor.submit(self._ocr_worker, frame.copy())

        # Usa o último resultado de OCR disponível (pode ser de frames anteriores)
        with self._ocr_lock:
            plates = list(self._last_plates)

        # Face recognition: escalonado meio intervalo após OCR para nunca coincidir
        # (OCR em background + face em foreground ao mesmo tempo → pico de memória).
        # Com ocr_interval=15 e face_interval=30: OCR em 0,15,30... face em 7,37,67...
        face_offset = self.ocr_interval // 2
        run_face = ((frame_number + face_offset) % self.face_interval == 0)
        return process_rtsp_frame(
            frame,
            plates_override=plates,
            face_cache=face_cache if run_face else None,
        )

    def close(self):
        if self._cap:
            self._cap.release()
            self._cap = None
        self._ocr_executor.shutdown(wait=False, cancel_futures=True)
