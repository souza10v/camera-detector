import cv2
import numpy as np
from app.config import settings


class FaceAnonymizer:
    def __init__(self):
        # Haar cascade for face detection — lightweight, no GPU required
        self._cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

    def detect_and_blur(self, image: np.ndarray) -> tuple[np.ndarray, int]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
        )

        result = image.copy()
        face_count = len(faces)

        for (x, y, w, h) in faces:
            # Add 20% padding around each face region
            pad_x = int(w * 0.2)
            pad_y = int(h * 0.2)
            x1 = max(0, x - pad_x)
            y1 = max(0, y - pad_y)
            x2 = min(image.shape[1], x + w + pad_x)
            y2 = min(image.shape[0], y + h + pad_y)

            roi = result[y1:y2, x1:x2]
            blur_k = settings.face_blur_intensity
            # Kernel must be odd
            if blur_k % 2 == 0:
                blur_k += 1
            blurred = cv2.GaussianBlur(roi, (blur_k, blur_k), 0)
            result[y1:y2, x1:x2] = blurred

        return result, face_count


face_anonymizer = FaceAnonymizer()
