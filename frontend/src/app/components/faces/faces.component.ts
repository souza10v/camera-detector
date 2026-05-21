import { Component, OnInit, Input, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../services/api.service';
import { UniqueFace, UniqueFaceDetail, UniqueFaceList } from '../../models/face.model';

@Component({
  selector: 'app-faces',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './faces.component.html',
  styleUrls: ['./faces.component.css'],
})
export class FacesComponent implements OnInit, OnChanges {
  @Input() refreshTrigger = 0;

  faces: UniqueFace[] = [];
  total = 0;
  loading = false;
  error: string | null = null;

  currentPage = 0;
  pageSize = 12;

  selected: UniqueFaceDetail | null = null;
  loadingDetail = false;

  readonly Math = Math;

  constructor(private api: ApiService) {}

  ngOnInit(): void { this.load(); }
  ngOnChanges(): void { this.load(); }

  load(): void {
    this.loading = true;
    this.error = null;
    const skip = this.currentPage * this.pageSize;
    this.api.listFaces(skip, this.pageSize).subscribe({
      next: (res: UniqueFaceList) => {
        this.faces = res.items;
        this.total = res.total;
        this.loading = false;
      },
      error: () => {
        this.error = 'Erro ao carregar rostos.';
        this.loading = false;
      },
    });
  }

  openDetail(face: UniqueFace): void {
    this.loadingDetail = true;
    this.api.getFace(face.id).subscribe({
      next: detail => {
        this.selected = detail;
        this.loadingDetail = false;
      },
      error: () => { this.loadingDetail = false; },
    });
  }

  closeDetail(): void { this.selected = null; }

  prevPage(): void {
    if (this.currentPage > 0) { this.currentPage--; this.load(); }
  }

  nextPage(): void {
    if ((this.currentPage + 1) * this.pageSize < this.total) { this.currentPage++; this.load(); }
  }

  get totalPages(): number { return Math.ceil(this.total / this.pageSize); }

  faceImageUrl(path: string | null): string {
    return path ? this.api.getFaceImageUrl(path) : '';
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleString('pt-BR');
  }
}
