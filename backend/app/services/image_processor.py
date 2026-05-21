import cv2
import numpy as np
import os
from pathlib import Path
from app.services.plate_detector import plate_detector
from app.services.face_recognition_service import detect_and_encode_faces, save_face_crop
from app.config import settings


class ImageProcessor:
    def process_image(self, image_path: str, reading_id: int) -> dict:
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Não foi possível ler a imagem: {image_path}")

        plates = plate_detector.detect_plates(image)
        annotated = plate_detector.annotate_image(image, plates)

        stem = Path(image_path).stem
        output_path = os.path.join(settings.processed_dir, f"{stem}_processed.jpg")
        cv2.imwrite(output_path, annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])

        if os.path.exists(image_path):
            os.remove(image_path)

        faces = detect_and_encode_faces(image)
        face_data = []
        for i, face in enumerate(faces):
            crop_path = save_face_crop(image, face["bbox"], reading_id, i)
            face_data.append({"embedding": face["embedding"], "crop_path": crop_path})

        best_plate = plates[0] if plates else None
        return {
            "plates": plates,
            "plate_text": best_plate["plate_text"] if best_plate else None,
            "confidence": best_plate["confidence"] if best_plate else None,
            "plates_detected": len(plates),
            "processed_image_path": output_path,
            "face_data": face_data,
        }

    def process_video(self, video_path: str, reading_id: int) -> dict:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Não foi possível abrir o vídeo: {video_path}")

        all_plates: list[dict] = []
        best_frame: np.ndarray | None = None
        best_confidence = 0.0
        best_frame_faces: list[dict] = []
        frame_number = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame_number += 1
                if frame_number % 10 != 0:
                    continue

                plates = plate_detector.detect_plates(frame)
                annotated = plate_detector.annotate_image(frame, plates)

                for plate in plates:
                    all_plates.append(plate)
                    if plate["confidence"] > best_confidence:
                        best_confidence = plate["confidence"]
                        best_frame = annotated.copy()
                        best_frame_faces = detect_and_encode_faces(frame)
        finally:
            cap.release()

        if os.path.exists(video_path):
            os.remove(video_path)

        output_path = None
        if best_frame is not None:
            stem = Path(video_path).stem
            output_path = os.path.join(settings.processed_dir, f"{stem}_best_frame.jpg")
            cv2.imwrite(output_path, best_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

        face_data = []
        if best_frame is not None:
            for i, face in enumerate(best_frame_faces):
                crop_path = save_face_crop(best_frame, face["bbox"], reading_id, i)
                face_data.append({"embedding": face["embedding"], "crop_path": crop_path})

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
            "processed_image_path": output_path,
            "face_data": face_data,
        }


image_processor = ImageProcessor()
