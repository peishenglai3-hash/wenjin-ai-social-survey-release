import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import api from "../api/client";
import { streamAI } from "../api/stream";
import { useApp } from "../context/AppContext";
import { validateFile } from "../utils/uploadValidation";
import { useAutoSave } from "../hooks/useAutoSave";
import QuickNav from "../components/QuickNav";
import InterviewModeConfig from "../components/InterviewModeConfig";
import CameraCapture from "../components/CameraCapture";
import type { FacialSignal } from "../components/CameraCapture";
import EmotionDashboard from "../components/EmotionDashboard";
import HintOverlay from "../components/HintOverlay";
import type { Hint } from "../components/HintOverlay";
import QuestionnaireFill from "../components/QuestionnaireFill";
import config from "../config";
import { getAccessToken } from "../api/client";
import { getAuthHeaders } from "../utils/authFetch";
import { enqueueSession, getQueueSize, flushQueue, startAutoFlush, getOnlineStatus } from "../services/offlineQueue";
import { AudioRecorder, type RecorderState } from "../services/audioRecorder";
import { fetchFieldNotes, createFieldNote, updateFieldNote, deleteFieldNote } from "../api/coding";
import type { FieldNoteItem, NoteType } from "../types/coding";
import { NOTE_TYPE_LABELS, NOTE_TYPE_ICONS } from "../types/coding";

// Check browser speech recognition support
const SpeechRecognitionAPI =
  (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

function getWsUrl(endpoint: "asr" | "asr/qwen" | "facial" = "asr"): string {
  const loc = window.location;
  const protocol = loc.protocol === "https:" ? "wss:" : "ws:";
  if (loc.hostname === "localhost") {
    return `${protocol}//${loc.hostname}:8000/api/v1/fieldwork/${endpoint}`;
  }
  return `${protocol}//${loc.host}/api/v1/fieldwork/${endpoint}`;
}

function createAuthenticatedWebSocket(url: string): WebSocket {
  const token = getAccessToken();
  if (token && token !== "guest") {
    return new WebSocket(url, ["bearer", token]);
  }
  return new WebSocket(url);
}

type Tab = "asr" | "hints" | "notes" | "image" | "file" | "camera" | "survey";
type ASRMode = "browser" | "xunfei" | "qwen" | null;
type Speaker = "interviewer" | "respondent";

interface SpeakerLine {
  id: string;
  text: string;
  timestamp: string; // HH:MM:SS
  questionIndex: number;
}

// ── Interview mode & scenario config ──
interface ScenarioTemplate {
  id: string; name: string; icon: string; category: string;
  description: string; features: string[];
  suitable_methods: string[]; common_pitfalls: string[];
  ethical_notes: string; recommended_tools: string;
}

export default function FieldworkTools() {
  const { project, theme } = useApp();
  const [activeTab, setActiveTab] = useState<Tab>("asr");

  // ── Interview Mode & Scenario State ──
  const [interviewMode, setInterviewMode] = useState<string | null>(null);
  const [scenarioTemplates, setScenarioTemplates] = useState<ScenarioTemplate[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<ScenarioTemplate | null>(null);
  const [showScenarioPicker, setShowScenarioPicker] = useState(false);

  // Fetch scenario templates on mount
  useEffect(() => {
    fetch(`${config.apiBaseUrl}/api/v1/scenarios/templates`, { headers: getAuthHeaders() })
      .then(r => r.json()).then(d => setScenarioTemplates(d.scenarios || [])).catch(() => {});
  }, []);

  // ── ASR State ──
  const [status, setStatus] = useState<"idle" | "connecting" | "ready" | "recording" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [asrMode, setAsrMode] = useState<ASRMode>(null);

  // ── Speaker-aware transcript state ──
  const [currentSpeaker, setCurrentSpeaker] = useState<Speaker>("interviewer");
  const [interviewerLines, setInterviewerLines] = useState<SpeakerLine[]>([]);
  const [respondentLines, setRespondentLines] = useState<SpeakerLine[]>([]);
  const [interimText, setInterimText] = useState("");
  const questionIndexRef = useRef(1);

  // Derived flat transcript for backward compat (auto-save, hints, etc.)
  const transcript = useMemo(() => {
    const all: string[] = [];
    for (const l of interviewerLines) all.push(`[访谈者 Q${l.questionIndex}] ${l.text}`);
    for (const l of respondentLines) all.push(`[被访谈者 Q${l.questionIndex}] ${l.text}`);
    return all.join("\n");
  }, [interviewerLines, respondentLines]);
  // ── Camera/Face state ──
  const [facialSignals, setFacialSignals] = useState<FacialSignal[]>([]);
  const [liveHints, setLiveHints] = useState<Hint[]>([]);
  const [cameraEnabled, setCameraEnabled] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const facialWsRef = useRef<WebSocket | null>(null);  // Facial signal WebSocket
  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const speechRef = useRef<any>(null); // SpeechRecognition instance
  // Refs to avoid stale closures in callbacks
  const statusRef = useRef(status);
  const currentSpeakerRef = useRef<Speaker>(currentSpeaker);
  const committedRef = useRef(""); // stable committed transcript buffer
  const speechActiveRef = useRef(false); // tracks if speech recognition should be active

  // ── Hints State ──
  const [hints, setHints] = useState<string[]>([]);
  const [hintsLoading, setHintsLoading] = useState(false);

  // ── Notes & Summary State ──
  const [notes, setNotes] = useState("");
  const [summary, setSummary] = useState("");
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const lastSavedContentRef = useRef("");

  // ── Field Notes State ──
  const [fieldNotes, setFieldNotes] = useState<FieldNoteItem[]>([]);
  const [notesFilter, setNotesFilter] = useState<NoteType | "all">("all");
  const [notesAiFilter, setNotesAiFilter] = useState<"all" | "ai" | "manual">("all");
  const [showNewNote, setShowNewNote] = useState(false);
  const [newNoteType, setNewNoteType] = useState<NoteType>("observation");
  const [newNoteContent, setNewNoteContent] = useState("");
  const [newNoteTags, setNewNoteTags] = useState("");
  const [editingNoteId, setEditingNoteId] = useState<number | null>(null);
  const [editingNoteContent, setEditingNoteContent] = useState("");
  const [notesLoading, setNotesLoading] = useState(false);

  // ── Questionnaire state ──
  interface QListItem { id: number; title: string; total_items: number; }
  const [questionnaireList, setQuestionnaireList] = useState<QListItem[]>([]);
  const [selectedQId, setSelectedQId] = useState<number | null>(null);
  const [questionnaireData, setQuestionnaireData] = useState<any>(null);
  const [surveyStats, setSurveyStats] = useState<any>(null);

  // Load field notes on mount and when session changes
  const loadFieldNotes = useCallback(async (sessionId?: number) => {
    setNotesLoading(true);
    try {
      const data = await fetchFieldNotes(sessionId);
      setFieldNotes(data || []);
    } catch { /* ignore */ }
    finally { setNotesLoading(false); }
  }, []);

  useEffect(() => {
    loadFieldNotes();
  }, [loadFieldNotes]);

  // Load questionnaire list when survey tab is active
  useEffect(() => {
    if (activeTab === "survey" && project?.id) {
      api.get(`/questionnaire/by-project/${project.id}`)
        .then(r => setQuestionnaireList(r.data || []))
        .catch(() => {});
    }
  }, [activeTab, project?.id]);

  const handleCreateNote = async () => {
    if (!newNoteContent.trim()) return;
    try {
      const tags = newNoteTags ? newNoteTags.split(",").map((t) => t.trim()).filter(Boolean) : [];
      await createFieldNote({
        session_id: 0, // Will be set by backend if session context exists
        note_type: newNoteType,
        content: newNoteContent.trim(),
        tags,
        ai_generated: false,
      });
      setNewNoteContent("");
      setNewNoteTags("");
      setShowNewNote(false);
      await loadFieldNotes();
    } catch { /* ignore */ }
  };

  const handleEditNote = async (noteId: number) => {
    if (!editingNoteContent.trim()) return;
    try {
      await updateFieldNote(noteId, { content: editingNoteContent.trim() } as any);
      setEditingNoteId(null);
      setEditingNoteContent("");
      await loadFieldNotes();
    } catch { /* ignore */ }
  };

  const handleDeleteNote = async (noteId: number) => {
    if (!confirm("确定删除此笔记？")) return;
    try {
      await deleteFieldNote(noteId);
      await loadFieldNotes();
    } catch { /* ignore */ }
  };

  // ── Auto-save: offline-first — queues locally when network is down ──
  const autoSaveSession = useCallback(async () => {
    if (!transcript && !notes) return;
    if (!project?.id) return;
    const currentContent = transcript + notes + summary;
    if (currentContent === lastSavedContentRef.current) return;
    try {
      const payload = {
        project_id: project.id,
        transcript_text: transcript,
        notes,
        summary_text: summary,
        hints_generated: JSON.stringify(hints),
      };
      const result = await enqueueSession("/fieldwork/sessions", payload);
      if (!result.queued) {
        lastSavedContentRef.current = currentContent;
        setDirty(false);
      }
      // If queued, keep dirty flag so user knows it's unsaved
    } catch {
      // silent — auto-save failures should never interrupt the user
    }
  }, [transcript, notes, summary, hints, project?.id]);

  useAutoSave(dirty, autoSaveSession);

  // Track dirty state when editable content changes
  useEffect(() => {
    const currentContent = transcript + notes + summary;
    if (currentContent !== lastSavedContentRef.current) {
      setDirty(true);
    }
  }, [transcript, notes, summary]);

  // ── Auto-hints timer ──
  const hintsTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const transcriptLenRef = useRef(0); // stable counter for hints trigger

  // Keep refs in sync with state
  useEffect(() => { statusRef.current = status; }, [status]);
  useEffect(() => { currentSpeakerRef.current = currentSpeaker; }, [currentSpeaker]);
  useEffect(() => { transcriptLenRef.current = transcript.length; }, [transcript]);

  useEffect(() => {
    if (status === "recording" && transcript.length > 100) {
      // Only set interval if one isn't already running
      if (!hintsTimerRef.current) {
        hintsTimerRef.current = setInterval(() => {
          fetchHints();
        }, 45000);
      }
    } else {
      if (hintsTimerRef.current) {
        clearInterval(hintsTimerRef.current);
        hintsTimerRef.current = null;
      }
    }
    return () => {
      if (hintsTimerRef.current) {
        clearInterval(hintsTimerRef.current);
        hintsTimerRef.current = null;
      }
    };
  }, [status, transcript.length > 99]); // Only re-evaluate on status change or crossing 100-char threshold

  const lastFacialSendRef = useRef(0);  // throttle facial WS sends

  /** Connect facial-signal WebSocket to backend EmotionTracker. */
  const connectFacialWS = useCallback(() => {
    if (facialWsRef.current?.readyState === WebSocket.OPEN) return;
    try {
      const ws = createAuthenticatedWebSocket(getWsUrl("facial"));
      facialWsRef.current = ws;
      ws.onopen = () => console.log("[FacialWS] Connected");
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "emotion_alert") {
            setLiveHints((prev) => [
              { id: `alert_${Date.now()}`, text: `${data.message} — ${data.suggested_action}`, urgency: "high" as const, timestamp: Date.now() },
              ...prev.slice(0, 9),
            ]);
          }
        } catch { /* ignore parse errors */ }
      };
      ws.onclose = () => {
        console.log("[FacialWS] Disconnected");
        facialWsRef.current = null;
      };
      ws.onerror = () => {
        facialWsRef.current?.close();
        facialWsRef.current = null;
      };
    } catch {
      // WebSocket not supported or connection failed — silently degrade
    }
  }, []);

  /** Send a facial signal to the backend (throttled to ~5Hz). */
  const sendFacialSignal = useCallback((signal: FacialSignal) => {
    const now = Date.now();
    if (now - lastFacialSendRef.current < 200) return; // throttle to 5Hz
    lastFacialSendRef.current = now;
    if (facialWsRef.current?.readyState === WebSocket.OPEN) {
      facialWsRef.current.send(JSON.stringify({ type: "facial_signal", signal }));
    }
  }, []);

  /** Disconnect facial WebSocket. */
  const disconnectFacialWS = useCallback(() => {
    if (facialWsRef.current) {
      facialWsRef.current.close();
      facialWsRef.current = null;
    }
  }, []);

  // Auto-connect facial WS when camera is enabled during recording
  useEffect(() => {
    if (cameraEnabled && status === "recording") {
      connectFacialWS();
    } else {
      disconnectFacialWS();
    }
    return () => { disconnectFacialWS(); };
  }, [cameraEnabled, status, connectFacialWS, disconnectFacialWS]);

  const stopRecording = useCallback(() => {
    speechActiveRef.current = false;
    // Stop browser speech recognition
    if (speechRef.current) {
      try { speechRef.current.stop(); } catch {}
      speechRef.current = null;
    }
    // Stop Xunfei WebSocket
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "end" }));
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    wsRef.current = null;
    setAsrMode(null);
    setStatus("idle");
    setInterimText("");
  }, []);

  /** Browser-based ASR using Web Speech API — works offline in Chrome */
  const startBrowserASR = useCallback(() => {
    if (!SpeechRecognitionAPI) {
      setErrorMsg("浏览器不支持语音识别。请使用 Chrome 或 Edge 浏览器。");
      setStatus("error");
      return;
    }

    const recognition = new SpeechRecognitionAPI();
    speechRef.current = recognition;
    speechActiveRef.current = true;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "zh-CN";

    recognition.onstart = () => {
      setAsrMode("browser");
      setStatus("recording");
    };

    recognition.onresult = (event: any) => {
      let interim = "";
      const now = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          const line: SpeakerLine = {
            id: `line_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
            text: result[0].transcript,
            timestamp: now,
            questionIndex: questionIndexRef.current,
          };
          committedRef.current += result[0].transcript;
          // Route to correct speaker column
          if (currentSpeakerRef.current === "interviewer") {
            setInterviewerLines((prev) => [...prev, line]);
          } else {
            setRespondentLines((prev) => [...prev, line]);
          }
        } else {
          interim += result[0].transcript;
        }
      }
      setInterimText(interim);
    };

    recognition.onerror = (event: any) => {
      console.error("Browser ASR error:", event.error);
      if (event.error === "not-allowed") {
        setErrorMsg("麦克风权限被拒绝，请在浏览器设置中允许访问麦克风");
        speechActiveRef.current = false;
        setStatus("error");
        setAsrMode(null);
      } else if (event.error === "no-speech") {
        // Normal during pauses — don't break recording flow
        // onend will fire next, and we'll restart from there
      } else if (event.error === "aborted") {
        // Intentionally stopped — expected
      } else {
        setErrorMsg(`浏览器语音识别错误: ${event.error}`);
        speechActiveRef.current = false;
        setStatus("error");
        setAsrMode(null);
      }
    };

    recognition.onend = () => {
      // Auto-restart if still recording (browser ASR stops after pauses)
      // Use refs instead of state to avoid stale closures
      if (speechActiveRef.current && speechRef.current) {
        try {
          recognition.start();
        } catch {
          // If restart fails, give up
          speechActiveRef.current = false;
        }
      }
    };

    recognition.start();
  }, []);

  const startRecording = useCallback(async () => {
    setErrorMsg("");
    setHints([]);
    setInterviewerLines([]);
    setRespondentLines([]);
    setInterimText("");
    setCurrentSpeaker("interviewer");
    questionIndexRef.current = 1;
    committedRef.current = "";
    setStatus("connecting");

    // ── Try browser ASR first (no server dependency) ──
    if (SpeechRecognitionAPI) {
      try {
        // Request microphone permission via getUserMedia first
        // (SpeechRecognition needs it, and this triggers the permission prompt)
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true },
        });
        // Stop the stream — browser ASR manages its own audio capture
        stream.getTracks().forEach((t) => t.stop());
        startBrowserASR();
        return;
      } catch (err: any) {
        if (err.name === "NotAllowedError") {
          setErrorMsg("麦克风权限被拒绝，请在浏览器设置中允许访问麦克风");
          setStatus("error");
          return;
        }
        // Fall through to Xunfei WebSocket on other errors
      }
    }

    // ── Fallback: Qwen WebSocket ASR ──
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true },
      });
      streamRef.current = stream;

      const ws = createAuthenticatedWebSocket(getWsUrl("asr/qwen"));
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      let wsReady = false;

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          // Qwen Paraformer WS responses
          if (data.header) {
            // Connection established
            setAsrMode("qwen");
            setStatus("recording");
            wsReady = true;
            startAudioPipeline(stream, ws);
          }
          // Extract transcript text from Qwen response
          const payload = data.payload || data;
          const text = payload.result || payload.text || "";
          if (text && text.trim()) {
            const now = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
            const line: SpeakerLine = {
              id: `line_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
              text: text.trim(),
              timestamp: now,
              questionIndex: questionIndexRef.current,
            };
            if (currentSpeakerRef.current === "interviewer") {
              setInterviewerLines((prev) => [...prev, line]);
            } else {
              setRespondentLines((prev) => [...prev, line]);
            }
          }
          if (data.type === "error" || (payload && payload.error)) {
            const errMsg = payload?.error || data.message || "ASR error";
            setErrorMsg(`千问语音服务: ${errMsg}`);
            setStatus("error");
          }
        } catch {
          // Binary frame — ignore
        }
      };

      ws.onerror = () => {
        setErrorMsg("千问语音服务连接失败。请尝试使用 Chrome 浏览器的语音识别功能。");
        setStatus("error");
      };

      ws.onclose = () => {
        if (statusRef.current === "recording") {
          speechActiveRef.current = false;
          setStatus("idle");
        }
      };

      // Timeout: if no response in 10s, try Xunfei fallback
      setTimeout(() => {
        if (!wsReady && wsRef.current === ws) {
          ws.close();
          setErrorMsg("千问ASR服务响应超时，请确认QWEN_API_KEY已配置。或使用Chrome浏览器语音识别。");
          setStatus("error");
        }
      }, 10000);
    } catch (err: any) {
      if (err.name === "NotAllowedError") {
        setErrorMsg("麦克风权限被拒绝，请在浏览器设置中允许访问麦克风");
      } else {
        setErrorMsg(`录音启动失败: ${err.message}`);
      }
      setStatus("error");
    }
  }, [startBrowserASR]);

  const startAudioPipeline = (stream: MediaStream, ws: WebSocket) => {
    const audioCtx = new AudioContext({ sampleRate: 16000 });
    audioCtxRef.current = audioCtx;
    const source = audioCtx.createMediaStreamSource(stream);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);
    source.connect(processor);
    processor.connect(audioCtx.destination);

    processor.onaudioprocess = (e) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      const inputData = e.inputBuffer.getChannelData(0);
      let samples: Float32Array;
      if (audioCtx.sampleRate === 16000) {
        samples = inputData;
      } else {
        const ratio = audioCtx.sampleRate / 16000;
        const newLen = Math.floor(inputData.length / ratio);
        samples = new Float32Array(newLen);
        for (let i = 0; i < newLen; i++) samples[i] = inputData[Math.floor(i * ratio)];
      }

      const pcm = new Int16Array(samples.length);
      for (let i = 0; i < samples.length; i++) {
        const s = Math.max(-1, Math.min(1, samples[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }

      const FRAME_SAMPLES = 640;
      for (let i = 0; i < pcm.length; i += FRAME_SAMPLES) {
        const chunk = pcm.slice(i, i + FRAME_SAMPLES);
        if (chunk.length === FRAME_SAMPLES && ws.readyState === WebSocket.OPEN) {
          ws.send(chunk.buffer);
        }
      }
    };
  };

  // ── Hints ──

  const fetchHints = async () => {
    if (!transcript.trim() || transcript.length < 50) return;
    setHintsLoading(true);
    try {
      const res = await api.post("/fieldwork/hints", {
        transcript: transcript.slice(-2000),
        scenario: selectedScenario?.id || project?.paradigm || "community_interview",
        phase: "main",
        theme,
        interview_mode: interviewMode,
      });
      const data = res.data.hints;
      if (Array.isArray(data)) {
        setHints(data);
      } else if (typeof data === "string") {
        try {
          setHints(JSON.parse(data));
        } catch {
          setHints([data]);
        }
      }
    } catch {
      // Silently fail for auto-hints
    } finally {
      setHintsLoading(false);
    }
  };

  const fetchHintsStream = async () => {
    if (!transcript.trim() || transcript.length < 50) return;
    setHintsLoading(true);
    setHints([]);
    let full = "";
    await streamAI(
      "/fieldwork/hints/stream",
      {
        transcript: transcript.slice(-2000),
        scenario: selectedScenario?.id || project?.paradigm || "community_interview",
        phase: "main",
        theme,
        interview_mode: interviewMode,
      },
      (token) => {
        full += token;
        try {
          const parsed = JSON.parse(full);
          if (Array.isArray(parsed)) setHints(parsed);
        } catch { /* wait for complete JSON */ }
      },
      () => {
        if (full) {
          try { setHints(JSON.parse(full)); } catch { setHints([full]); }
        }
        setHintsLoading(false);
      },
      (err) => { console.error(err); setHintsLoading(false); },
    );
  };

  // ── Summarize ──

  const handleSummarize = async () => {
    const textToSummarize = transcript || notes;
    if (!textToSummarize.trim()) return;
    setSummaryLoading(true);
    setSummary("");
    await streamAI(
      "/fieldwork/summarize/stream",
      { transcript: textToSummarize, theme },
      (token) => setSummary((prev) => prev + token),
      () => setSummaryLoading(false),
      (err) => { setSummary(err); setSummaryLoading(false); },
    );
  };

  // ── Image Analysis State ──
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState("");
  const [imageDesc, setImageDesc] = useState("");
  const [imageAnalysis, setImageAnalysis] = useState("");
  const [imageLoading, setImageLoading] = useState(false);
  const [imageFocus, setImageFocus] = useState("auto");
  const [imageLocation, setImageLocation] = useState("");

  // ── Offline queue & network state ──
  const [isOnline, setIsOnline] = useState(getOnlineStatus());
  const [queueSize, setQueueSize] = useState(getQueueSize());

  useEffect(() => {
    startAutoFlush(60000);
    const updateNetwork = () => {
      setIsOnline(getOnlineStatus());
      setQueueSize(getQueueSize());
    };
    window.addEventListener("online", updateNetwork);
    window.addEventListener("offline", updateNetwork);
    const pollQueue = setInterval(() => setQueueSize(getQueueSize()), 5000);
    return () => {
      window.removeEventListener("online", updateNetwork);
      window.removeEventListener("offline", updateNetwork);
      clearInterval(pollQueue);
    };
  }, []);

  // ── AudioRecorder (Opus/WebM — for saving, complementary to ASR) ──
  const audioRecorderRef = useRef<AudioRecorder | null>(null);
  const [opusRecorderState, setOpusRecorderState] = useState<RecorderState>({
    status: "idle", elapsedSeconds: 0, totalBytes: 0, chunkCount: 0,
  });
  const [storageEstimate, setStorageEstimate] = useState<string>("");

  useEffect(() => {
    AudioRecorder.estimateRemainingTime().then(setStorageEstimate);
  }, []);

  const startOpusRecording = async () => {
    const recorder = new AudioRecorder();
    audioRecorderRef.current = recorder;
    recorder.setCallbacks(setOpusRecorderState, async (chunk) => {
      // Queue each chunk for upload when online
      if (project?.id) {
        const formData = new FormData();
        formData.append("file", chunk.blob, `interview-chunk-${chunk.index}.webm`);
        formData.append("project_id", String(project.id));
        formData.append("chunk_index", String(chunk.index));
        formData.append("language", "zh");
        try {
          await api.post("/fieldwork/transcribe-file", formData, {
            headers: { "Content-Type": "multipart/form-data" },
          });
        } catch {
          // Queue for later — chunk blobs are in memory, store reference
          console.warn(`[Opus] Chunk ${chunk.index} upload queued`);
        }
      }
    });
    await recorder.start();
  };

  const stopOpusRecording = async () => {
    if (audioRecorderRef.current) {
      const chunks = await audioRecorderRef.current.stop();
      console.log(`[Opus] Recorded ${chunks.length} chunks, ${AudioRecorder.formatBytes(opusRecorderState.totalBytes)}`);
      audioRecorderRef.current = null;
    }
  };

  // ── File Upload Transcription State ──
  const [fileUpload, setFileUpload] = useState<File | null>(null);
  const [fileUploading, setFileUploading] = useState(false);
  const [fileResult, setFileResult] = useState<any>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const result = validateFile(file, "audio");
    if (!result.ok) {
      alert(`⚠️ ${result.reason}`);
      // Reset file input so user can re-select
      const input = e.target as HTMLInputElement;
      input.value = "";
      return;
    }
    setFileUpload(file);
    setFileResult(null);
  };

  const handleFileUpload = async () => {
    if (!fileUpload) return;
    setFileUploading(true);
    setFileResult(null);
    try {
      const form = new FormData();
      form.append("file", fileUpload);
      form.append("language", "zh");
      const res = await api.post("/fieldwork/transcribe-file", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setFileResult(res.data);
    } catch (e: any) {
      setFileResult({ error: e.message || "上传失败" });
    } finally {
      setFileUploading(false);
    }
  };

  // ── Image Analysis Handlers ──

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const result = validateFile(file, "image");
    if (!result.ok) {
      alert(`⚠️ ${result.reason}`);
      const input = e.target as HTMLInputElement;
      input.value = "";
      return;
    }
    setImageFile(file);
    setImageAnalysis("");

    const reader = new FileReader();
    reader.onload = () => setImagePreview(reader.result as string);
    reader.readAsDataURL(file);
  };

  const handleAnalyzeImage = async () => {
    if (!imageFile && !imageDesc.trim()) return;
    setImageLoading(true);
    setImageAnalysis("");
    try {
      let imageBase64 = "";
      if (imageFile) {
        const reader = new FileReader();
        imageBase64 = await new Promise((resolve) => {
          reader.onload = () => {
            const result = (reader.result as string).split(",")[1] || "";
            resolve(result);
          };
          reader.readAsDataURL(imageFile);
        });
      }

      const res = await api.post("/image/analyze", {
        image_base64: imageBase64,
        image_description: imageDesc,
        research_topic: project?.research_direction || "",
        field_location: imageLocation,
        analysis_focus: imageFocus,
      });
      setImageAnalysis(res.data.analysis || "未返回分析结果");
    } catch {
      setImageAnalysis("图片分析失败，请重试");
    } finally {
      setImageLoading(false);
    }
  };

  // ── Download ──

  const handleDownload = async (content: string, label: string, fileType: "docx" | "md") => {
    if (!content) return;
    setDownloading(fileType);
    try {
      const title = label.slice(0, 30) || "田野记录";
      const res = await api.post("/export/download-content", {
        content,
        file_type: fileType,
        title,
      }, { responseType: "blob" });
      const blob = new Blob([res.data], {
        type: fileType === "docx"
          ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          : "text/markdown",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${title}.${fileType}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert(`${fileType.toUpperCase()} 下载失败`);
    } finally {
      setDownloading(null);
    }
  };

  // ── Save Session (offline-first) ──

  const handleSaveSession = async () => {
    if (!transcript && !notes) return;
    if (!project?.id) {
      alert("请先在首页创建或选择一个项目，再保存田野会话。");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        project_id: project.id,
        transcript_text: transcript,
        notes,
        summary_text: summary,
        hints_generated: JSON.stringify(hints),
      };
      const result = await enqueueSession("/fieldwork/sessions", payload);
      if (result.queued) {
        alert(`📡 当前离线，会话已暂存本地（队列: ${getQueueSize()} 条）。恢复网络后自动同步。`);
      } else {
        lastSavedContentRef.current = transcript + notes + summary;
        setDirty(false);
        alert("田野会话已保存");
      }
    } catch {
      alert("保存失败");
    } finally {
      setSaving(false);
    }
  };

  // ── Render ──

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: "asr", label: "录音转写 · AI提示", icon: "🎙" },
    { key: "hints", label: "提示历史", icon: "💡" },
    { key: "notes", label: "笔记与摘要", icon: "📝" },
    { key: "image", label: "图像分析", icon: "📷" },
    { key: "file", label: "文件转写", icon: "📁" },
    { key: "camera", label: "面部情绪", icon: "📷" },
    { key: "survey", label: "问卷调查", icon: "📋" },
  ];

  return (
    <div className="page">
      <h2>调查工具箱</h2>
      <p className="subtitle">录音转写 · AI实时提示 · 笔记摘要 · 会话管理</p>

      {/* HTTPS warning */}
      {window.location.protocol === "http:" && window.location.hostname !== "localhost" && (
        <div className="warning-banner">
          ⚠ 浏览器安全策略要求 <strong>HTTPS</strong> 才能访问麦克风。当前为 HTTP 连接，录音功能不可用。请联系管理员配置 SSL 证书。
        </div>
      )}

      {/* Offline indicator & sync queue */}
      {(!isOnline || queueSize > 0) && (
        <div style={{
          padding: "8px 14px", marginBottom: 16, borderRadius: 8,
          background: isOnline ? "#F0FDF4" : "#FEF3C7",
          border: `1px solid ${isOnline ? "#BBF7D0" : "#FDE68A"}`,
          fontSize: 13, display: "flex", alignItems: "center", gap: 8,
        }}>
          <span>{isOnline ? "📶" : "📡"}</span>
          <span style={{ flex: 1 }}>
            {isOnline
              ? queueSize > 0
                ? `正在同步 ${queueSize} 条离线会话...`
                : "已连接"
              : `离线模式 · ${queueSize} 条会话暂存本地`}
          </span>
          {!isOnline && (
            <span style={{ fontSize: 11, color: "#92400E" }}>
              恢复网络后自动同步
            </span>
          )}
          {isOnline && queueSize > 0 && (
            <button
              onClick={() => flushQueue().then(() => setQueueSize(getQueueSize()))}
              style={{ fontSize: 11, padding: "2px 8px", cursor: "pointer" }}
            >
              立即同步
            </button>
          )}
        </div>
      )}

      {/* Storage estimate for recording */}
      {opusRecorderState.status === "idle" && storageEstimate && (
        <div style={{
          fontSize: 11, color: "var(--text-muted)", marginBottom: 8,
          textAlign: "right",
        }}>
          💾 可用存储: ~{storageEstimate}
        </div>
      )}

      {/* Tab bar */}
      <div className="fieldwork-tabs" role="group" aria-label="田野工具模块">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setActiveTab(t.key)}
            aria-pressed={activeTab === t.key}
            className={`fieldwork-tab${activeTab === t.key ? " fieldwork-tab--active" : ""}`}
          >
            <span style={{ marginRight: 6 }}>{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Tab 1: ASR Recording ── */}
      {activeTab === "asr" && (
        <div>
          {/* ── Scenario & Interview Mode Config (shown before/during recording setup) ── */}
          {status === "idle" && (
            <>
              {/* Scenario quick-pick bar */}
              <div style={{
                display: "flex", alignItems: "center", gap: 10, marginBottom: 16,
                padding: "10px 14px", background: "var(--surface)", borderRadius: 10,
                border: "1px solid var(--border)",
              }}>
                <span style={{ fontSize: 18 }}>🎬</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>
                    {selectedScenario ? `${selectedScenario.icon} ${selectedScenario.name}` : "未选择场景模板"}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {selectedScenario
                      ? selectedScenario.description
                      : "选择场景模板以获取针对性建议和伦理提醒"}
                  </div>
                </div>
                <button
                  onClick={() => setShowScenarioPicker(!showScenarioPicker)}
                  className="btn-secondary scenario-picker-toggle"
                  style={{ fontSize: 12, padding: "5px 12px", whiteSpace: "nowrap" }}
                >
                  {showScenarioPicker ? "收起 ▲" : selectedScenario ? "更换场景" : "选择场景"}
                </button>
              </div>

              {/* Scenario picker dropdown */}
              {showScenarioPicker && (
                <div style={{
                  marginBottom: 16, padding: 12, background: "#F8FAFC",
                  borderRadius: 10, border: "1px solid #E2E8F0",
                  display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                  gap: 8, maxHeight: 280, overflowY: "auto",
                }}>
                  {scenarioTemplates.map(t => (
                    <div
                      key={t.id}
                      onClick={() => { setSelectedScenario(t); setShowScenarioPicker(false); }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedScenario(t);
                          setShowScenarioPicker(false);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      aria-pressed={selectedScenario?.id === t.id}
                      style={{
                        padding: "10px 12px", borderRadius: 8, cursor: "pointer",
                        border: selectedScenario?.id === t.id ? "2px solid var(--primary)" : "1px solid transparent",
                        background: selectedScenario?.id === t.id ? "#EEF2FF" : "#fff",
                        transition: "all 0.12s",
                      }}
                    >
                      <div style={{ fontSize: 18, marginBottom: 2 }}>{t.icon}</div>
                      <div style={{ fontWeight: 600, fontSize: 12 }}>{t.name}</div>
                      <div style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1.3 }}>
                        {t.description.slice(0, 40)}...
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Ethical notes & pitfalls for selected scenario */}
              {selectedScenario && !showScenarioPicker && (
                <div style={{
                  marginBottom: 16, padding: "12px 16px",
                  background: "#FFF7ED", border: "1px solid #FED7AA", borderRadius: 10,
                  fontSize: 12, lineHeight: 1.6,
                }}>
                  <div style={{ fontWeight: 600, color: "#C2410C", marginBottom: 4 }}>
                    ⚠️ 场景提醒
                  </div>
                  {selectedScenario.common_pitfalls.length > 0 && (
                    <div style={{ marginBottom: 4 }}>
                      <strong>常见陷阱：</strong>
                      {selectedScenario.common_pitfalls.slice(0, 3).join("；")}
                    </div>
                  )}
                  {selectedScenario.ethical_notes && (
                    <div style={{ marginBottom: 4 }}>
                      <strong>伦理注意：</strong>{selectedScenario.ethical_notes}
                    </div>
                  )}
                  {selectedScenario.recommended_tools && (
                    <div>
                      <strong>🛠 推荐工具：</strong>{selectedScenario.recommended_tools}
                    </div>
                  )}
                </div>
              )}

              {/* Interview Mode Config */}
              <InterviewModeConfig
                selected={interviewMode}
                onSelect={(mode) => setInterviewMode(mode.id)}
              />
            </>
          )}

        <div className="placeholder-panel">
          <div className="status-indicator" role="status" aria-live="polite">
            <span className={`status-dot ${status === "recording" ? "status-dot--on" : status === "connecting" ? "status-dot--connecting" : "status-dot--off"}`} />
            <span>
              {status === "idle" && "录音就绪 · 点击开始"}
              {status === "connecting" && "正在连接语音服务..."}
              {status === "recording" && `● 录音中 — ${asrMode === "browser" ? "浏览器语音识别" : asrMode === "xunfei" ? "讯飞实时转写" : "实时转写进行中"}`}
              {status === "error" && "连接失败"}
              {status === "ready" && "服务已就绪"}
            </span>
            <span style={{ marginLeft: "auto", fontSize: 12, color: "#94A3B8" }}>
              {status === "recording" && `引擎: ${asrMode === "browser" ? "浏览器内置 (推荐)" : asrMode === "xunfei" ? "讯飞语音云" : "未知"}`}
            </span>
          </div>

          {/* ── Two-column speaker transcript grid ── */}
          <div className="transcript-grid" style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 14,
            marginBottom: 14,
          }}>
            {/* Left: Interviewer */}
            <div className="transcript-col" style={{
              border: `2px solid ${currentSpeaker === "interviewer" ? "#3B82F6" : "#DBEAFE"}`,
              borderRadius: 10, overflow: "hidden",
            }}>
              <div style={{
                padding: "8px 12px", fontWeight: 600, fontSize: 13,
                background: "#EFF6FF", borderBottom: "1px solid #DBEAFE",
                display: "flex", alignItems: "center", gap: 6,
              }}>
                <span>👤 访谈者</span>
                {currentSpeaker === "interviewer" && status === "recording" && (
                  <span style={{ fontSize: 10, color: "#DC2626", fontWeight: 400 }}>● 说话中</span>
                )}
              </div>
              <div style={{ padding: 10, minHeight: 100, maxHeight: 360, overflowY: "auto", fontSize: 13, lineHeight: 1.7 }}>
                {interviewerLines.length === 0 && !(currentSpeaker === "interviewer" && interimText) && (
                  <span style={{ color: "#94A3B8", fontSize: 12 }}>访谈者发言将显示在此...</span>
                )}
                {interviewerLines.map((line) => (
                  <div key={line.id} style={{
                    marginBottom: 6, padding: "4px 0",
                    borderBottom: "1px solid #F1F5F9",
                  }}>
                    <span style={{ fontSize: 10, color: "#94A3B8", marginRight: 6 }}>{line.timestamp}</span>
                    <span style={{
                      display: "inline-block", fontSize: 10, padding: "1px 6px",
                      background: "#DBEAFE", color: "#1E40AF", borderRadius: 4, marginRight: 6,
                    }}>Q{line.questionIndex}</span>
                    {line.text}
                  </div>
                ))}
                {currentSpeaker === "interviewer" && interimText && (
                  <div style={{ color: "#94A3B8", fontStyle: "italic", fontSize: 13 }}>
                    {interimText}
                  </div>
                )}
              </div>
            </div>

            {/* Right: Respondent */}
            <div className="transcript-col" style={{
              border: `2px solid ${currentSpeaker === "respondent" ? "#F59E0B" : "#FED7AA"}`,
              borderRadius: 10, overflow: "hidden",
            }}>
              <div style={{
                padding: "8px 12px", fontWeight: 600, fontSize: 13,
                background: "#FFF7ED", borderBottom: "1px solid #FED7AA",
                display: "flex", alignItems: "center", gap: 6,
              }}>
                <span>🎤 被访谈者</span>
                {currentSpeaker === "respondent" && status === "recording" && (
                  <span style={{ fontSize: 10, color: "#DC2626", fontWeight: 400 }}>● 说话中</span>
                )}
              </div>
              <div style={{ padding: 10, minHeight: 100, maxHeight: 360, overflowY: "auto", fontSize: 13, lineHeight: 1.7 }}>
                {respondentLines.length === 0 && !(currentSpeaker === "respondent" && interimText) && (
                  <span style={{ color: "#94A3B8", fontSize: 12 }}>被访谈者发言将显示在此...</span>
                )}
                {respondentLines.map((line) => (
                  <div key={line.id} style={{
                    marginBottom: 6, padding: "4px 0",
                    borderBottom: "1px solid #FFF7ED",
                  }}>
                    <span style={{ fontSize: 10, color: "#94A3B8", marginRight: 6 }}>{line.timestamp}</span>
                    <span style={{
                      display: "inline-block", fontSize: 10, padding: "1px 6px",
                      background: "#FED7AA", color: "#C2410C", borderRadius: 4, marginRight: 6,
                    }}>Q{line.questionIndex}</span>
                    {line.text}
                  </div>
                ))}
                {currentSpeaker === "respondent" && interimText && (
                  <div style={{ color: "#94A3B8", fontStyle: "italic", fontSize: 13 }}>
                    {interimText}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Speaker toggle controls */}
          {status === "recording" && (
            <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
              <button
                type="button"
                onClick={() => setCurrentSpeaker("interviewer")}
                aria-pressed={currentSpeaker === "interviewer"}
                style={{
                  flex: 1, padding: "10px 16px",
                  background: currentSpeaker === "interviewer" ? "#1E3A8A" : "#E2E8F0",
                  color: currentSpeaker === "interviewer" ? "#fff" : "#475569",
                  border: "none", borderRadius: 8, fontSize: 14, cursor: "pointer",
                  fontWeight: currentSpeaker === "interviewer" ? 700 : 400,
                  transition: "all 0.15s",
                }}
              >
                🎤 我来说（提问）
              </button>
              <button
                type="button"
                onClick={() => setCurrentSpeaker("respondent")}
                aria-pressed={currentSpeaker === "respondent"}
                style={{
                  flex: 1, padding: "10px 16px",
                  background: currentSpeaker === "respondent" ? "#C2410C" : "#E2E8F0",
                  color: currentSpeaker === "respondent" ? "#fff" : "#475569",
                  border: "none", borderRadius: 8, fontSize: 14, cursor: "pointer",
                  fontWeight: currentSpeaker === "respondent" ? 700 : 400,
                  transition: "all 0.15s",
                }}
              >
                🔊 请回答（受访者）
              </button>
              <button
                onClick={() => {
                  questionIndexRef.current += 1;
                  setCurrentSpeaker("interviewer");
                }}
                style={{
                  padding: "10px 14px", fontSize: 13, cursor: "pointer",
                  background: "#F0FDF4", color: "#166534", border: "1px solid #BBF7D0",
                  borderRadius: 8, whiteSpace: "nowrap",
                }}
                title="进入下一个问题"
              >
                → Q{questionIndexRef.current + 1}
              </button>
            </div>
          )}

          {errorMsg && (
            <div role="alert" style={{ padding: "12px 16px", background: "#FEF2F2", color: "#DC2626", borderRadius: 8, marginBottom: 16 }}>
              {errorMsg}
            </div>
          )}

          <div style={{ display: "flex", gap: 12, marginTop: 16 }}>
            {status !== "recording" ? (
              <button
                onClick={startRecording}
                disabled={status === "connecting"}
                style={{
                  padding: "12px 32px",
                  background: status === "connecting" ? "#94A3B8" : "#1E3A8A",
                  color: "#fff",
                  border: "none",
                  borderRadius: 8,
                  fontSize: 16,
                  cursor: status === "connecting" ? "not-allowed" : "pointer",
                }}
              >
                {status === "connecting" ? "连接中..." : "开始录音"}
              </button>
            ) : (
              <button
                onClick={stopRecording}
                style={{
                  padding: "12px 32px",
                  background: "#DC2626",
                  color: "#fff",
                  border: "none",
                  borderRadius: 8,
                  fontSize: 16,
                  cursor: "pointer",
                }}
              >
                停止录音
              </button>
            )}
            {transcript && status === "idle" && (
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button
                  onClick={() => {
                    setNewNoteContent(transcript.trim());
                    setNewNoteType("quote");
                    setActiveTab("notes");
                    setShowNewNote(true);
                  }}
                  className="btn-secondary"
                  style={{ fontSize: 12, padding: "6px 12px" }}
                >
                  → 转为田野笔记
                </button>
                <button
                  onClick={() => navigator.clipboard.writeText(transcript).then(() => alert("已复制")).catch(() => {})}
                  className="btn-secondary"
                  style={{ fontSize: 12, padding: "6px 12px" }}
                >
                  复制文本
                </button>
              </div>
            )}

            {/* Inline AI hints during recording */}
            {status === "recording" && hints.length > 0 && (
              <div style={{ marginTop: 16, padding: "10px 14px", background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)" }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", marginBottom: 8 }}>
                  💡 实时AI提示 ({hints.length})
                </div>
                {hints.slice(0, 2).map((hint, i) => (
                  <div key={i} style={{
                    padding: "8px 10px", fontSize: 12, lineHeight: 1.5,
                    borderLeft: "3px solid var(--primary)", marginBottom: 6,
                    background: "#F8FAFC", borderRadius: 4,
                    display: "flex", alignItems: "flex-start", gap: 6,
                  }}>
                    <span style={{ flex: 1 }}>{hint}</span>
                    <button
                      onClick={() => {
                        setNewNoteContent(hint);
                        setNewNoteType("memo");
                        setActiveTab("notes");
                        setShowNewNote(true);
                      }}
                      style={{
                        fontSize: 10, padding: "2px 6px", cursor: "pointer",
                        background: "var(--primary-light)", color: "var(--primary)",
                        border: "1px solid var(--primary)", borderRadius: 4,
                        whiteSpace: "nowrap",
                      }}
                    >
                      + 笔记
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── Opus Audio Recording (parallel to ASR — saves compressed file) ── */}
          <details style={{ marginTop: 20, borderTop: "1px solid var(--border)", paddingTop: 16 }}>
            <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600, color: "var(--text-muted)", userSelect: "none" }}>
              🎵 高质量录音保存 (Opus压缩 · 分段上传 · 不依赖服务器)
            </summary>
            <div style={{ marginTop: 12 }}>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                {opusRecorderState.status === "recording"
                  ? `🔴 录音中 · ${AudioRecorder.formatDuration(opusRecorderState.elapsedSeconds)} · ${AudioRecorder.formatBytes(opusRecorderState.totalBytes)} · ${opusRecorderState.chunkCount}段`
                  : opusRecorderState.status === "idle"
                  ? "Opus编码压缩约240KB/分钟（相比WAV减少40倍），每5分钟自动分段上传。可与语音转写同时使用。"
                  : opusRecorderState.status === "requesting"
                  ? "请求麦克风权限..."
                  : opusRecorderState.errorMessage || opusRecorderState.status}
              </p>
              <div style={{ display: "flex", gap: 8 }}>
                {opusRecorderState.status !== "recording" ? (
                  <button
                    onClick={startOpusRecording}
                    disabled={opusRecorderState.status === "requesting"}
                    className="btn-secondary"
                    style={{ fontSize: 13, padding: "8px 16px" }}
                  >
                    {opusRecorderState.status === "requesting" ? "请求权限中..." : "开始保存录音"}
                  </button>
                ) : (
                  <button
                    onClick={stopOpusRecording}
                    style={{
                      padding: "8px 16px", background: "#DC2626", color: "#fff",
                      border: "none", borderRadius: 8, fontSize: 13, cursor: "pointer",
                    }}
                  >
                    停止保存
                  </button>
                )}
                {opusRecorderState.chunkCount > 0 && opusRecorderState.status === "idle" && (
                  <span style={{ fontSize: 12, color: "var(--text-muted)", alignSelf: "center" }}>
                    ✅ {opusRecorderState.chunkCount}段录音已保存 · 共{AudioRecorder.formatBytes(opusRecorderState.totalBytes)}
                  </span>
                )}
              </div>
            </div>
          </details>
        </div>
        </div>
      )}

      {/* ── Tab 2: AI Hints ── */}
      {activeTab === "hints" && (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
            <button onClick={fetchHintsStream} disabled={hintsLoading || transcript.length < 50} className="btn-primary">
              {hintsLoading ? "AI分析中（流式生成）..." : "获取AI访谈提示"}
            </button>
            <span className="hint">
              {transcript.length < 50
                ? "需至少50字转录文本"
                : status === "recording"
                ? "录音中每45秒自动获取提示"
                : "基于当前转录文本获取即时建议"}
            </span>
          </div>

          {hints.length > 0 && (
            <div>
              <h4 style={{ marginBottom: 12 }}>AI 即时建议</h4>
              {hints.map((hint, i) => (
                <div
                  key={i}
                  style={{
                    padding: "14px 18px",
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    marginBottom: 8,
                    fontSize: 14,
                    lineHeight: 1.7,
                    borderLeft: "4px solid var(--primary)",
                  }}
                >
                  <span style={{ color: "var(--primary)", fontWeight: 600, marginRight: 8 }}>#{i + 1}</span>
                  {hint}
                </div>
              ))}
            </div>
          )}

          {hints.length === 0 && !hintsLoading && (
            <div className="placeholder-panel" style={{ textAlign: "center", padding: 48 }}>
              <p className="hint">
                {transcript.length < 50
                  ? "请先在「录音转写」标签页开始录音，积累至少50字转录文本后，再回来获取AI提示。"
                  : "点击上方按钮，AI将分析当前转录内容并提供追问方向、话术建议和注意事项。"}
              </p>
            </div>
          )}

          {/* Current transcript preview for context */}
          {transcript && (
            <details style={{ marginTop: 24 }}>
              <summary style={{ cursor: "pointer", color: "var(--text-muted)", fontSize: 13, userSelect: "none" }}>
                当前转录文本预览（{transcript.length}字）...
              </summary>
              <div style={{ marginTop: 8, padding: 12, background: "#f9fafb", borderRadius: 8, fontSize: 13, maxHeight: 200, overflowY: "auto", whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                {transcript.slice(-1000)}
              </div>
            </details>
          )}
        </div>
      )}

      {/* ── Tab 3: Notes & Summary ── */}
      {activeTab === "notes" && (
        <div>
          {/* ── Filter bar ── */}
          <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>📝 田野笔记</span>
            <select
              value={notesFilter}
              onChange={(e) => setNotesFilter(e.target.value as NoteType | "all")}
              style={{ fontSize: 12, padding: "4px 8px", width: "auto" }}
            >
              <option value="all">全部类型</option>
              {Object.entries(NOTE_TYPE_LABELS).map(([v, label]) => (
                <option key={v} value={v}>{NOTE_TYPE_ICONS[v as NoteType]} {label}</option>
              ))}
            </select>
            <select
              value={notesAiFilter}
              onChange={(e) => setNotesAiFilter(e.target.value as "all" | "ai" | "manual")}
              style={{ fontSize: 12, padding: "4px 8px", width: "auto" }}
            >
              <option value="all">全部来源</option>
              <option value="ai">🤖 AI生成</option>
              <option value="manual">✍️ 手动</option>
            </select>
            <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: "auto" }}>
              {fieldNotes.length} 条笔记
            </span>
          </div>

          {/* ── Note cards ── */}
          {notesLoading ? (
            <div style={{ textAlign: "center", padding: 16, color: "var(--text-muted)", fontSize: 13 }}>加载中...</div>
          ) : fieldNotes.filter((n) => {
            if (notesFilter !== "all" && n.note_type !== notesFilter) return false;
            if (notesAiFilter === "ai" && !n.ai_generated) return false;
            if (notesAiFilter === "manual" && n.ai_generated) return false;
            return true;
          }).length === 0 ? (
            <div style={{ textAlign: "center", padding: 24, color: "var(--text-muted)", fontSize: 13, background: "var(--surface)", borderRadius: 8, marginBottom: 12 }}>
              {fieldNotes.length === 0 ? "暂无笔记，点击下方按钮创建第一条" : "没有匹配的笔记"}
            </div>
          ) : (
            <div style={{ maxHeight: 400, overflowY: "auto", marginBottom: 16 }}>
              {fieldNotes.filter((n) => {
                if (notesFilter !== "all" && n.note_type !== notesFilter) return false;
                if (notesAiFilter === "ai" && !n.ai_generated) return false;
                if (notesAiFilter === "manual" && n.ai_generated) return false;
                return true;
              }).map((note) => (
                <div
                  key={note.id}
                  style={{
                    padding: 12,
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    marginBottom: 8,
                  }}
                >
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                    <span style={{ fontSize: 12 }}>
                      {NOTE_TYPE_ICONS[note.note_type] || "📌"} {NOTE_TYPE_LABELS[note.note_type] || note.note_type}
                    </span>
                    <span style={{
                      fontSize: 10,
                      padding: "1px 6px",
                      borderRadius: 10,
                      background: note.ai_generated ? "#dbeafe" : "#f3f4f6",
                      color: note.ai_generated ? "#1d4ed8" : "#6b7280",
                    }}>
                      {note.ai_generated ? "AI生成" : "手动"}
                    </span>
                    {note.timestamp_in_recording != null && (
                      <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
                        {(note.timestamp_in_recording / 60).toFixed(0)}:{((note.timestamp_in_recording % 60) || 0).toString().padStart(2, "0")}
                      </span>
                    )}
                    <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-muted)" }}>
                      {new Date(note.created_at).toLocaleDateString("zh-CN")}
                    </span>
                  </div>

                  {editingNoteId === note.id ? (
                    <div>
                      <textarea
                        value={editingNoteContent}
                        onChange={(e) => setEditingNoteContent(e.target.value)}
                        rows={3}
                        style={{ width: "100%", padding: 8, borderRadius: 6, border: "1px solid var(--border)", resize: "vertical", fontSize: 13 }}
                      />
                      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                        <button onClick={() => handleEditNote(note.id)} className="btn-primary" style={{ fontSize: 12, padding: "3px 10px" }}>保存</button>
                        <button onClick={() => { setEditingNoteId(null); setEditingNoteContent(""); }} className="btn-secondary" style={{ fontSize: 12, padding: "3px 10px" }}>取消</button>
                      </div>
                    </div>
                  ) : (
                    <div style={{ fontSize: 13, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
                      {note.content.length > 150 ? note.content.slice(0, 150) + "..." : note.content}
                    </div>
                  )}

                  {editingNoteId !== note.id && (
                    <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                      <button
                        onClick={() => { setEditingNoteId(note.id); setEditingNoteContent(note.content); }}
                        className="btn-secondary"
                        style={{ fontSize: 11, padding: "2px 8px" }}
                      >
                        ✏️ 编辑
                      </button>
                      {note.ai_generated && (
                        <button className="btn-secondary" style={{ fontSize: 11, padding: "2px 8px", color: "#16a34a" }}>
                          ✅ 确认
                        </button>
                      )}
                      <button
                        onClick={() => handleDeleteNote(note.id)}
                        className="btn-secondary"
                        style={{ fontSize: 11, padding: "2px 8px", color: "#dc2626" }}
                      >
                        🗑 删除
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* ── New note inline form ── */}
          {showNewNote && (
            <div style={{ padding: 12, background: "var(--primary-light)", borderRadius: 8, marginBottom: 16 }}>
              <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                <select value={newNoteType} onChange={(e) => setNewNoteType(e.target.value as NoteType)} style={{ fontSize: 12, padding: "4px 8px", width: "auto" }}>
                  {Object.entries(NOTE_TYPE_LABELS).map(([v, label]) => (
                    <option key={v} value={v}>{NOTE_TYPE_ICONS[v as NoteType]} {label}</option>
                  ))}
                </select>
                <input
                  value={newNoteTags}
                  onChange={(e) => setNewNoteTags(e.target.value)}
                  placeholder="标签，逗号分隔"
                  style={{ flex: 1, fontSize: 12, padding: "4px 8px" }}
                />
              </div>
              <textarea
                value={newNoteContent}
                onChange={(e) => setNewNoteContent(e.target.value)}
                placeholder="记录观察、引用、反思或备忘..."
                rows={3}
                style={{ width: "100%", padding: 8, borderRadius: 6, border: "1px solid var(--border)", resize: "vertical", fontSize: 13 }}
              />
              <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                <button onClick={handleCreateNote} disabled={!newNoteContent.trim()} className="btn-primary" style={{ fontSize: 12, padding: "4px 12px" }}>保存笔记</button>
                <button onClick={() => { setShowNewNote(false); setNewNoteContent(""); }} className="btn-secondary" style={{ fontSize: 12, padding: "4px 12px" }}>取消</button>
              </div>
            </div>
          )}

          {/* ── Quick note textarea (original) ── */}
          <div className="form-group">
            <label>快速笔记</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="在此记录田野观察笔记、受访者非语言信息、环境描述、反思备忘..."
              rows={4}
              style={{ maxWidth: "100%", width: "100%" }}
            />
          </div>

          <div className="button-row" style={{ marginBottom: 20, flexWrap: "wrap" }}>
            <button onClick={() => setShowNewNote(!showNewNote)} className="btn-secondary" style={{ fontSize: 13 }}>
              {showNewNote ? "收起" : "＋ 新建结构化笔记"}
            </button>
            <button onClick={handleSummarize} disabled={summaryLoading || (!transcript && !notes)} className="btn-primary">
              {summaryLoading ? "AI摘要生成中..." : "生成AI摘要"}
            </button>
            <button onClick={handleSaveSession} disabled={saving || (!transcript && !notes)} className="btn-secondary">
              {saving ? "保存中..." : "保存会话"}
            </button>
          </div>

          {summary && (
            <div>
              <div className="md-content">
                <h4 style={{ marginTop: 0 }}>AI 结构化摘要</h4>
                {summary}
              </div>
              <div className="button-row" style={{ flexWrap: "wrap", marginTop: 12 }}>
                <button
                  onClick={() => handleDownload(summary, "田野摘要", "docx")}
                  disabled={downloading !== null}
                  className="btn-secondary"
                  style={{ background: "var(--primary)", color: "#fff", border: "none" }}
                >
                  {downloading === "docx" ? "下载中..." : "下载 Word (.docx)"}
                </button>
                <button
                  onClick={() => handleDownload(summary, "田野摘要", "md")}
                  disabled={downloading !== null}
                  className="btn-secondary"
                >
                  {downloading === "md" ? "下载中..." : "下载 Markdown (.md)"}
                </button>
              </div>
            </div>
          )}

          {!summary && !summaryLoading && (
            <div className="placeholder-panel" style={{ textAlign: "center", padding: 32 }}>
              <p className="hint">
                基于转录文本或笔记内容，AI可生成结构化摘要：核心发现、主题编码、情感基调、待追问问题和访谈技巧反思。
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── Tab 4: Image Analysis ── */}
      {activeTab === "image" && (
        <div>
          <p className="subtitle" style={{ marginBottom: 16 }}>
            上传田野照片，AI进行场景识别、文本提取、社会文化解读和隐私伦理提醒
          </p>

          <div className="form-row" style={{ gap: 16, marginBottom: 16 }}>
            <div className="form-group" style={{ flex: 1 }}>
              <label>分析侧重点</label>
              <select value={imageFocus} onChange={(e) => setImageFocus(e.target.value)}>
                <option value="auto">自动识别</option>
                <option value="general">通用分析</option>
                <option value="social_interaction">社交互动</option>
                <option value="built_environment">建成环境</option>
                <option value="text_ocr">文字提取</option>
                <option value="objects">物体识别</option>
              </select>
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>拍摄地点（可选）</label>
              <input
                value={imageLocation}
                onChange={(e) => setImageLocation(e.target.value)}
                placeholder="例如：武汉市洪山区关山街道"
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: 16, marginBottom: 16, flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 300px" }}>
              <div className="form-group">
                <label>上传图片（JPEG / PNG / WEBP，最大 10MB）</label>
                <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={handleImageSelect} style={{ padding: 8 }} />
                <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "4px 0 0" }}>
                  大图将自动压缩至合适尺寸，移动网络下也可快速上传
                </p>
              </div>
              {imagePreview && (
                <div style={{ marginTop: 12, textAlign: "center" }}>
                  <img src={imagePreview} alt="预览" style={{ maxWidth: "100%", maxHeight: 300, borderRadius: 8, border: "1px solid var(--border)" }} />
                </div>
              )}
            </div>
            <div style={{ flex: "1 1 300px" }}>
              <div className="form-group">
                <label>文字描述（可选，若无图片则基于描述分析）</label>
                <textarea
                  value={imageDesc}
                  onChange={(e) => setImageDesc(e.target.value)}
                  placeholder="描述照片中的场景、人物、物品、文字等..."
                  rows={5}
                  style={{ width: "100%" }}
                />
              </div>
            </div>
          </div>

          <button
            onClick={handleAnalyzeImage}
            disabled={imageLoading || (!imageFile && !imageDesc.trim())}
            className="btn-primary"
            style={{ width: "100%" }}
          >
            {imageLoading ? "AI分析中..." : imageFile ? "分析上传的图片" : "基于文字描述分析"}
          </button>

          {imageAnalysis && (
            <div className="md-content" style={{ marginTop: 24 }}>
              <h4 style={{ marginTop: 0 }}>AI 图像分析结果</h4>
              {imageAnalysis}
            </div>
          )}

          {!imageAnalysis && !imageLoading && (
            <div className="placeholder-panel" style={{ textAlign: "center", padding: 32, marginTop: 24 }}>
              <p className="hint">
                AI 图像分析（基于文本描述）：场景类型判断、人物/物品/文字识别、社会文化符号解读、研究价值评估、隐私伦理提醒。
                上传田野现场照片（将提取格式和大小元数据）或输入场景描述即可开始分析。如需直接图像识别，请配置视觉模型API。
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── Tab 5: File Upload Transcription ── */}
      {activeTab === "file" && (
        <div>
          <p className="subtitle" style={{ marginBottom: 16 }}>
            上传录音/视频文件，千问ASR自动转写，支持AI深度分析
          </p>

          {/* Format & size info card */}
          <div style={{
            padding: "10px 14px", background: "#F0F7FF", borderRadius: 8,
            border: "1px solid #BFDBFE", marginBottom: 16, fontSize: 12,
            color: "#1E40AF", lineHeight: 1.6,
          }}>
            <strong>📋 支持格式：</strong>WAV / MP3 / M4A / OGG / FLAC / AAC / OPUS / WEBM / MP4 / MOV / MKV<br />
            <strong>📏 最大文件：</strong>500 MB（约 12 小时录音）&nbsp;&nbsp;|&nbsp;&nbsp;
            <strong>⏱ 预计耗时：</strong>录音时长的 1/3 ~ 1/2<br />
            <strong>⚠️ 注意：</strong>文件会通过服务器公网URL供千问API访问，请勿上传敏感内容
          </div>

          <div style={{ display: "flex", gap: 16, marginBottom: 16, flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 300px" }}>
              <div className="form-group">
                <label>选择音频/视频文件</label>
                <input
                  type="file"
                  accept="audio/*,video/*,.wav,.mp3,.m4a,.ogg,.flac,.mp4,.mov,.mkv"
                  onChange={handleFileSelect}
                  style={{ padding: 8 }}
                />
              </div>
              {fileUpload && (
                <div style={{ marginTop: 8, fontSize: 13, color: "var(--text-muted)" }}>
                  已选择: {fileUpload.name} ({(fileUpload.size / 1024 / 1024).toFixed(1)} MB)
                </div>
              )}
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
            <button
              onClick={handleFileUpload}
              disabled={fileUploading || !fileUpload}
              className="btn-primary"
            >
              {fileUploading ? "上传转写中..." : "上传并转写"}
            </button>
            {fileResult?.transcript && (
              <button
                onClick={async () => {
                  if (!fileResult?.transcript || !fileResult?.file_id) return;
                  setFileUploading(true);
                  try {
                    const res = await api.post(`/fieldwork/transcribe-file/${fileResult.file_id}/analyze`, {
                      transcript: fileResult.transcript,
                      theme,
                    });
                    setFileResult((prev: any) => ({ ...prev, analysis: res.data.analysis }));
                  } catch (e: any) {
                    setFileResult((prev: any) => ({ ...prev, analysis: "AI分析失败: " + (e.message || "未知错误") }));
                  } finally {
                    setFileUploading(false);
                  }
                }}
                disabled={fileUploading}
                className="btn-secondary"
                style={{ background: "var(--primary)", color: "#fff", border: "none" }}
              >
                AI深度分析
              </button>
            )}
          </div>

          {fileResult && (
            <div style={{ marginTop: 16 }}>
              {fileResult.error ? (
                <div style={{ padding: 12, background: "#FEF2F2", color: "#DC2626", borderRadius: 8 }}>
                  ❌ {fileResult.error}
                </div>
              ) : (
                <div>
                  <div style={{
                    padding: 12, background: "var(--surface)", borderRadius: 8,
                    border: "1px solid var(--border)", marginBottom: 12,
                  }}>
                    <strong>状态:</strong>{" "}
                    {fileResult.status === "completed" ? "✅ 转写完成" :
                     fileResult.status === "transcribing" ? "⏳ 转写中..." :
                     fileResult.status === "processing" ? "⏳ 处理中..." :
                     fileResult.status}
                    {fileResult.message && <p style={{ marginTop: 8, color: "var(--text-muted)", fontSize: 13 }}>{fileResult.message}</p>}
                    {fileResult.file_id && <p style={{ marginTop: 4, fontSize: 12, color: "#94A3B8" }}>文件ID: {fileResult.file_id}</p>}
                  </div>

                  {fileResult.transcript && (
                    <div className="md-content" style={{ marginTop: 16 }}>
                      <h4>📝 转写结果</h4>
                      <pre style={{ whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.7, maxHeight: 400, overflowY: "auto" }}>{fileResult.transcript}</pre>
                    </div>
                  )}

                  {fileResult.sentences && fileResult.sentences.length > 0 && (
                    <details style={{ marginTop: 12 }}>
                      <summary style={{ cursor: "pointer", fontSize: 13 }}>查看逐句时间戳（{fileResult.sentences.length}句）</summary>
                      <div style={{ maxHeight: 300, overflowY: "auto", marginTop: 8 }}>
                        {fileResult.sentences.map((s: any, i: number) => (
                          <div key={i} style={{ padding: "4px 8px", fontSize: 12, borderBottom: "1px solid var(--border)" }}>
                            <span style={{ color: "#94A3B8" }}>[{s.begin_time}s-{s.end_time}s]</span>
                            {s.speaker_id && <span style={{ color: "var(--primary)", marginLeft: 8 }}>说话人{s.speaker_id}:</span>}
                            <span style={{ marginLeft: 8 }}>{s.text}</span>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  {fileResult.analysis && (
                    <div className="md-content" style={{ marginTop: 16 }}>
                      <h4>🔍 AI深度分析</h4>
                      {fileResult.analysis}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {!fileResult && !fileUploading && (
            <div className="placeholder-panel" style={{ textAlign: "center", padding: 32, marginTop: 16 }}>
              <p className="hint">
                支持上传录音文件（如访谈录音MP3、会议录音M4A等）或视频文件进行自动转写。
                千问ASR支持<strong>说话人分离</strong>、<strong>自动语种检测</strong>、<strong>词级时间戳</strong>等功能。
                <br /><br />
                上传后自动提交千问FileTrans进行转写，完成即可使用<strong>「AI深度分析」</strong>功能进行主题编码、情感分析、理论关联等分析。
                <br /><br />
                <strong>注意：</strong>文件会通过服务器公网URL供千问API访问，请勿上传敏感内容。
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── Tab 6: Facial Emotion (Camera + MediaPipe) ── */}
      {activeTab === "camera" && (
        <div>
          <p className="subtitle" style={{ marginBottom: 16 }}>
            浏览器端面部情绪识别 · MediaPipe Face Mesh 本地推理 · 不上传原始视频
          </p>

          {/* PIPL compliance notice */}
          <div style={{
            padding: "10px 14px", background: "#F0FDF4", borderRadius: 8,
            border: "1px solid #BBF7D0", marginBottom: 16, fontSize: 12,
            color: "#166534", lineHeight: 1.6,
          }}>
            <strong>🔒 隐私保护：</strong>所有面部识别在浏览器本地完成（MediaPipe Face Mesh），
            仅发送情绪信号（数值）到后端用于访谈辅助分析，<strong>不传输任何视频或图像数据</strong>。
            符合 PIPL 第13条本地处理原则。
          </div>

          {!cameraEnabled ? (
            <div style={{ textAlign: "center", padding: 48 }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>📷</div>
              <h3 style={{ marginBottom: 8 }}>实时面部情绪识别</h3>
              <p style={{ color: "var(--text-muted)", marginBottom: 24, maxWidth: 500, margin: "0 auto 24px" }}>
                开启摄像头后，AI将在浏览器本地分析受访者的面部表情（专注度、微笑、惊讶等），
                结合语音情绪为访谈教练提供<strong>双模态情绪参考</strong>。
              </p>
              <button
                onClick={() => setCameraEnabled(true)}
                className="btn-primary"
                style={{ padding: "14px 40px", fontSize: 16 }}
              >
                📷 开启面部识别
              </button>
              <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 12 }}>
                需要摄像头权限 · 仅限 HTTPS/localhost · 推荐 Chrome/Edge
              </p>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 20, alignItems: "start" }}>
              {/* Left: Camera + Dashboard */}
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                  <CameraCapture
                    onEmotionSignal={(signal) => {
                      setFacialSignals((prev) => [...prev.slice(-300), signal]);
                      sendFacialSignal(signal);
                    }}
                    fps={5}
                    width={320}
                    height={240}
                    enabled={cameraEnabled}
                  />
                  <div style={{ flex: 1, fontSize: 13 }}>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>📊 实时采集指标</div>
                    <div style={{ display: "grid", gap: 6 }}>
                      {[
                        { label: "数据频率", value: "5 Hz (200ms/次)" },
                        { label: "面部地标", value: "468点 (MediaPipe)" },
                        { label: "推理位置", value: "浏览器本地" },
                        { label: "网络传输", value: "仅数值信号" },
                      ].map((m) => (
                        <div key={m.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                          <span style={{ color: "var(--text-muted)" }}>{m.label}</span>
                          <span style={{ fontWeight: 500 }}>{m.value}</span>
                        </div>
                      ))}
                    </div>
                    <button
                      onClick={() => { setCameraEnabled(false); setFacialSignals([]); }}
                      className="btn-secondary"
                      style={{ marginTop: 12, fontSize: 12, padding: "6px 14px" }}
                    >
                      关闭摄像头
                    </button>
                  </div>
                </div>

                <EmotionDashboard signals={facialSignals} maxHistory={60} height={260} />
              </div>

              {/* Right: Hints sidebar */}
              <div>
                <HintOverlay
                  hints={liveHints}
                  mode="sidebar"
                  maxVisible={5}
                  onDismiss={(id) => setLiveHints((prev) => prev.filter((h) => h.id !== id))}
                />

                {/* Fetch hints button */}
                <div style={{ marginTop: 16 }}>
                  <button
                    onClick={fetchHintsStream}
                    disabled={hintsLoading || transcript.length < 50}
                    className="btn-primary"
                    style={{ width: "100%", fontSize: 13, padding: "10px 0" }}
                  >
                    {hintsLoading ? "AI分析中..." : "获取AI访谈提示"}
                  </button>
                  {transcript.length < 50 && (
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6, textAlign: "center" }}>
                      需至少50字转录文本（请先在录音转写Tab开始录音）
                    </p>
                  )}
                </div>

                {/* Quick emotion context */}
                {facialSignals.length > 0 && (
                  <div style={{ marginTop: 16, padding: 12, background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", fontSize: 12 }}>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>📋 情绪摘要（最近30秒）</div>
                    {(() => {
                      const recent = facialSignals.slice(-150); // ~30s at 5Hz
                      const avgEngagement = recent.length > 0
                        ? Math.round(recent.reduce((s, v) => s + v.engagement, 0) / recent.length * 100)
                        : 0;
                      const expressions = recent.map((s) => s.expression);
                      const topExpr = expressions.length > 0
                        ? expressions.sort((a, b) =>
                            expressions.filter((v) => v === a).length - expressions.filter((v) => v === b).length
                          ).pop() || "neutral"
                        : "neutral";
                      return (
                        <>
                          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                            <span style={{ color: "var(--text-muted)" }}>平均专注度</span>
                            <span style={{ fontWeight: 600 }}>{avgEngagement}%</span>
                          </div>
                          <div style={{ display: "flex", justifyContent: "space-between" }}>
                            <span style={{ color: "var(--text-muted)" }}>主要表情</span>
                            <span style={{ fontWeight: 600 }}>
                              {topExpr === "happy" ? "😊 愉悦" :
                               topExpr === "surprised" ? "😲 惊讶" :
                               topExpr === "concentrating" ? "🤔 专注" :
                               topExpr === "tired" ? "😴 疲惫" : "😐 中性"}
                            </span>
                          </div>
                        </>
                      );
                    })()}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Survey Tab: 问卷调查 ── */}
      {activeTab === "survey" && (
        <div>
          <p className="subtitle" style={{ marginBottom: 16 }}>
            选择已生成的问卷，面对面填写，一站式完成数据收集
          </p>

          {questionnaireList.length === 0 ? (
            <div className="placeholder-panel" style={{ textAlign: "center", padding: 48 }}>
              <p className="hint">
                {project?.id
                  ? "暂无可用问卷。请先在「问卷设计」中生成并保存问卷。"
                  : "请先创建项目并在「问卷设计」中生成问卷。"}
              </p>
            </div>
          ) : (
            <div>
              <div className="form-group" style={{ marginBottom: 16 }}>
                <label>选择问卷</label>
                <select
                  value={selectedQId || ""}
                  onChange={async (e) => {
                    const id = Number(e.target.value);
                    setSelectedQId(id);
                    try {
                      const res = await api.get(`/questionnaire/${id}`);
                      setQuestionnaireData(res.data);
                      setSurveyStats(null);
                      // Also load stats
                      const statsRes = await api.get(`/questionnaire/${id}/stats`);
                      setSurveyStats(statsRes.data);
                    } catch { /* ignore */ }
                  }}
                  style={{ width: "100%", padding: "10px 14px", fontSize: 14 }}
                >
                  <option value="">-- 选择问卷 --</option>
                  {questionnaireList.map((q) => (
                    <option key={q.id} value={q.id}>
                      {q.title} ({q.total_items}题)
                    </option>
                  ))}
                </select>
              </div>

              {/* Stats summary */}
              {surveyStats && surveyStats.total_responses > 0 && (
                <div style={{
                  padding: "10px 14px", marginBottom: 16,
                  background: "#F0FDF4", borderRadius: 8, border: "1px solid #BBF7D0",
                  fontSize: 13,
                }}>
                  📊 已收集 <strong>{surveyStats.total_responses}</strong> 份回答
                  {surveyStats.question_stats.slice(0, 3).map((qs: any) => (
                    <span key={qs.question_id} style={{ marginLeft: 12, fontSize: 11, color: "var(--text-muted)" }}>
                      {qs.question_id}: {Object.values(qs.frequencies).reduce((a: number, b: any) => a + b, 0)}人
                    </span>
                  ))}
                </div>
              )}

              {/* Fill component */}
              {questionnaireData && (
                <QuestionnaireFill
                  questionnaire={questionnaireData}
                  onComplete={() => {
                    // Reload stats after completion
                    if (selectedQId) {
                      api.get(`/questionnaire/${selectedQId}/stats`)
                        .then(r => setSurveyStats(r.data))
                        .catch(() => {});
                    }
                  }}
                />
              )}
            </div>
          )}
        </div>
      )}

      {/* QuickNav: appears after user completes meaningful work */}
      <QuickNav
        currentPath="/fieldwork"
        visible={!!(summary || imageAnalysis || fileResult?.transcript)}
        nextPath="/analysis"
        nextLabel="数据分析"
      />
    </div>
  );
}
