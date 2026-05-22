import { Component, OnInit, OnDestroy, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

export interface CameraEntry {
  id: number;
  name: string;
  url: string;
  description: string | null;
  enabled: boolean;
  // estado local
  online?: boolean | null;
  pinging?: boolean;
  workerStatus?: 'running' | 'starting' | 'stopped' | 'unknown';
}

@Component({
  selector: 'app-camera-list',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './camera-list.component.html',
  styleUrls: ['./camera-list.component.css'],
})
export class CameraListComponent implements OnInit, OnDestroy {
  @Output() viewCamera = new EventEmitter<CameraEntry>();

  cameras: CameraEntry[] = [];
  loading = false;

  showForm = false;
  editingId: number | null = null;
  form = { name: '', url: '', description: '', enabled: true };
  saving = false;

  private pollInterval: ReturnType<typeof setInterval> | null = null;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.load();
    // Atualiza status a cada 20s
    this.pollInterval = setInterval(() => this.refreshStatus(), 20_000);
  }

  ngOnDestroy(): void {
    if (this.pollInterval) clearInterval(this.pollInterval);
  }

  load(): void {
    this.loading = true;
    this.http.get<CameraEntry[]>('/api/v1/cameras/').subscribe({
      next: (cams: any[]) => {
        this.cameras = cams.map(c => ({ ...c, online: null, pinging: false, workerStatus: 'unknown' }));
        this.loading = false;
        this.refreshStatus();
      },
      error: () => { this.loading = false; },
    });
  }

  refreshStatus(): void {
    this.cameras.forEach(c => {
      this.ping(c);
      this.fetchWorkerStatus(c);
    });
  }

  ping(cam: CameraEntry): void {
    cam.pinging = true;
    this.http.get<{ online: boolean }>(`/api/v1/cameras/${cam.id}/ping`).subscribe({
      next: r => { cam.online = r.online; cam.pinging = false; },
      error: ()  => { cam.online = false;  cam.pinging = false; },
    });
  }

  fetchWorkerStatus(cam: CameraEntry): void {
    this.http.get<{ status: string }>(`/api/v1/cameras/${cam.id}/worker-status`).subscribe({
      next: r => { cam.workerStatus = r.status as any; },
      error: ()  => { cam.workerStatus = 'unknown'; },
    });
  }

  startWorker(cam: CameraEntry): void {
    cam.workerStatus = 'starting';
    this.http.post<any>(`/api/v1/cameras/${cam.id}/start`, {}).subscribe({
      next: () => { setTimeout(() => this.fetchWorkerStatus(cam), 2000); },
      error: (err) => {
        cam.workerStatus = 'stopped';
        const msg = err?.error?.detail ?? 'Erro ao iniciar processamento.';
        alert(msg);
      },
    });
  }

  stopWorker(cam: CameraEntry): void {
    cam.workerStatus = 'stopped';
    this.http.post(`/api/v1/cameras/${cam.id}/stop`, {}).subscribe();
  }

  openForm(cam?: CameraEntry): void {
    if (cam) {
      this.editingId = cam.id;
      this.form = { name: cam.name, url: cam.url, description: cam.description ?? '', enabled: cam.enabled };
    } else {
      this.editingId = null;
      this.form = { name: '', url: '', description: '', enabled: true };
    }
    this.showForm = true;
  }

  closeForm(): void { this.showForm = false; }

  save(): void {
    if (!this.form.name.trim() || !this.form.url.trim()) return;
    this.saving = true;
    const body = { ...this.form };
    const req = this.editingId
      ? this.http.put<CameraEntry>(`/api/v1/cameras/${this.editingId}`, body)
      : this.http.post<CameraEntry>('/api/v1/cameras/', body);
    req.subscribe({
      next: () => { this.saving = false; this.showForm = false; this.load(); },
      error: (err) => {
        this.saving = false;
        const msg = err?.error?.detail ?? 'Erro ao salvar câmera.';
        alert(msg);
      },
    });
  }

  delete(cam: CameraEntry): void {
    if (!confirm(`Remover "${cam.name}"?`)) return;
    this.http.delete(`/api/v1/cameras/${cam.id}`).subscribe(() => this.load());
  }

  view(cam: CameraEntry): void {
    this.viewCamera.emit(cam);
  }

  workerLabel(s: string | undefined): string {
    return ({ running: 'Processando', starting: 'Iniciando…', stopped: 'Parado', unknown: '—' } as any)[s ?? 'unknown'] ?? '—';
  }
}
