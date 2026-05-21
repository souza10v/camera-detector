export type ProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface PlateReading {
  id: number;
  plate_text: string | null;
  confidence: number | null;
  processed_image_path: string | null;
  original_filename: string;
  file_type: string;
  status: ProcessingStatus;
  error_message: string | null;
  faces_detected: number;
  plates_detected: number;
  created_at: string;
  updated_at: string;
}

export interface PlateReadingList {
  total: number;
  items: PlateReading[];
}

export interface ProcessingResult {
  reading_id: number;
  plate_text: string | null;
  confidence: number | null;
  faces_detected: number;
  plates_detected: number;
  processed_image_url: string | null;
  status: ProcessingStatus;
  message: string;
}
