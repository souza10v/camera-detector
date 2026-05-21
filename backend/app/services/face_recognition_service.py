import cv2
import numpy as np
import face_recognition
import os
from pathlib import Path
from app.config import settings


def _ensure_faces_dir() -> str:
    faces_dir = os.path.join(settings.processed_dir, "faces")
    Path(faces_dir).mkdir(parents=True, exist_ok=True)
    return faces_dir


def detect_and_encode_faces(image_bgr: np.ndarray) -> list[dict]:
    """Detect faces and extract 128-dim embeddings. Returns list with bbox and embedding."""
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb, model="hog")
    if not locations:
        return []
    encodings = face_recognition.face_encodings(rgb, locations)
    results = []
    for (top, right, bottom, left), enc in zip(locations, encodings):
        results.append({
            "embedding": enc.tolist(),
            "bbox": (left, top, right - left, bottom - top),  # x, y, w, h
        })
    return results


def _crop_face(image_bgr: np.ndarray, bbox: tuple) -> np.ndarray:
    x, y, w, h = bbox
    pad = 20
    y1 = max(0, y - pad)
    y2 = min(image_bgr.shape[0], y + h + pad)
    x1 = max(0, x - pad)
    x2 = min(image_bgr.shape[1], x + w + pad)
    return image_bgr[y1:y2, x1:x2]


def save_face_crop(image_bgr: np.ndarray, bbox: tuple, reading_id: int, face_index: int) -> str:
    crop = _crop_face(image_bgr, bbox)
    faces_dir = _ensure_faces_dir()
    path = os.path.join(faces_dir, f"reading_{reading_id}_face_{face_index}.jpg")
    cv2.imwrite(path, crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return path


def save_face_crop_stream(image_bgr: np.ndarray, bbox: tuple) -> str:
    import uuid
    crop = _crop_face(image_bgr, bbox)
    faces_dir = _ensure_faces_dir()
    path = os.path.join(faces_dir, f"stream_{uuid.uuid4().hex[:12]}.jpg")
    cv2.imwrite(path, crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return path


def find_best_match(embedding: list[float], candidates: list[dict]) -> tuple[dict | None, float]:
    """Compare embedding against stored candidates. Returns best match and its distance."""
    if not candidates:
        return None, float("inf")
    enc = np.array(embedding)
    best, best_dist = None, float("inf")
    for c in candidates:
        stored = np.array(c["embedding"])
        dist = float(np.linalg.norm(enc - stored))
        if dist < best_dist:
            best_dist = dist
            best = c
    return best, best_dist
