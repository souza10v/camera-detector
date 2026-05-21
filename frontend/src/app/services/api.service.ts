import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { PlateReadingList, ProcessingResult } from '../models/reading.model';

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

  getImageUrl(path: string): string {
    return path.startsWith('/images') ? path : `/images/${path}`;
  }
}
