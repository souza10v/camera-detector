import {
  Component, ElementRef, OnDestroy, ViewChild, AfterViewInit
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

type Mode = 'webcam' | 'rtsp';
type StreamStatus = 'idle' | 'connecting' | 'streaming' | 'error';

interface StreamResult {
  frame_b64: string;
  plate_text: string | null;
  confidence: number | null;
  plates_detected: number;
  faces_detected: number;
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
  @ViewChild('videoEl') videoElRef!: ElementRef<HTMLVideoElement>;
  @ViewChild('canvasEl') canvasElRef!: ElementRef<HTMLCanvasElement>;

  mode: Mode = 'webcam';
  status: StreamStatus = 'idle';
  errorMessage = '';
  rtspUrl = '';

  currentFrame = '';
  lastResult: StreamResult | null = null;

  private ws: WebSocket | null = null;
  private mediaStream: MediaStream | null = null;
  private captureInterval: ReturnType<typeof setInterval> | null = null;

  ngAfterViewInit(): void {}

  ngOnDestroy(): void {
    this.stop();
  }

  setMode(m: Mode): void {
    if (this.status !== 'idle') this.stop();
    this.mode = m;
  }

  async start(): Promise<void> {
    this.status = 'connecting';
    this.errorMessage = '';
    this.lastResult = null;
    this.currentFrame = '';

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
    this.ws.onmessage = e => this.handleMessage(JSON.parse(e.data));
    this.ws.onerror = () => this.setError('Erro na conexão WebSocket.');
    this.ws.onclose = () => { if (this.status === 'streaming') this.stop(); };

    this.ws.onopen = () => {
      this.status = 'streaming';
      // Capture a frame and send it every ~100ms (10fps cap sent to backend)
      this.captureInterval = setInterval(() => this.captureAndSend(), 100);
    };
  }

  private captureAndSend(): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    const video = this.videoElRef.nativeElement;
    const canvas = this.canvasElRef.nativeElement;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(video, 0, 0);
    // Send at reduced quality to keep bandwidth manageable
    const b64 = canvas.toDataURL('image/jpeg', 0.6).split(',')[1];
    this.ws.send(JSON.stringify({ type: 'frame', data: b64 }));
  }

  // ── RTSP ─────────────────────────────────────────────────────────────────

  private startRtsp(): void {
    if (!this.rtspUrl.trim()) {
      this.setError('Informe a URL do stream RTSP.');
      return;
    }

    this.ws = new WebSocket(`${WS_BASE}/rtsp`);
    this.ws.onmessage = e => this.handleMessage(JSON.parse(e.data));
    this.ws.onerror = () => this.setError('Erro na conexão WebSocket.');
    this.ws.onclose = () => { if (this.status === 'streaming') this.stop(); };

    this.ws.onopen = () => {
      this.ws!.send(JSON.stringify({ type: 'start', url: this.rtspUrl.trim() }));
    };
  }

  // ── Shared ────────────────────────────────────────────────────────────────

  private handleMessage(msg: { type: string } & Partial<StreamResult> & { message?: string }): void {
    if (msg.type === 'connected') {
      this.status = 'streaming';
    } else if (msg.type === 'result') {
      this.currentFrame = `data:image/jpeg;base64,${msg.frame_b64}`;
      this.lastResult = msg as StreamResult;
      if (this.status !== 'streaming') this.status = 'streaming';
    } else if (msg.type === 'error') {
      this.setError(msg.message ?? 'Erro desconhecido.');
    }
  }

  private setError(msg: string): void {
    this.errorMessage = msg;
    this.status = 'error';
    this.stop();
    this.status = 'error'; // keep error status after stop resets to idle
  }

  confidencePercent(conf: number | null): string {
    return conf != null ? `${(conf * 100).toFixed(1)}%` : '—';
  }
}
