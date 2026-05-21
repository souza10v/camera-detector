import { Component } from '@angular/core';
import { UploadComponent } from './components/upload/upload.component';
import { ReadingsComponent } from './components/readings/readings.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [UploadComponent, ReadingsComponent],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent {
  refreshTrigger = 0;

  onUploadComplete(): void {
    this.refreshTrigger++;
  }
}
