import { useState, useCallback } from "react";
import api from "../api/client";
import { DIM_LABELS_MAP } from "../types/spectrum";
import { getErrorMessage } from "../utils/errors";

/* ── Types ─────────────────────────────────────────────────────────── */

interface ReflectionQuestion {
  id: string; prompt: string; tradition: string; spectrum_touch: string;
}
interface Insight {
  dimension: string; direction: number; confidence: number; rationale: string;
}
interface SpectrumShift {
  dimension: string; current_value: number | null; direction: number;
  confidence: number; rationale: string;
}
interface ReflectionState {
  session_id: string; title: string; intro: string;
  current_question: ReflectionQuestion | null; total_questions: number; question_number: number;
}
interface ConcludeState {
  summary: string; insights: Insight[]; spectrum_shifts: SpectrumShift[]; total_questions: number;
}

const TRADITION_LABELS: Record<string, string> = {
  ethnomethodology: "常人方法学", pragmatism: "法国实用主义", bourdieu: "反思社会学",
};

/* ── Props ─────────────────────────────────────────────────────────── */
interface ReflectionPanelProps {
  theme?: string; profileId: number; projectId?: number;
  sourceSessionId?: number; onComplete?: (c: ConcludeState) => void; className?: string;
}

/* ── Component ─────────────────────────────────────────────────────── */
export default function ReflectionPanel({ profileId, projectId, sourceSessionId, onComplete, className = "" }: ReflectionPanelProps) {
  const [phase, setPhase] = useState<"idle" | "intro" | "answering" | "concluding" | "done">("idle");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [session, setSession] = useState<ReflectionState | null>(null);
  const [answer, setAnswer] = useState("");
  const [followup, setFollowup] = useState("");
  const [conclusion, setConclusion] = useState<ConcludeState | null>(null);

  const start = useCallback(async (triggerType: string) => {
    setLoading(true); setError("");
    try {
      const { data } = await api.post("/reflection/start", { trigger_type: triggerType, profile_id: profileId, project_id: projectId, source_session_id: sourceSessionId });
      if (data.error) { setError(data.error); return; }
      setSession(data); setPhase("intro");
    } catch (error: unknown) { setError(getErrorMessage(error, "启动失败")); }
    finally { setLoading(false); }
  }, [profileId, projectId, sourceSessionId]);

  const respond = useCallback(async () => {
    if (!answer.trim() || !session) return;
    setLoading(true); setError("");
    try {
      const { data } = await api.post("/reflection/respond", { session_id: session.session_id, answer: answer.trim() });
      if (data.error) { setError(data.error); return; }
      setFollowup(data.ai_followup ?? ""); setAnswer("");
      if (data.completed) { setPhase("concluding"); }
      else if (data.next_question) {
        setSession(p => p ? { ...p, current_question: data.next_question, question_number: data.question_number } : p);
        setPhase("answering");
      }
    } catch (error: unknown) { setError(getErrorMessage(error, "提交失败")); }
    finally { setLoading(false); }
  }, [answer, session]);

  const conclude = useCallback(async () => {
    if (!session) return;
    setLoading(true); setError("");
    try {
      const { data } = await api.post("/reflection/conclude", { session_id: session.session_id, apply_adjustments: false });
      if (data.error) { setError(data.error); return; }
      setConclusion(data); setPhase("done"); onComplete?.(data);
    } catch (error: unknown) { setError(getErrorMessage(error, "总结失败")); }
    finally { setLoading(false); }
  }, [session, onComplete]);

  /* ── Idle ── */
  if (phase === "idle") {
    return (
      <div className={`reflection-card ${className}`}>
        <h2 className="reflection-title">反思性迭代画像</h2>
        <p className="reflection-subtitle">
          基于社会学反思性原理（法国实用主义、常人方法学、布迪厄反思社会学），在每次调查完成后引导你进行结构化反思。
        </p>
        <div className="reflection-trigger-grid">
          {[
            { id: "fieldwork_completed", label: "田野调查反思", desc: "完成一次田野调查后", icon: "🎙" },
            { id: "analysis_completed", label: "数据分析反思", desc: "完成一轮数据分析后", icon: "🔍" },
            { id: "project_completed", label: "项目综合反思", desc: "完成整个项目后", icon: "📄" },
          ].map(tr => (
            <button key={tr.id} onClick={() => start(tr.id)} disabled={loading}
              className="reflection-trigger-btn">
              <span className="reflection-trigger-icon">{tr.icon}</span>
              <span className="reflection-trigger-label">{tr.label}</span>
              <span className="reflection-trigger-desc">{tr.desc}</span>
            </button>
          ))}
        </div>
        {error && <p style={{ marginTop: 16, fontSize: 14, color: "#dc2626" }}>{error}</p>}
      </div>
    );
  }

  /* ── Intro ── */
  if (phase === "intro" && session) {
    return (
      <div className={`reflection-card ${className}`} style={{ maxWidth: 672 }}>
        <span style={{ fontSize: 12, fontWeight: 500, color: "var(--primary)", textTransform: "uppercase", letterSpacing: 0.5 }}>
          反思会话
        </span>
        <h2 className="reflection-title" style={{ marginTop: 8 }}>{session.title}</h2>
        <div className="reflection-intro-text">{session.intro}</div>
        <button onClick={() => setPhase("answering")} className="btn-primary">
          开始反思
        </button>
      </div>
    );
  }

  /* ── Answering / Concluding ── */
  if ((phase === "answering" || phase === "concluding") && session?.current_question) {
    const q = session.current_question;
    const pct = Math.round((session.question_number / session.total_questions) * 100);

    return (
      <div className={`reflection-card ${className}`} style={{ maxWidth: 672, padding: 24 }}>
        {/* Progress bar */}
        <div className="reflection-progress">
          <div className="reflection-progress-bar-bg">
            <div className="reflection-progress-bar-fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="reflection-progress-label">{session.question_number}/{session.total_questions}</span>
        </div>

        {/* Tradition tag */}
        {q.tradition && (
          <span className="reflection-tradition-tag">
            {TRADITION_LABELS[q.tradition] ?? q.tradition}
          </span>
        )}

        {/* Question */}
        <div className="reflection-question-text">{q.prompt}</div>

        {/* AI follow-up */}
        {followup && (
          <div className="reflection-followup">{followup}</div>
        )}

        {/* Answer input */}
        {phase === "answering" && (
          <>
            <textarea
              value={answer}
              onChange={e => setAnswer(e.target.value)}
              placeholder="请输入你的反思……例如：你发现了什么意外？什么预设被挑战了？"
              rows={4}
              className="reflection-textarea"
              disabled={loading}
            />
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
              <button onClick={respond} disabled={loading || !answer.trim()} className="btn-primary">
                {loading ? "思考中…" : "提交反思"}
              </button>
            </div>
          </>
        )}

        {/* Conclude prompt */}
        {phase === "concluding" && (
          <div style={{ textAlign: "center", padding: "16px 0" }}>
            <p style={{ color: "var(--text)", fontSize: 14, marginBottom: 16 }}>你已经回答了所有反思问题。</p>
            <button onClick={conclude} disabled={loading} className="btn-primary">
              {loading ? "生成总结中…" : "查看反思总结"}
            </button>
          </div>
        )}

        {error && <p style={{ marginTop: 12, fontSize: 14, color: "#dc2626" }}>{error}</p>}
      </div>
    );
  }

  /* ── Done ── */
  if (phase === "done" && conclusion) {
    return (
      <div className={`reflection-card ${className}`} style={{ maxWidth: 672, padding: 24 }}>
        <span className="reflection-done-header">反思完成</span>
        <h2 style={{ fontSize: 18, fontWeight: 600, color: "var(--text)", marginTop: 8, marginBottom: 16 }}>
          反思总结 · {conclusion.total_questions} 个问题
        </h2>

        {/* Summary */}
        <div className="reflection-intro-text" style={{ marginBottom: 20 }}>
          {conclusion.summary}
        </div>

        {/* Insights */}
        {conclusion.insights.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <h3 className="reflection-section-title">迭代洞察</h3>
            {conclusion.insights.map((ins, i) => (
              <div key={i} className="reflection-insight-card">
                <span style={{ fontWeight: 500, color: "var(--text)" }}>
                  {DIM_LABELS_MAP[ins.dimension] ?? ins.dimension}
                </span>
                <span style={{
                  marginLeft: 8, fontSize: 12,
                  color: ins.direction > 0 ? "#059669" : "#d97706",
                }}>
                  {ins.direction > 0 ? "→" : "←"} {Math.abs(ins.direction)}
                </span>
                <span style={{ marginLeft: 8, fontSize: 12, color: "var(--text-muted)" }}>
                  (置信度 {Math.round(ins.confidence * 100)}%)
                </span>
                <p style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 4 }}>{ins.rationale}</p>
              </div>
            ))}
          </div>
        )}

        {/* Spectrum shifts */}
        {conclusion.spectrum_shifts.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <h3 className="reflection-section-title">光谱偏移建议</h3>
            {conclusion.spectrum_shifts.map((shift, i) => (
              <div key={i} className="reflection-shift-row">
                <span style={{ color: "var(--text)", width: 112 }}>
                  {DIM_LABELS_MAP[shift.dimension] ?? shift.dimension}
                </span>
                <span style={{ color: "var(--text-muted)" }}>{shift.current_value}/5</span>
                <span style={{ color: shift.direction > 0 ? "#059669" : "#d97706" }}>
                  {shift.direction > 0 ? "→" : "←"}
                </span>
                <span style={{ color: "var(--text-muted)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {shift.rationale}
                </span>
              </div>
            ))}
          </div>
        )}

        <button
          onClick={() => { setPhase("idle"); setSession(null); setConclusion(null); setFollowup(""); }}
          className="btn-secondary">
          开始新的反思
        </button>
      </div>
    );
  }

  /* ── Loading / Error ── */
  return (
    <div className={`reflection-card ${className}`}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 20, height: 20,
          border: "2px solid var(--primary-light)", borderTopColor: "var(--primary)",
          borderRadius: "50%", animation: "pulse 1s infinite",
        }} />
        <span style={{ fontSize: 14, color: "var(--text-muted)" }}>
          {loading ? "处理中…" : "加载中…"}
        </span>
      </div>
      {error && <p style={{ marginTop: 12, fontSize: 14, color: "#dc2626" }}>{error}</p>}
    </div>
  );
}
