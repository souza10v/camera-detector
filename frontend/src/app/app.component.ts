import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { UploadComponent } from './components/upload/upload.component';
import { ReadingsComponent } from './components/readings/readings.component';
import { CameraComponent } from './components/camera/camera.component';

type Tab = 'upload' | 'camera' | 'readings';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, UploadComponent, ReadingsComponent, CameraComponent],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent {
  activeTab: Tab = 'upload';
  refreshTrigger = 0;

  setTab(tab: Tab): void {
    this.activeTab = tab;
  }

  onUploadComplete(): void {
    this.refreshTrigger++;
  }
}
