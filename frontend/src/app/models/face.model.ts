export interface FaceDetection {
  id: number;
  reading_id: number;
  unique_face_id: number;
  face_image_path: string | null;
  created_at: string;
}

export interface UniqueFace {
  id: number;
  representative_image_path: string | null;
  appearance_count: number;
  first_seen_at: string;
  last_seen_at: string;
}

export interface UniqueFaceDetail extends UniqueFace {
  detections: FaceDetection[];
}

export interface UniqueFaceList {
  total: number;
  items: UniqueFace[];
}
