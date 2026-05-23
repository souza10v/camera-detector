import {
  Component, ElementRef, OnDestroy, ViewChild, AfterViewInit, Input, OnChanges, SimpleChanges
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

interface StreamResult {
  plate_text: string | null;
  confidence: number | null;
  plates_detected: number;
  plates: PlateAnnotation[];
  faces: FaceAnnotation[];
  frame_b64?: string;
}

// Uma entrada de câmera RTSP gerenciada independentemente
interface RtspCamera {
  id: string;
  url: string;
  label: string;
  status: StreamStatus;
  errorMessage: string;
  currentFrame: string;
  lastResult: StreamResult | null;
  ws: WebSocket | null;
}

const WS_BASE = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/v1/ws`;

@Component({
  selector: 'app-camera',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './camera.component.html',
  styleUrls: ['./camera.component.css'],
})
export class CameraComponent implements AfterViewInit, OnDestroy, OnChanges {
  @ViewChild('videoEl')   videoElRef!: ElementRef<HTMLVideoElement>;
  @ViewChild('overlayEl') overlayElRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('captureEl') captureElRef!: ElementRef<HTMLCanvasElement>;

  // Quando uma câmera é selecionada no cadastro, esses inputs são preenchidos
  @Input() presetRtspUrl: string | null = null;
  @Input() presetRtspLabel: string | null = null;

  mode: Mode = 'webcam';

  // ── Webcam state ──────────────────────────────────────────────────────────
  webcamStatus: StreamStatus = 'idle';
  webcamError = '';
  webcamResult: StreamResult | null = null;
  private webcamWs: WebSocket | null = null;
  private mediaStream: MediaStream | null = null;
  private captureInterval: ReturnType<typeof setInterval> | null = null;

  // ── RTSP multi-camera state ───────────────────────────────────────────────
  cameras: RtspCamera[] = [];
  newUrl = '';
  newLabel = '';

  ngAfterViewInit(): void {}

  ngOnDestroy(): void {
    this.stopWebcam();
    this.cameras.forEach(c => this.disconnectCamera(c));
  }

  ngOnChanges(changes: SimpleChanges): void {
    // Quando o app seleciona uma câmera do cadastro, muda para RTSP e adiciona automaticamente
    if (changes['presetRtspUrl'] && this.presetRtspUrl) {
      this.mode = 'rtsp';
      // Evita duplicatas — remove câmera com a mesma URL se já existir
      this.cameras = this.cameras.filter(c => c.url !== this.presetRtspUrl);
      const cam: RtspCamera = {
        id: crypto.randomUUID(),
        url: this.presetRtspUrl,
        label: this.presetRtspLabel ?? this.presetRtspUrl,
        status: 'connecting',
        errorMessage: '',
        currentFrame: '',
        lastResult: null,
        ws: null,
      };
      this.cameras.push(cam);
      this.connectCamera(cam);
    }
  }

  setMode(m: Mode): void {
    if (m === 'webcam' && this.mode !== 'webcam') {
      this.cameras.forEach(c => this.disconnectCamera(c));
    }
    if (m === 'rtsp' && this.mode !== 'rtsp') {
      this.stopWebcam();
    }
    this.mode = m;
  }

  // ── Webcam ────────────────────────────────────────────────────────────────

  async startWebcam(): Promise<void> {
    this.webcamStatus = 'connecting';
    this.webcamError = '';
    this.webcamResult = null;
    this.clearOverlay();

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      const video = this.videoElRef.nativeElement;
      video.srcObject = this.mediaStream;
      await video.play();
    } catch {
      this.webcamStatus = 'error';
      this.webcamError = 'Não foi possível acessar a webcam. Verifique as permissões.';
      return;
    }

    this.webcamWs = new WebSocket(`${WS_BASE}/webcam`);
    this.webcamWs.onmessage = e => this.handleWebcamMessage(JSON.parse(e.data));
    this.webcamWs.onerror = () => {
      this.webcamStatus = 'error';
      this.webcamError = 'Erro na conexão WebSocket.';
    };
    this.webcamWs.onclose = () => {
      if (this.webcamStatus === 'streaming') this.stopWebcam();
    };
    this.webcamWs.onopen = () => {
      this.webcamStatus = 'streaming';
      this.captureInterval = setInterval(() => this.captureAndSend(), 100);
    };
  }

  stopWebcam(): void {
    this.captureInterval && clearInterval(this.captureInterval);
    this.captureInterval = null;
    this.webcamWs?.close();
    this.webcamWs = null;
    this.mediaStream?.getTracks().forEach(t => t.stop());
    this.mediaStream = null;
    this.clearOverlay();
    this.webcamStatus = 'idle';
  }

  private captureAndSend(): void {
    if (!this.webcamWs || this.webcamWs.readyState !== WebSocket.OPEN) return;
    const video   = this.videoElRef.nativeElement;
    const capture = this.captureElRef.nativeElement;
    capture.width  = video.videoWidth  || 640;
    capture.height = video.videoHeight || 480;
    capture.getContext('2d')!.drawImage(video, 0, 0);
    const b64 = capture.toDataURL('image/jpeg', 0.8).split(',')[1];
    this.webcamWs.send(JSON.stringify({ type: 'frame', data: b64 }));
  }

  private handleWebcamMessage(msg: { type: string } & Partial<StreamResult> & { message?: string }): void {
    if (msg.type === 'result') {
      this.webcamResult = msg as StreamResult;
      this.drawOverlay(msg.plates ?? [], msg.faces ?? []);
    } else if (msg.type === 'error') {
      this.webcamStatus = 'error';
      this.webcamError = msg.message ?? 'Erro desconhecido.';
    }
  }

  // ── RTSP multi-camera ─────────────────────────────────────────────────────

  addCamera(): void {
    const url = this.newUrl.trim();
    if (!url) return;

    const cam: RtspCamera = {
      id: crypto.randomUUID(),
      url,
      label: this.newLabel.trim() || `Câmera ${this.cameras.length + 1}`,
      status: 'connecting',
      errorMessage: '',
      currentFrame: '',
      lastResult: null,
      ws: null,
    };

    this.cameras.push(cam);
    this.newUrl = '';
    this.newLabel = '';
    this.connectCamera(cam);
  }

  removeCamera(cam: RtspCamera): void {
    this.disconnectCamera(cam);
    this.cameras = this.cameras.filter(c => c.id !== cam.id);
  }

  private connectCamera(cam: RtspCamera): void {
    const ws = new WebSocket(`${WS_BASE}/rtsp`);
    cam.ws = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'start', url: cam.url }));
    };

    ws.onmessage = e => {
      const msg = JSON.parse(e.data) as { type: string } & Partial<StreamResult> & { message?: string };
      if (msg.type === 'connected') {
        cam.status = 'streaming';
      } else if (msg.type === 'result') {
        cam.currentFrame = `data:image/jpeg;base64,${msg.frame_b64}`;
        cam.lastResult = msg as StreamResult;
        if (cam.status !== 'streaming') cam.status = 'streaming';
      } else if (msg.type === 'error') {
        cam.status = 'error';
        cam.errorMessage = msg.message ?? 'Erro desconhecido.';
        cam.ws = null;
      }
    };

    ws.onerror = () => {
      cam.status = 'error';
      cam.errorMessage = 'Erro na conexão WebSocket.';
      cam.ws = null;
    };

    ws.onclose = () => {
      if (cam.status === 'streaming') {
        cam.status = 'error';
        cam.errorMessage = 'Conexão encerrada.';
      }
      cam.ws = null;
    };
  }

  reconnectCamera(cam: RtspCamera): void {
    this.disconnectCamera(cam);
    cam.status = 'connecting';
    cam.errorMessage = '';
    cam.currentFrame = '';
    cam.lastResult = null;
    this.connectCamera(cam);
  }

  private disconnectCamera(cam: RtspCamera): void {
    if (cam.ws) {
      if (cam.ws.readyState === WebSocket.OPEN) {
        cam.ws.send(JSON.stringify({ type: 'stop' }));
      }
      cam.ws.close();
      cam.ws = null;
    }
    cam.status = 'idle';
  }

  stopAllCameras(): void {
    this.cameras.forEach(c => this.disconnectCamera(c));
  }

  anyStreaming(): boolean {
    return this.cameras.some(c => c.status === 'streaming' || c.status === 'connecting');
  }

  // ── Canvas overlay (webcam only) ──────────────────────────────────────────

  private drawOverlay(plates: PlateAnnotation[], faces: FaceAnnotation[]): void {
    const video   = this.videoElRef?.nativeElement;
    const overlay = this.overlayElRef?.nativeElement;
    if (!video || !overlay) return;
    overlay.width  = video.videoWidth  || 640;
    overlay.height = video.videoHeight || 480;
    const ctx = overlay.getContext('2d')!;
    ctx.clearRect(0, 0, overlay.width, overlay.height);

    for (const plate of plates) {
      const [x, y, w, h] = plate.bbox;
      ctx.strokeStyle = '#00e676';
      ctx.lineWidth = 3;
      ctx.strokeRect(x, y, w, h);
      const label = `${plate.text}  ${(plate.confidence * 100).toFixed(0)}%`;
      ctx.font = 'bold 15px monospace';
      const lw = ctx.measureText(label).width + 12;
      const ly = y > 24 ? y - 24 : y + h;
      ctx.fillStyle = 'rgba(0,0,0,0.72)';
      ctx.fillRect(x, ly, lw, 24);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(label, x + 6, ly + 16);
    }

    for (const face of faces) {
      const [x, y, w, h] = face.bbox;
      const color = face.face_id !== null ? '#42a5f5' : '#ff9800';
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);
      ctx.font = 'bold 13px sans-serif';
      const lw = ctx.measureText(face.label).width + 12;
      const ly = y > 22 ? y - 22 : y + h;
      ctx.fillStyle = face.face_id !== null ? 'rgba(66,165,245,0.85)' : 'rgba(255,152,0,0.85)';
      ctx.fillRect(x, ly, lw, 22);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(face.label, x + 6, ly + 15);
    }
  }

  private clearOverlay(): void {
    try {
      const overlay = this.overlayElRef?.nativeElement;
      if (overlay) overlay.getContext('2d')?.clearRect(0, 0, overlay.width, overlay.height);
    } catch { /* not yet rendered */ }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  statusLabel(s: StreamStatus): string {
    return { idle: 'Inativo', connecting: 'Conectando…', streaming: 'Transmitindo', error: 'Erro' }[s];
  }

  confidencePercent(conf: number | null): string {
    return conf != null ? `${(conf * 100).toFixed(1)}%` : '—';
  }

  countIdentified(faces: FaceAnnotation[]): number {
    return faces.filter(f => f.face_id !== null).length;
  }
}
