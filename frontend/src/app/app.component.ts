import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { UploadComponent } from './components/upload/upload.component';
import { ReadingsComponent } from './components/readings/readings.component';
import { CameraComponent } from './components/camera/camera.component';
import { FacesComponent } from './components/faces/faces.component';
import { CameraListComponent, CameraEntry } from './components/camera-list/camera-list.component';

type Tab = 'upload' | 'cameras' | 'stream' | 'readings' | 'faces';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, UploadComponent, ReadingsComponent, CameraComponent, FacesComponent, CameraListComponent],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent {
  activeTab: Tab = 'upload';
  refreshTrigger = 0;

  // Câmera selecionada para visualização via cadastro
  selectedCameraUrl: string | null = null;
  selectedCameraLabel: string | null = null;

  setTab(tab: Tab): void {
    this.activeTab = tab;
    if (tab !== 'stream') {
      this.selectedCameraUrl = null;
    }
  }

  onUploadComplete(): void {
    this.refreshTrigger++;
  }

  onViewCamera(cam: CameraEntry): void {
    this.selectedCameraUrl = cam.url;
    this.selectedCameraLabel = cam.name;
    this.activeTab = 'stream';
  }
}
