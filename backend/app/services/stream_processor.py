import cv2
import numpy as np
import base64
from app.services.plate_detector import plate_detector
from app.services.face_recognition_service import (
    detect_and_encode_faces, find_best_match, save_face_crop_stream
)
from app.config import settings


def decode_frame(b64: str) -> np.ndarray:
    data = base64.b64decode(b64)
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def encode_frame(frame: np.ndarray, quality: int = 75) -> str:
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
    run_ocr: bool = True,
    face_cache: list[dict] | None = None,
) -> dict:
    """Encodes frame with plate + face annotations. No blur."""
    plates = plate_detector.detect_plates(frame) if run_ocr else []
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
    def __init__(self, url: str, ocr_interval: int = 10, face_interval: int = 20):
        self.url = url
        self.ocr_interval = ocr_interval
        self.face_interval = face_interval
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self.url)
        return self._cap.isOpened()

    def read_and_process(self, frame_number: int, face_cache: list[dict]) -> dict | None:
        if self._cap is None or not self._cap.isOpened():
            return None
        ret, frame = self._cap.read()
        if not ret:
            return None
        run_ocr = (frame_number % self.ocr_interval == 0)
        run_face = (frame_number % self.face_interval == 0)
        return process_rtsp_frame(
            frame,
            run_ocr=run_ocr,
            face_cache=face_cache if run_face else None,
        )

    def close(self):
        if self._cap:
            self._cap.release()
            self._cap = None
