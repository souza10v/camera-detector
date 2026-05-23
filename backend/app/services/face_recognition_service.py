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


def detect_and_encode_faces(image_bgr: np.ndarray, min_face_px: int = 50) -> list[dict]:
    """Detect faces and extract 128-dim embeddings.

    Aplica dois filtros para reduzir falsos positivos (rodas, placas redondas, etc.):
    1. Tamanho mínimo: faces menores que min_face_px × min_face_px são descartadas.
    2. Landmarks: valida que os olhos estão em posição plausível dentro do bbox.
       Detectores HOG às vezes retornam rodas / objetos circulares como "faces";
       os landmarks do dlib raramente encontram olhos nessas regiões.
    """
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

    # Reduz imagens muito grandes para acelerar detecção (escala bbox de volta depois)
    h, w = rgb.shape[:2]
    max_dim = max(h, w)
    scale = 1.0
    if max_dim > 1280:
        scale = 1280 / max_dim
        rgb_small = cv2.resize(rgb, (int(w * scale), int(h * scale)))
    else:
        rgb_small = rgb

    locations_small = face_recognition.face_locations(rgb_small, model="hog", number_of_times_to_upsample=1)
    if not locations_small:
        return []

    # Escala de volta para coordenadas da imagem original
    if scale != 1.0:
        locations = [
            (int(top / scale), int(right / scale), int(bottom / scale), int(left / scale))
            for (top, right, bottom, left) in locations_small
        ]
    else:
        locations = locations_small

    # ── Filtro 1: tamanho mínimo ──────────────────────────────────────────────
    locations = [
        loc for loc in locations
        if (loc[2] - loc[0]) >= min_face_px and (loc[1] - loc[3]) >= min_face_px
    ]
    if not locations:
        return []

    # ── Filtro 2: landmarks — valida estrutura facial completa ───────────────
    # face_landmarks retorna dict com olhos, nariz, boca, etc.
    # Rodas / objetos circulares não têm olhos + nariz + boca em posição coerente.
    landmark_results = face_recognition.face_landmarks(rgb, locations)
    valid_locations = []
    for loc, lm in zip(locations, landmark_results):
        if not lm:
            continue
        left_eye  = lm.get("left_eye",  [])
        right_eye = lm.get("right_eye", [])
        nose_tip  = lm.get("nose_tip",  [])
        top_lip   = lm.get("top_lip",   [])
        # Todos os marcos principais devem existir
        if not left_eye or not right_eye or not nose_tip or not top_lip:
            continue

        face_top, face_right, face_bottom, face_left = loc
        face_h = max(face_bottom - face_top, 1)
        face_w = max(face_right  - face_left, 1)

        le_y   = sum(p[1] for p in left_eye)  / len(left_eye)
        re_y   = sum(p[1] for p in right_eye) / len(right_eye)
        avg_eye_y  = (le_y + re_y) / 2
        nose_y     = sum(p[1] for p in nose_tip) / len(nose_tip)
        lip_y      = sum(p[1] for p in top_lip)  / len(top_lip)

        # Verificação 1 — olhos no terço superior da face (top 55 %)
        if avg_eye_y > face_top + face_h * 0.55:
            continue

        # Verificação 2 — nariz ABAIXO dos olhos e ACIMA da boca
        # Em uma roda, essa sequência vertical raramente se mantém
        if not (avg_eye_y < nose_y < lip_y):
            continue

        # Verificação 3 — nariz dentro dos ⅔ centrais verticais da face
        if nose_y < face_top + face_h * 0.30 or nose_y > face_top + face_h * 0.80:
            continue

        # Verificação 4 — separação horizontal dos olhos: 25–80 % da largura
        le_x  = sum(p[0] for p in left_eye)  / len(left_eye)
        re_x  = sum(p[0] for p in right_eye) / len(right_eye)
        eye_sep = abs(re_x - le_x)
        if eye_sep < face_w * 0.25 or eye_sep > face_w * 0.80:
            continue

        valid_locations.append(loc)

    if not valid_locations:
        return []

    encodings = face_recognition.face_encodings(rgb, valid_locations)
    results = []
    for (top, right, bottom, left), enc in zip(valid_locations, encodings):
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
