import {
  Component, ElementRef, OnDestroy, ViewChild, AfterViewInit
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

type Mode = 'webcam' | 'rtsp';
type StreamStatus = 'idle' | 'connecting' | 'streaming' | 'error';

interface PlateAnnotation {
  text: string;
  confidence: number;
  bbox: [number, number, number, number];
}

interface FaceAnnotation {
  bbox: [number, number, number, number];
  face_id: number | null;
  label: string;
}

interface WebcamResult {
  plate_text: string | null;
  confidence: number | null;
  plates_detected: number;
  plates: PlateAnnotation[];
  faces: FaceAnnotation[];
}

interface RtspResult extends WebcamResult {
  frame_b64: string;
}

const WS_BASE = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/v1/ws`;

@Component({
  selector: 'app-camera',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './camera.component.html',
  styleUrls: ['./camera.component.css'],
})
export class CameraComponent implements AfterViewInit, OnDestroy {
  @ViewChild('videoEl')   videoElRef!: ElementRef<HTMLVideoElement>;
  @ViewChild('overlayEl') overlayElRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('captureEl') captureElRef!: ElementRef<HTMLCanvasElement>;

  mode: Mode = 'webcam';
  status: StreamStatus = 'idle';
  errorMessage = '';
  rtspUrl = '';

  currentRtspFrame = '';
  lastResult: WebcamResult | null = null;

  private ws: WebSocket | null = null;
  private mediaStream: MediaStream | null = null;
  private captureInterval: ReturnType<typeof setInterval> | null = null;

  ngAfterViewInit(): void {}
  ngOnDestroy(): void { this.stop(); }

  setMode(m: Mode): void {
    if (this.status !== 'idle') this.stop();
    this.mode = m;
    this.lastResult = null;
    this.currentRtspFrame = '';
  }

  async start(): Promise<void> {
    this.status = 'connecting';
    this.errorMessage = '';
    this.lastResult = null;
    this.currentRtspFrame = '';
    this.clearOverlay();

    if (this.mode === 'webcam') {
      await this.startWebcam();
    } else {
      this.startRtsp();
    }
  }

  stop(): void {
    this.captureInterval && clearInterval(this.captureInterval);
    this.captureInterval = null;

    if (this.ws) {
      if (this.mode === 'rtsp' && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'stop' }));
      }
      this.ws.close();
      this.ws = null;
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(t => t.stop());
      this.mediaStream = null;
    }

    this.clearOverlay();
    this.status = 'idle';
  }

  // ── Webcam ────────────────────────────────────────────────────────────────

  private async startWebcam(): Promise<void> {
    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      const video = this.videoElRef.nativeElement;
      video.srcObject = this.mediaStream;
      await video.play();
    } catch {
      this.setError('Não foi possível acessar a webcam. Verifique as permissões do navegador.');
      return;
    }

    this.ws = new WebSocket(`${WS_BASE}/webcam`);
    this.ws.onmessage = e => this.handleWebcamMessage(JSON.parse(e.data));
    this.ws.onerror = () => this.setError('Erro na conexão WebSocket.');
    this.ws.onclose = () => { if (this.status === 'streaming') this.stop(); };
    this.ws.onopen = () => {
      this.status = 'streaming';
      // Send a frame every 100ms — backend decides when to run OCR
      this.captureInterval = setInterval(() => this.captureAndSend(), 100);
    };
  }

  private captureAndSend(): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    const video = this.videoElRef.nativeElement;
    const capture = this.captureElRef.nativeElement;
    capture.width  = video.videoWidth  || 640;
    capture.height = video.videoHeight || 480;
    capture.getContext('2d')!.drawImage(video, 0, 0);
    const b64 = capture.toDataURL('image/jpeg', 0.5).split(',')[1];
    this.ws.send(JSON.stringify({ type: 'frame', data: b64 }));
  }

  private handleWebcamMessage(msg: { type: string } & Partial<WebcamResult> & { message?: string }): void {
    if (msg.type === 'result') {
      this.lastResult = msg as WebcamResult;
      this.drawOverlay(msg.plates ?? [], msg.faces ?? []);
    } else if (msg.type === 'error') {
      this.setError(msg.message ?? 'Erro desconhecido.');
    }
  }

  // ── RTSP ─────────────────────────────────────────────────────────────────

  private startRtsp(): void {
    if (!this.rtspUrl.trim()) {
      this.setError('Informe a URL do stream RTSP.');
      return;
    }

    this.ws = new WebSocket(`${WS_BASE}/rtsp`);
    this.ws.onmessage = e => this.handleRtspMessage(JSON.parse(e.data));
    this.ws.onerror = () => this.setError('Erro na conexão WebSocket.');
    this.ws.onclose = () => { if (this.status === 'streaming') this.stop(); };
    this.ws.onopen = () => {
      this.ws!.send(JSON.stringify({ type: 'start', url: this.rtspUrl.trim() }));
    };
  }

  private handleRtspMessage(msg: { type: string } & Partial<RtspResult> & { message?: string }): void {
    if (msg.type === 'connected') {
      this.status = 'streaming';
    } else if (msg.type === 'result') {
      this.currentRtspFrame = `data:image/jpeg;base64,${msg.frame_b64}`;
      this.lastResult = msg as WebcamResult;
      if (this.status !== 'streaming') this.status = 'streaming';
    } else if (msg.type === 'error') {
      this.setError(msg.message ?? 'Erro desconhecido.');
    }
  }

  // ── Canvas overlay ────────────────────────────────────────────────────────

  private drawOverlay(plates: PlateAnnotation[], faces: FaceAnnotation[]): void {
    const video   = this.videoElRef.nativeElement;
    const overlay = this.overlayElRef.nativeElement;
    overlay.width  = video.videoWidth  || 640;
    overlay.height = video.videoHeight || 480;
    const ctx = overlay.getContext('2d')!;
    ctx.clearRect(0, 0, overlay.width, overlay.height);

    // Plates — green
    for (const plate of plates) {
      const [x, y, w, h] = plate.bbox;
      ctx.strokeStyle = '#00e676';
      ctx.lineWidth = 3;
      ctx.strokeRect(x, y, w, h);

      const label = `${plate.text}  ${(plate.confidence * 100).toFixed(0)}%`;
      ctx.font = 'bold 15px monospace';
      const labelW = ctx.measureText(label).width + 12;
      const labelH = 24;
      const labelY = y > labelH ? y - labelH : y + h;
      ctx.fillStyle = 'rgba(0,0,0,0.72)';
      ctx.fillRect(x, labelY, labelW, labelH);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(label, x + 6, labelY + 16);
    }

    // Faces — orange (unknown) or blue (identified)
    for (const face of faces) {
      const [x, y, w, h] = face.bbox;
      const color = face.face_id !== null ? '#42a5f5' : '#ff9800';
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);

      ctx.font = 'bold 13px sans-serif';
      const labelW = ctx.measureText(face.label).width + 12;
      const labelH = 22;
      const labelY = y > labelH ? y - labelH : y + h;
      ctx.fillStyle = face.face_id !== null ? 'rgba(66,165,245,0.85)' : 'rgba(255,152,0,0.85)';
      ctx.fillRect(x, labelY, labelW, labelH);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(face.label, x + 6, labelY + 15);
    }
  }

  private clearOverlay(): void {
    try {
      const overlay = this.overlayElRef?.nativeElement;
      if (overlay) overlay.getContext('2d')?.clearRect(0, 0, overlay.width, overlay.height);
    } catch { /* not yet rendered */ }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  private setError(msg: string): void {
    this.errorMessage = msg;
    this.stop();
    this.status = 'error';
  }

  countIdentified(faces: FaceAnnotation[]): number {
    return faces.filter(f => f.face_id !== null).length;
  }

  confidencePercent(conf: number | null): string {
    return conf != null ? `${(conf * 100).toFixed(1)}%` : '—';
  }
}
