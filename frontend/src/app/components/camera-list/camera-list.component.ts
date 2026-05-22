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
  // estado local (não vem do backend)
  online?: boolean | null;   // null = não verificado, true/false = resultado do ping
  pinging?: boolean;
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

  private pingInterval: ReturnType<typeof setInterval> | null = null;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.load();
    // Verifica status de todas as câmeras a cada 30s
    this.pingInterval = setInterval(() => this.pingAll(), 30_000);
  }

  ngOnDestroy(): void {
    if (this.pingInterval) clearInterval(this.pingInterval);
  }

  load(): void {
    this.loading = true;
    this.http.get<CameraEntry[]>('/api/v1/cameras/').subscribe({
      next: (cams: any[]) => {
        this.cameras = cams.map(c => ({ ...c, online: null, pinging: false }));
        this.loading = false;
        this.pingAll();
      },
      error: () => { this.loading = false; },
    });
  }

  pingAll(): void {
    this.cameras.forEach(c => this.ping(c));
  }

  ping(cam: CameraEntry): void {
    cam.pinging = true;
    this.http.get<{ online: boolean }>(`/api/v1/cameras/${cam.id}/ping`).subscribe({
      next: r => { cam.online = r.online; cam.pinging = false; },
      error: ()  => { cam.online = false;  cam.pinging = false; },
    });
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
      error: ()  => { this.saving = false; },
    });
  }

  delete(cam: CameraEntry): void {
    if (!confirm(`Remover "${cam.name}"?`)) return;
    this.http.delete(`/api/v1/cameras/${cam.id}`).subscribe(() => this.load());
  }

  view(cam: CameraEntry): void {
    this.viewCamera.emit(cam);
  }
}
