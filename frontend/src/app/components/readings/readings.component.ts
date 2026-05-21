import { Component, OnInit, Input, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';
import { PlateReading, PlateReadingList } from '../../models/reading.model';

@Component({
  selector: 'app-readings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './readings.component.html',
  styleUrls: ['./readings.component.css'],
})
export class ReadingsComponent implements OnInit, OnChanges {
  readonly Math = Math;
  @Input() refreshTrigger = 0;

  readings: PlateReading[] = [];
  total = 0;
  loading = false;
  error: string | null = null;

  searchQuery = '';
  currentPage = 0;
  pageSize = 10;

  selectedImage: string | null = null;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.load();
  }

  ngOnChanges(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    this.error = null;
    const skip = this.currentPage * this.pageSize;

    const obs = this.searchQuery.trim()
      ? this.api.searchByPlate(this.searchQuery.trim(), skip, this.pageSize)
      : this.api.listReadings(skip, this.pageSize);

    obs.subscribe({
      next: (res: PlateReadingList) => {
        this.readings = res.items;
        this.total = res.total;
        this.loading = false;
      },
      error: () => {
        this.error = 'Erro ao carregar leituras.';
        this.loading = false;
      },
    });
  }

  search(): void {
    this.currentPage = 0;
    this.load();
  }

  clearSearch(): void {
    this.searchQuery = '';
    this.currentPage = 0;
    this.load();
  }

  prevPage(): void {
    if (this.currentPage > 0) {
      this.currentPage--;
      this.load();
    }
  }

  nextPage(): void {
    if ((this.currentPage + 1) * this.pageSize < this.total) {
      this.currentPage++;
      this.load();
    }
  }

  get totalPages(): number {
    return Math.ceil(this.total / this.pageSize);
  }

  openImage(path: string | null): void {
    this.selectedImage = path ? this.api.getImageUrl(path) : null;
  }

  closeImage(): void {
    this.selectedImage = null;
  }

  confidencePercent(conf: number | null): string {
    return conf != null ? `${(conf * 100).toFixed(1)}%` : '-';
  }

  statusClass(status: string): string {
    const map: Record<string, string> = {
      completed: 'badge-success',
      failed: 'badge-danger',
      pending: 'badge-warning',
      processing: 'badge-info',
    };
    return map[status] ?? 'badge-info';
  }

  statusLabel(status: string): string {
    const map: Record<string, string> = {
      completed: 'Concluído',
      failed: 'Falhou',
      pending: 'Pendente',
      processing: 'Processando',
    };
    return map[status] ?? status;
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleString('pt-BR');
  }
}
