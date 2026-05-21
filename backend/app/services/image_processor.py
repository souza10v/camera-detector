import cv2
import numpy as np
import os
from pathlib import Path
from app.services.face_anonymizer import face_anonymizer
from app.services.plate_detector import plate_detector
from app.config import settings


class ImageProcessor:
    def process_image(self, image_path: str) -> dict:
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Não foi possível ler a imagem: {image_path}")

        # 1. Detect plates first
        plates = plate_detector.detect_plates(image)

        # 2. Annotate plate regions on image
        annotated = plate_detector.annotate_image(image, plates)

        # 3. Blur faces — original image never stored with faces visible
        anonymized, face_count = face_anonymizer.detect_and_blur(annotated)

        # 4. Save processed image
        stem = Path(image_path).stem
        output_path = os.path.join(settings.processed_dir, f"{stem}_processed.jpg")
        cv2.imwrite(output_path, anonymized, [cv2.IMWRITE_JPEG_QUALITY, 90])

        # Remove the raw upload — never keep originals
        if os.path.exists(image_path):
            os.remove(image_path)

        best_plate = plates[0] if plates else None
        return {
            "plates": plates,
            "plate_text": best_plate["plate_text"] if best_plate else None,
            "confidence": best_plate["confidence"] if best_plate else None,
            "plates_detected": len(plates),
            "faces_detected": face_count,
            "processed_image_path": output_path,
        }

    def process_video(self, video_path: str) -> dict:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Não foi possível abrir o vídeo: {video_path}")

        all_plates: list[dict] = []
        total_faces = 0
        best_frame: np.ndarray | None = None
        best_confidence = 0.0
        frame_number = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_number += 1
                # Process every 10th frame for performance
                if frame_number % 10 != 0:
                    continue

                plates = plate_detector.detect_plates(frame)
                annotated = plate_detector.annotate_image(frame, plates)
                anonymized, face_count = face_anonymizer.detect_and_blur(annotated)
                total_faces += face_count

                for plate in plates:
                    all_plates.append(plate)
                    if plate["confidence"] > best_confidence:
                        best_confidence = plate["confidence"]
                        best_frame = anonymized.copy()
        finally:
            cap.release()

        if os.path.exists(video_path):
            os.remove(video_path)

        output_path = None
        if best_frame is not None:
            stem = Path(video_path).stem
            output_path = os.path.join(settings.processed_dir, f"{stem}_best_frame.jpg")
            cv2.imwrite(output_path, best_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

        # Deduplicate and pick best plate
        seen: set[str] = set()
        unique_plates: list[dict] = []
        for p in sorted(all_plates, key=lambda x: x["confidence"], reverse=True):
            if p["plate_text"] not in seen:
                seen.add(p["plate_text"])
                unique_plates.append(p)

        best_plate = unique_plates[0] if unique_plates else None
        return {
            "plates": unique_plates,
            "plate_text": best_plate["plate_text"] if best_plate else None,
            "confidence": best_plate["confidence"] if best_plate else None,
            "plates_detected": len(unique_plates),
            "faces_detected": total_faces,
            "processed_image_path": output_path,
        }


image_processor = ImageProcessor()
