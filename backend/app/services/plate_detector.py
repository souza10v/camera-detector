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


# Termos que DVRs/câmeras gravam como overlay na imagem e que o OCR
# pode confundir com placa. Comparação é feita após normalização (só A-Z0-9).
_OCR_BLOCKLIST: set[str] = {
    # Overlays genéricos de canal
    "CANAL", "CANAL1", "CANAL2", "CANAL3", "CANAL4",
    "CANAL5", "CANAL6", "CANAL7", "CANAL8",
    "CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8",
    "CAM1", "CAM2", "CAM3", "CAM4",
    "CAMERA1", "CAMERA2", "CAMERA3", "CAMERA4",
    # Marcas / fabricantes (incluindo variações por leitura errada do OCR)
    "INTELBRAS", "INTELBROS", "INTELBRАС", "INTELBRA",
    "HIKVISION", "HIKVISON", "HIKV",
    "DAHUA", "AXIS", "BOSCH",
    "HANWHA", "VIVOTEK", "UNIVIEW", "REOLINK", "FOSCAM",
    # Textos de data/hora e sistema comuns em DVRs
    "RECORD", "REC", "LIVE", "ALARM", "MOTION",
    "GRAVANDO", "GRAVACAO", "ENTRADA",
}


# Prefixos de marcas — qualquer texto que CONTENHA esses prefixos é bloqueado
# (cobre leituras parciais do OCR como "INTELB", "INTELBR", etc.)
_BRAND_PREFIXES: tuple[str, ...] = (
    "INTELB", "HIKVIS", "DAHUA", "HANWHA", "VIVOTE", "UNIVIE",
)


def _is_blocklisted(normalized: str) -> bool:
    """Retorna True se o texto normalizado está na blocklist ou contém um termo dela."""
    if normalized in _OCR_BLOCKLIST:
        return True
    # Rejeita textos que começam OU contêm prefixos de marcas conhecidas
    if any(normalized.startswith(p) or p in normalized for p in _BRAND_PREFIXES):
        return True
    # Rejeita se começa com qualquer termo da blocklist (ex: "CANAL1EXTRA")
    return any(normalized.startswith(term) for term in _OCR_BLOCKLIST)


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

    # Caracteres permitidos em placas brasileiras (allowlist melhora velocidade e precisão do OCR)
    _PLATE_ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    def _preprocess_roi(self, roi: np.ndarray) -> list[np.ndarray]:
        """Retorna múltiplas versões pré-processadas do ROI para maximizar detecção.

        Para ROIs pequenos (região de placa detectada), aplica upscale 2×.
        Para imagens grandes (frame completo), redimensiona para no máximo 720p
        para evitar travar o OCR.
        """
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if len(roi.shape) == 3 else roi.copy()
        h, w = gray.shape[:2]

        if h < 80 or w < 160:
            # ROI pequeno (placa detectada por cascade) — escala 2× para melhorar leitura
            gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        elif max(h, w) > 800:
            # Frame grande — limita dimensão máxima a 800 px para controlar memória do OCR.
            # 4 workers × EasyOCR em imagens muito grandes → OOM no container.
            # Placa de ~80px em 960px → ~67px em 800px: ainda legível com allowlist.
            scale = 800.0 / max(h, w)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # Versão 1: filtro bilateral + threshold Otsu (boa para alto contraste)
        bilateral = cv2.bilateralFilter(gray, 11, 17, 17)
        _, otsu = cv2.threshold(bilateral, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Versão 2: Otsu invertido (letras escuras em fundo claro)
        _, otsu_inv = cv2.threshold(bilateral, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Versão 3: threshold adaptativo (melhor para iluminação irregular)
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8
        )

        # Versão 4: CLAHE (melhora contraste em cenas escuras ou super-expostas)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        return [otsu, otsu_inv, adaptive, enhanced]

    def _ocr_roi(self, reader: easyocr.Reader, processed: np.ndarray) -> list[tuple]:
        """Executa OCR num ROI pré-processado com allowlist de placa."""
        return reader.readtext(
            processed,
            detail=1,
            allowlist=self._PLATE_ALLOWLIST,
            # Dicas de parágrafo: placas são texto horizontal em uma linha
            paragraph=False,
            width_ths=0.5,
        )

    def detect_plates(self, image: np.ndarray) -> list[dict]:
        reader = get_ocr_reader()
        results: list[dict] = []
        seen: set[str] = set()

        # ── Estratégia 1: Haar cascade para regiões de placa ──────────────────
        gray_full = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        cascade_hits = self._plate_cascade.detectMultiScale(
            gray_full, scaleFactor=1.1, minNeighbors=5, minSize=(60, 20)
        )

        rois: list[tuple[int, int, int, int, np.ndarray]] = []
        for (x, y, w, h) in cascade_hits:
            # Expande ligeiramente a ROI para não cortar bordas
            pad_x, pad_y = int(w * 0.05), int(h * 0.1)
            x1 = max(0, x - pad_x)
            y1 = max(0, y - pad_y)
            x2 = min(image.shape[1], x + w + pad_x)
            y2 = min(image.shape[0], y + h + pad_y)
            rois.append((x1, y1, x2 - x1, y2 - y1, image[y1:y2, x1:x2]))

        # ── Estratégia 2: frame completo como fallback ─────────────────────────
        full_image_fallback = not rois
        if full_image_fallback:
            rois = [(0, 0, image.shape[1], image.shape[0], image)]

        for (x, y, w, h, roi) in rois:
            versions = self._preprocess_roi(roi)

            # No fallback de imagem completa, tentamos as versões em ordem mas
            # paramos ao encontrar a primeira placa válida (desempenho no stream)
            for processed in versions:
                for (_, text, conf) in self._ocr_roi(reader, processed):
                    normalized = _normalize_plate(text)

                    # Requer exatamente 7 chars (formato de placa brasileiro)
                    if len(normalized) != 7:
                        continue
                    if conf < settings.ocr_confidence_threshold:
                        continue
                    if _is_blocklisted(normalized):
                        continue
                    if not _is_valid_plate(normalized):
                        continue
                    if normalized in seen:
                        continue

                    seen.add(normalized)
                    results.append({
                        "plate_text": normalized,
                        "confidence": float(conf),
                        "bbox": (x, y, w, h),
                        "valid_format": True,
                    })

                # Sai do loop de versões assim que encontrar pelo menos uma placa válida
                # (evita múltiplas chamadas OCR desnecessárias no fallback de frame completo)
                if results:
                    break

        # Ordena por confiança (melhor primeiro)
        results.sort(key=lambda r: r["confidence"], reverse=True)
        return results

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
