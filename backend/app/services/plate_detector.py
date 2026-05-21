import cv2
import numpy as np
import easyocr
import re
from typing import Optional
from app.config import settings


_reader: Optional[easyocr.Reader] = None


def get_ocr_reader() -> easyocr.Reader:
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(["en", "pt"], gpu=False)
    return _reader


def _normalize_plate(text: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
    return cleaned


def _is_valid_plate(text: str) -> bool:
    # Brazilian plate formats: ABC1234 (old) or ABC1D23 (Mercosul)
    old = re.match(r"^[A-Z]{3}\d{4}$", text)
    mercosul = re.match(r"^[A-Z]{3}\d[A-Z]\d{2}$", text)
    return bool(old or mercosul)


class PlateDetector:
    def __init__(self):
        # Haar cascade for license plates as a fast pre-filter
        self._plate_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_russian_plate_number.xml"
        )

    def _preprocess_roi(self, roi: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh

    def detect_plates(self, image: np.ndarray) -> list[dict]:
        reader = get_ocr_reader()
        results = []

        # Strategy 1: Haar cascade detects plate regions
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        plates = self._plate_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

        rois = []
        for (x, y, w, h) in plates:
            rois.append((x, y, w, h, image[y:y+h, x:x+w]))

        # Strategy 2: run OCR on the full image if no ROIs found
        if not rois:
            rois = [(0, 0, image.shape[1], image.shape[0], image)]

        for (x, y, w, h, roi) in rois:
            processed = self._preprocess_roi(roi)
            ocr_results = reader.readtext(processed, detail=1)

            for (_, text, conf) in ocr_results:
                normalized = _normalize_plate(text)
                if len(normalized) >= 5 and conf >= settings.ocr_confidence_threshold:
                    valid = _is_valid_plate(normalized)
                    results.append({
                        "plate_text": normalized,
                        "confidence": float(conf),
                        "bbox": (x, y, w, h),
                        "valid_format": valid,
                    })

        # Sort by confidence and deduplicate
        results.sort(key=lambda r: r["confidence"], reverse=True)
        seen = set()
        unique = []
        for r in results:
            if r["plate_text"] not in seen:
                seen.add(r["plate_text"])
                unique.append(r)

        return unique

    def annotate_image(self, image: np.ndarray, plates: list[dict]) -> np.ndarray:
        annotated = image.copy()
        for plate in plates:
            x, y, w, h = plate["bbox"]
            color = (0, 255, 0) if plate["valid_format"] else (0, 165, 255)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
            label = f"{plate['plate_text']} ({plate['confidence']:.0%})"
            cv2.putText(
                annotated, label, (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2
            )
        return annotated


plate_detector = PlateDetector()
