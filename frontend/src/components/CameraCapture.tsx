/**
 * CameraCapture — Browser-side facial analysis via MediaPipe Face Mesh.
 *
 * Captures webcam video, runs MediaPipe Face Mesh (468 landmarks) locally in-browser,
 * and extracts basic emotion/attention signals WITHOUT sending raw video anywhere.
 * PIPL-compliant: all facial processing stays on-device.
 *
 * Signals extracted:
 *  - Eye Aspect Ratio (EAR) → drowsiness / engagement
 *  - Mouth curvature → smile / frown detection
 *  - Eyebrow position → surprise / concentration
 *  - Head pose (yaw/pitch/roll) → attention direction
 *
 * Usage:
 *   <CameraCapture
 *     onEmotionSignal={(signal) => sendToPipeline(signal)}
 *     fps={5}
 *     width={320}
 *   />
 */

import { useEffect, useRef, useCallback, useState } from "react";
import { getErrorMessage, getErrorName } from "../utils/errors";

interface FaceMeshResults {
  multiFaceLandmarks?: Array<Array<{ x: number; y: number; z?: number }>>;
}

interface FaceMeshLike {
  setOptions(options: Record<string, boolean | number>): void;
  onResults(callback: (results: FaceMeshResults) => void): void;
  send(input: { image: HTMLVideoElement }): Promise<void>;
  close(): void;
}

// ── Types ──────────────────────────────────────────────────────

export interface FacialSignal {
  timestamp: number;
  /** Eye Aspect Ratio — low values indicate drowsiness or closed eyes */
  ear_left: number;
  ear_right: number;
  /** Mouth curvature — positive = smile, negative = frown */
  mouth_curve: number;
  /** Eyebrow lift — high values indicate raised brows (surprise) */
  brow_lift: number;
  /** Head pose in degrees */
  head_yaw: number;
  head_pitch: number;
  head_roll: number;
  /** Overall engagement score 0–1 */
  engagement: number;
  /** Detected expression label (best-effort, local only) */
  expression: "neutral" | "happy" | "surprised" | "concentrating" | "tired" | "uncertain";
}

interface CameraCaptureProps {
  onEmotionSignal?: (signal: FacialSignal) => void;
  fps?: number;
  width?: number;
  height?: number;
  mirrored?: boolean;
  enabled?: boolean;
}

// ── MediaPipe Face Mesh landmark indices ───────────────────────
const LEFT_EYE = [33, 160, 158, 133, 153, 144];
const RIGHT_EYE = [362, 385, 387, 263, 373, 380];
const MOUTH = [61, 291, 13, 14];
const LEFT_BROW = [70, 105];
const RIGHT_BROW = [300, 334];
const NOSE_TIP = 1;
const NOSE_BRIDGE = 168;
const CHIN = 152;

// ── Geometry helpers ────────────────────────────────────────────

function dist(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
}

function computeEAR(landmarks: { x: number; y: number }[], indices: number[]): number {
  const [p1, p2, p3, p4, p5, p6] = indices.map((i) => landmarks[i]);
  const v1 = dist(p2, p4), v2 = dist(p3, p5), h = dist(p1, p6);
  if (h < 0.001) return 0.3;
  return (v1 + v2) / (2.0 * h);
}

function computeMouthCurve(landmarks: { x: number; y: number }[], indices: number[]): number {
  const [lc, rc, top, bot] = indices.map((i) => landmarks[i]);
  const w = dist(lc, rc), h = dist(top, bot);
  if (w < 0.001) return 0;
  return (h / w - 0.15) * 5; // normalize to approx -1..1
}

function computeBrowLift(
  landmarks: { x: number; y: number }[],
  browIdx: number[], eyeIdx: number[],
): number {
  const browY = (landmarks[browIdx[0]].y + landmarks[browIdx[1]].y) / 2;
  const eyeY = (landmarks[eyeIdx[0]].y + landmarks[eyeIdx[1]].y) / 2;
  return eyeY - browY; // positive = raised brows
}

function estimateHeadPose(landmarks: { x: number; y: number; z?: number }[]): {
  yaw: number; pitch: number; roll: number;
} {
  const nt = landmarks[NOSE_TIP], nb = landmarks[NOSE_BRIDGE], ch = landmarks[CHIN];
  const yaw = ((nt.x || 0) - 0.5) * 60;
  const bcd = Math.abs((ch.y || 0) - (nb.y || 0));
  const pitch = bcd > 0.001 ? (((nt.y || 0) - (nb.y || 0)) / bcd - 0.5) * 60 : 0;
  const le = landmarks[LEFT_EYE[0]], re = landmarks[RIGHT_EYE[0]];
  const roll = Math.atan2((re.y || 0) - (le.y || 0), (re.x || 0) - (le.x || 0)) * (180 / Math.PI);
  return { yaw, pitch, roll };
}

// ── Expression labels ───────────────────────────────────────────

const EXPR_LABELS: Record<string, string> = {
  happy: "😊 愉悦", surprised: "😲 惊讶", concentrating: "🤔 专注",
  tired: "😴 疲惫", uncertain: "😕 迟疑", neutral: "😐 中性",
};

// ── Component ───────────────────────────────────────────────────

export default function CameraCapture({
  onEmotionSignal, fps = 5, width = 320, height = 240,
  mirrored = true, enabled = true,
}: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const faceMeshRef = useRef<FaceMeshLike | null>(null);
  const animRef = useRef<number>(0);
  const lastSignalRef = useRef<number>(0);
  const [status, setStatus] = useState<"idle" | "loading" | "active" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [expression, setExpression] = useState("—");

  const processLandmarks = useCallback((landmarks: { x: number; y: number; z?: number }[]) => {
    if (!landmarks || landmarks.length < 468) return;
    const now = Date.now();
    if (now - lastSignalRef.current < 1000 / fps) return;
    lastSignalRef.current = now;

    const earL = computeEAR(landmarks, LEFT_EYE);
    const earR = computeEAR(landmarks, RIGHT_EYE);
    const mc = computeMouthCurve(landmarks, MOUTH);
    const blL = computeBrowLift(landmarks, LEFT_BROW, LEFT_EYE);
    const blR = computeBrowLift(landmarks, RIGHT_BROW, RIGHT_EYE);
    const bl = (blL + blR) / 2;
    const { yaw, pitch, roll } = estimateHeadPose(landmarks);
    const avgEAR = (earL + earR) / 2;

    let engagement = 0.7;
    if (avgEAR < 0.18) engagement -= 0.3;
    else if (avgEAR > 0.25) engagement += 0.1;
    if (Math.abs(yaw) > 15) engagement -= 0.2;
    if (pitch < -15) engagement -= 0.3;
    if (mc > 0.1) engagement += 0.1;
    engagement = Math.max(0, Math.min(1, engagement));

    let expr: FacialSignal["expression"] = "neutral";
    if (mc > 0.15 && avgEAR > 0.22) expr = "happy";
    else if (bl > 0.04 && avgEAR > 0.24) expr = "surprised";
    else if (bl < -0.01 && mc < -0.05 && avgEAR < 0.20) expr = "concentrating";
    else if (avgEAR < 0.17 && Math.abs(yaw) > 10) expr = "tired";
    else if (mc < -0.08) expr = "uncertain";

    setExpression(EXPR_LABELS[expr] || expr);

    onEmotionSignal?.({
      timestamp: now, ear_left: earL, ear_right: earR,
      mouth_curve: mc, brow_lift: bl,
      head_yaw: yaw, head_pitch: pitch, head_roll: roll,
      engagement, expression: expr,
    });

    // Draw landmark overlay
    const canvas = canvasRef.current;
    if (canvas) {
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (const idx of [...LEFT_EYE, ...RIGHT_EYE, ...MOUTH, ...LEFT_BROW, ...RIGHT_BROW, NOSE_TIP, CHIN]) {
          const lm = landmarks[idx]; if (!lm) continue;
          ctx.fillStyle = "#4F46E5"; ctx.beginPath();
          ctx.arc(lm.x * canvas.width, lm.y * canvas.height, 2, 0, 2 * Math.PI); ctx.fill();
        }
        const [lc, rc] = MOUTH.slice(0, 2).map((i) => landmarks[i]);
        ctx.strokeStyle = mc > 0.05 ? "#10B981" : mc < -0.05 ? "#EF4444" : "#6B7280";
        ctx.lineWidth = 2; ctx.beginPath();
        ctx.moveTo(lc.x * canvas.width, lc.y * canvas.height);
        ctx.quadraticCurveTo(
          (lc.x + rc.x) / 2 * canvas.width,
          ((lc.y + rc.y) / 2 + mc * 30) * canvas.height,
          rc.x * canvas.width, rc.y * canvas.height,
        ); ctx.stroke();
      }
    }
  }, [fps, onEmotionSignal]);

  useEffect(() => {
    if (!enabled) {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      if (animRef.current) cancelAnimationFrame(animRef.current);
      return;
    }
    let cancelled = false;

    async function init() {
      setStatus("loading"); setErrorMsg("");
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: width }, height: { ideal: height }, facingMode: "user", frameRate: { ideal: fps * 2 } },
          audio: false,
        });
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        const video = videoRef.current; if (!video) return;
        video.srcObject = stream; await video.play();

        const { FaceMesh } = await import("@mediapipe/face_mesh");
        const faceMesh = new FaceMesh({
          locateFile: (file: string) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`,
        });
        faceMesh.setOptions({ maxNumFaces: 1, refineLandmarks: false, minDetectionConfidence: 0.7, minTrackingConfidence: 0.5 });
        faceMesh.onResults((results: FaceMeshResults) => {
          const landmarks = results.multiFaceLandmarks;
          if (landmarks && landmarks.length > 0) processLandmarks(landmarks[0]);
        });
        faceMeshRef.current = faceMesh;
        setStatus("active");

        const loop = async () => {
          if (cancelled) return;
          if (video.readyState >= 2 && faceMeshRef.current) await faceMeshRef.current.send({ image: video });
          animRef.current = requestAnimationFrame(loop);
        };
        loop();
      } catch (err: unknown) {
        if (cancelled) return;
        const errorName = getErrorName(err);
        setErrorMsg(errorName === "NotAllowedError" ? "摄像头权限被拒绝" : errorName === "NotFoundError" ? "未检测到摄像头" : `初始化失败: ${getErrorMessage(err, "未知错误")}`);
        setStatus("error");
      }
    }
    init();
    return () => {
      cancelled = true;
      cancelAnimationFrame(animRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      faceMeshRef.current?.close();
      faceMeshRef.current = null;
    };
  }, [enabled, width, height, fps, processLandmarks]);

  const visibleStatus = enabled ? status : "idle";

  return (
    <div style={{ position: "relative", width, borderRadius: 10, background: "#0F172A", overflow: "hidden" }}>
      <div style={{ position: "absolute", top: 8, left: 8, zIndex: 10, display: "flex", gap: 6, alignItems: "center" }}>
        <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 600, color: "#fff", background: status === "active" ? "#10B981" : status === "loading" ? "#F59E0B" : status === "error" ? "#EF4444" : "#6B7280" }}>
          {visibleStatus === "active" ? "● 实时" : visibleStatus === "loading" ? "◌ 加载" : visibleStatus === "error" ? "✕ 错误" : "○ 待机"}
        </span>
        {visibleStatus === "active" && <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: 10, background: "rgba(255,255,255,0.15)", color: "#E2E8F0" }}>{expression}</span>}
      </div>
      <video ref={videoRef} style={{ display: "none" }} playsInline muted />
      <canvas ref={canvasRef} width={width} height={height} style={{ width: "100%", aspectRatio: `${width}/${height}`, transform: mirrored ? "scaleX(-1)" : "none", borderRadius: 10 }} />
      <div style={{ position: "absolute", bottom: 6, right: 8, zIndex: 10, fontSize: 9, color: "rgba(255,255,255,0.4)" }}>🔒 本地推理 · 不上传视频</div>
      {visibleStatus === "error" && <div style={{ position: "absolute", inset: 0, zIndex: 20, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.7)", borderRadius: 10 }}><div style={{ textAlign: "center", color: "#FCA5A5", padding: 20, fontSize: 12 }}><div style={{ fontSize: 24, marginBottom: 8 }}>📷✕</div>{errorMsg}</div></div>}
      {visibleStatus === "loading" && <div style={{ position: "absolute", inset: 0, zIndex: 20, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.5)", borderRadius: 10 }}><div style={{ textAlign: "center", color: "#E2E8F0", fontSize: 13 }}><div style={{ fontSize: 24, marginBottom: 8 }}>⏳</div>加载面部识别模型...</div></div>}
    </div>
  );
}
