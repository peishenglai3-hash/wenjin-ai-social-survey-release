/**
 * Mobile-optimized Audio Recorder — Opus/WebM encoding with chunked output.
 *
 * P0 for mid-July field deployment:
 *   - Opus @ 32kbps → ~240KB/min (vs WAV ~10MB/min)
 *   - 5-minute chunks → each ~1.2MB, uploadable over weak 4G
 *   - Storage check before recording starts
 *   - Wake Lock support to prevent sleep during recording
 */

export interface AudioChunk {
  blob: Blob;
  index: number;
  durationSeconds: number;
  startedAt: string;
}

export interface RecorderState {
  status: "idle" | "requesting" | "recording" | "paused" | "stopping" | "error";
  elapsedSeconds: number;
  totalBytes: number;
  chunkCount: number;
  errorMessage?: string;
}

type RecorderCallback = (state: RecorderState) => void;
type ChunkCallback = (chunk: AudioChunk) => void;

const TARGET_BITRATE = 32000;
const CHUNK_DURATION_SECONDS = 300;
const STORAGE_WARN_THRESHOLD_MB = 100;

async function estimateStorageMB(): Promise<number | null> {
  if ("storage" in navigator && "estimate" in navigator.storage) {
    try {
      const est = await navigator.storage.estimate();
      if (est.quota && est.usage) {
        return (est.quota - est.usage) / (1024 * 1024);
      }
    } catch { /* not available */ }
  }
  return null;
}

interface WakeLockSentinelLike {
  release(): Promise<void>;
}

async function requestWakeLock(): Promise<WakeLockSentinelLike | null> {
  if ("wakeLock" in navigator) {
    try {
      return await navigator.wakeLock.request("screen");
    } catch { /* user denied or not supported */ }
  }
  return null;
}

export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: AudioChunk[] = [];
  private startTime: number = 0;
  private chunkStartTime: number = 0;
  private elapsedTimer: ReturnType<typeof setInterval> | null = null;
  private wakeLock: WakeLockSentinelLike | null = null;
  private chunkIndex: number = 0;

  public state: RecorderState = {
    status: "idle", elapsedSeconds: 0, totalBytes: 0, chunkCount: 0,
  };

  private onStateChange: RecorderCallback | null = null;
  private onChunk: ChunkCallback | null = null;

  public setCallbacks(onState: RecorderCallback, onChunk: ChunkCallback) {
    this.onStateChange = onState;
    this.onChunk = onChunk;
  }

  private emitState(partial?: Partial<RecorderState>) {
    if (partial) Object.assign(this.state, partial);
    this.onStateChange?.({ ...this.state });
  }

  public async start(): Promise<void> {
    if (this.state.status === "recording") return;

    this.emitState({ status: "requesting" });

    const freeMB = await estimateStorageMB();
    if (freeMB !== null && freeMB < STORAGE_WARN_THRESHOLD_MB) {
      console.warn(
        `[AudioRecorder] Low storage: ~${freeMB.toFixed(0)}MB free. ` +
        `Each hour needs ~15MB.`,
      );
    }

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000, channelCount: 1,
          echoCancellation: true, noiseSuppression: true,
        },
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "未知错误";
      this.emitState({ status: "error", errorMessage: `麦克风权限被拒绝: ${message}` });
      return;
    }

    let mimeType = "";
    const candidates = [
      "audio/webm;codecs=opus", "audio/webm",
      "audio/ogg;codecs=opus", "audio/mp4",
    ];
    for (const c of candidates) {
      if (MediaRecorder.isTypeSupported(c)) { mimeType = c; break; }
    }
    if (!mimeType) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
      this.emitState({ status: "error", errorMessage: "浏览器不支持录音功能" });
      return;
    }

    const isOpus = mimeType.includes("opus");
    console.log(`[AudioRecorder] Codec: ${mimeType} (Opus: ${isOpus})`);

    this.mediaRecorder = new MediaRecorder(this.stream, {
      mimeType, audioBitsPerSecond: TARGET_BITRATE,
    });

    this.chunkIndex = 0;
    this.chunks = [];
    this.startTime = Date.now();
    this.chunkStartTime = this.startTime;

    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data.size === 0) return;
      const now = Date.now();
      const chunk: AudioChunk = {
        blob: event.data,
        index: this.chunkIndex++,
        durationSeconds: (now - this.chunkStartTime) / 1000,
        startedAt: new Date(this.chunkStartTime).toISOString(),
      };
      this.chunks.push(chunk);
      this.chunkStartTime = now;
      this.emitState({
        totalBytes: this.chunks.reduce((s, c) => s + c.blob.size, 0),
        chunkCount: this.chunks.length,
      });
      this.onChunk?.(chunk);
    };

    this.mediaRecorder.onerror = () => {
      this.emitState({ status: "error", errorMessage: "录音器内部错误" });
    };

    this.mediaRecorder.start(CHUNK_DURATION_SECONDS * 1000);
    this.emitState({ status: "recording", elapsedSeconds: 0, totalBytes: 0, chunkCount: 0 });

    this.wakeLock = await requestWakeLock();

    this.elapsedTimer = setInterval(() => {
      this.emitState({ elapsedSeconds: Math.floor((Date.now() - this.startTime) / 1000) });
    }, 1000);
  }

  public async stop(): Promise<AudioChunk[]> {
    if (!this.mediaRecorder || this.state.status !== "recording") {
      return this.chunks;
    }
    this.emitState({ status: "stopping" });

    return new Promise((resolve) => {
      this.mediaRecorder!.onstop = () => {
        if (this.elapsedTimer) { clearInterval(this.elapsedTimer); this.elapsedTimer = null; }
        if (this.wakeLock) {
          try { void this.wakeLock.release(); } catch { /* already released */ }
          this.wakeLock = null;
        }
        if (this.stream) {
          this.stream.getTracks().forEach((t) => t.stop());
          this.stream = null;
        }
        const finalElapsed = Math.floor((Date.now() - this.startTime) / 1000);
        const totalBytes = this.chunks.reduce((s, c) => s + c.blob.size, 0);
        this.emitState({ status: "idle", elapsedSeconds: finalElapsed, totalBytes });
        resolve(this.chunks);
      };
      this.mediaRecorder!.stop();
    });
  }

  public static getChunkURL(chunk: AudioChunk): string {
    return URL.createObjectURL(chunk.blob);
  }

  public static formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  public static formatDuration(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  public static async estimateRemainingTime(): Promise<string> {
    const freeMB = await estimateStorageMB();
    if (freeMB === null) return "未知";
    const minutesAt32kbps = freeMB / 0.24;
    if (minutesAt32kbps > 600) return `${Math.floor(minutesAt32kbps / 60)}小时+`;
    return `${Math.floor(minutesAt32kbps)}分钟`;
  }
}
