import cv2
import numpy as np
import base64
import time
from app.services.face_anonymizer import face_anonymizer
from app.services.plate_detector import plate_detector
from app.config import settings


def decode_frame(b64: str) -> np.ndarray:
    data = base64.b64decode(b64)
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def encode_frame(frame: np.ndarray, quality: int = 75) -> str:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf).decode()


def process_frame(frame: np.ndarray, run_ocr: bool = True) -> dict:
    plates = plate_detector.detect_plates(frame) if run_ocr else []
    annotated = plate_detector.annotate_image(frame, plates)
    anonymized, face_count = face_anonymizer.detect_and_blur(annotated)

    best = plates[0] if plates else None
    return {
        "frame_b64": encode_frame(anonymized),
        "plate_text": best["plate_text"] if best else None,
        "confidence": best["confidence"] if best else None,
        "plates_detected": len(plates),
        "faces_detected": face_count,
    }


class RTSPStreamer:
    """Opens an RTSP (or any OpenCV-compatible) stream and processes frames."""

    def __init__(self, url: str, ocr_interval: int = 10):
        self.url = url
        self.ocr_interval = ocr_interval  # run OCR every N frames
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self.url)
        return self._cap.isOpened()

    def read_and_process(self, frame_number: int) -> dict | None:
        if self._cap is None or not self._cap.isOpened():
            return None
        ret, frame = self._cap.read()
        if not ret:
            return None
        run_ocr = (frame_number % self.ocr_interval == 0)
        return process_frame(frame, run_ocr=run_ocr)

    def close(self):
        if self._cap:
            self._cap.release()
            self._cap = None
