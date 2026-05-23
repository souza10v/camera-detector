import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { PlateReadingList, ProcessingResult } from '../models/reading.model';
import { UniqueFaceList, UniqueFaceDetail } from '../models/face.model';

const API_BASE = '/api/v1';

@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private http: HttpClient) {}

  uploadFile(file: File): Observable<ProcessingResult> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<ProcessingResult>(`${API_BASE}/upload/`, form);
  }

  listReadings(skip = 0, limit = 20): Observable<PlateReadingList> {
    const params = new HttpParams().set('skip', skip).set('limit', limit);
    return this.http.get<PlateReadingList>(`${API_BASE}/readings/`, { params });
  }

  searchByPlate(plate: string, skip = 0, limit = 20): Observable<PlateReadingList> {
    const params = new HttpParams().set('plate', plate).set('skip', skip).set('limit', limit);
    return this.http.get<PlateReadingList>(`${API_BASE}/readings/search`, { params });
  }

  listFaces(skip = 0, limit = 20): Observable<UniqueFaceList> {
    const params = new HttpParams().set('skip', skip).set('limit', limit);
    return this.http.get<UniqueFaceList>(`${API_BASE}/faces/`, { params });
  }

  getFace(faceId: number): Observable<UniqueFaceDetail> {
    return this.http.get<UniqueFaceDetail>(`${API_BASE}/faces/${faceId}`);
  }

  deleteFace(faceId: number): Observable<void> {
    return this.http.delete<void>(`${API_BASE}/faces/${faceId}`);
  }

  getImageUrl(path: string): string {
    return path.startsWith('/images') ? path : `/images/${path}`;
  }

  getFaceImageUrl(path: string | null): string {
    if (!path) return '';
    const filename = path.split('/').slice(-2).join('/'); // faces/filename.jpg
    return `/images/${filename}`;
  }
}
