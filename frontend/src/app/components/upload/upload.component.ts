import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../services/api.service';
import { ProcessingResult } from '../../models/reading.model';

@Component({
  selector: 'app-upload',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './upload.component.html',
  styleUrls: ['./upload.component.css'],
})
export class UploadComponent {
  @Output() uploadComplete = new EventEmitter<void>();

  selectedFile: File | null = null;
  preview: string | null = null;
  loading = false;
  result: ProcessingResult | null = null;
  error: string | null = null;
  isDragging = false;

  constructor(private api: ApiService) {}

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files?.length) {
      this.setFile(input.files[0]);
    }
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = false;
    const file = event.dataTransfer?.files[0];
    if (file) this.setFile(file);
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = true;
  }

  onDragLeave(): void {
    this.isDragging = false;
  }

  private setFile(file: File): void {
    this.selectedFile = file;
    this.result = null;
    this.error = null;

    if (file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = e => this.preview = e.target?.result as string;
      reader.readAsDataURL(file);
    } else {
      this.preview = null;
    }
  }

  submit(): void {
    if (!this.selectedFile) return;
    this.loading = true;
    this.error = null;
    this.result = null;

    this.api.uploadFile(this.selectedFile).subscribe({
      next: res => {
        this.result = res;
        this.loading = false;
        this.uploadComplete.emit();
      },
      error: err => {
        this.error = err.error?.detail ?? 'Erro ao processar arquivo.';
        this.loading = false;
      },
    });
  }

  reset(): void {
    this.selectedFile = null;
    this.preview = null;
    this.result = null;
    this.error = null;
  }

  getImageUrl(url: string | null): string {
    return url ? this.api.getImageUrl(url) : '';
  }

  confidencePercent(conf: number | null): string {
    return conf != null ? `${(conf * 100).toFixed(1)}%` : '-';
  }
}
