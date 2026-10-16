import { useState, useMemo } from "react";
import api from "../api/client";

interface ParsedQuestion {
  id: string;
  construct: string;
  text: string;
  options: string[];
  scale_type: string;
  reversed: boolean;
  intent: string;
}

interface QuestionnaireData {
  id: number;
  title: string;
  constructs_json: string;
  questions_json: string;
  total_items: number;
  estimated_time_minutes: number;
}

interface AnswerEntry {
  question_id: string;
  question_text: string;
  value: string;
  option_index: number | null;
  is_skipped: boolean;
}

interface QuestionnaireFillProps {
  questionnaire: QuestionnaireData;
  onComplete?: (responseId: number) => void;
}

export default function QuestionnaireFill({ questionnaire, onComplete }: QuestionnaireFillProps) {
  const questions: ParsedQuestion[] = useMemo(() => {
    try { return JSON.parse(questionnaire.questions_json); }
    catch { return []; }
  }, [questionnaire.questions_json]);

  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Map<string, AnswerEntry>>(new Map());
  const [respondentLabel, setRespondentLabel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [done, setDone] = useState(false);

  const currentQ = questions[currentIndex];
  const progress = questions.length > 0 ? Math.round(((currentIndex + 1) / questions.length) * 100) : 0;

  const setAnswer = (qid: string, value: string, optionIndex: number | null = null) => {
    setAnswers((prev) => {
      const next = new Map(prev);
      next.set(qid, {
        question_id: qid,
        question_text: currentQ?.text || "",
        value,
        option_index: optionIndex,
        is_skipped: false,
      });
      return next;
    });
  };

  const skipQuestion = () => {
    setAnswers((prev) => {
      const next = new Map(prev);
      next.set(currentQ.id, {
        question_id: currentQ.id,
        question_text: currentQ.text,
        value: "",
        option_index: null,
        is_skipped: true,
      });
      return next;
    });
    if (currentIndex < questions.length - 1) {
      setCurrentIndex((i) => i + 1);
    }
  };

  const handleNext = () => {
    if (currentIndex < questions.length - 1) setCurrentIndex((i) => i + 1);
  };

  const handlePrev = () => {
    if (currentIndex > 0) setCurrentIndex((i) => i - 1);
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setSubmitError("");
    try {
      const res = await api.post(`/questionnaire/${questionnaire.id}/respond`, {
        respondent_label: respondentLabel || `受访者${new Date().toLocaleTimeString("zh-CN")}`,
        answers: Array.from(answers.values()),
      });
      setDone(true);
      onComplete?.(res.data.id);
    } catch {
      setSubmitError("提交失败，请重试。请检查网络连接后再次提交。");
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <div style={{ textAlign: "center", padding: 32 }} role="status">
        <div style={{ fontSize: 48, marginBottom: 16 }}>✅</div>
        <h3>问卷填写完成</h3>
        <p style={{ color: "var(--text-muted)" }}>
          共 {questions.length} 题，已提交 {answers.size} 个回答。
        </p>
        <button type="button" onClick={() => { setDone(false); setCurrentIndex(0); setAnswers(new Map()); setSubmitError(""); }}
          className="btn-secondary" style={{ marginTop: 16 }}>
          填写新一份
        </button>
      </div>
    );
  }

  if (!currentQ) {
    return <p role="status" style={{ color: "var(--text-muted)", textAlign: "center", padding: 32 }}>问卷中没有题目。</p>;
  }

  const currentAnswer = answers.get(currentQ.id);

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 12, color: "var(--text-muted)" }}>
          <span>第 {currentIndex + 1}/{questions.length} 题</span>
          <span>{progress}%</span>
        </div>
        <div
          role="progressbar"
          aria-label="问卷完成进度"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
          style={{ background: "#E5E7EB", borderRadius: 4, height: 6, overflow: "hidden" }}
        >
          <div style={{ width: `${progress}%`, height: "100%", background: "var(--primary)", borderRadius: 4, transition: "width 0.2s" }} />
        </div>
      </div>

      <div style={{ padding: 20, background: "var(--surface)", borderRadius: 12, border: "1px solid var(--border)", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span style={{ background: "var(--primary)", color: "#fff", borderRadius: 6, padding: "2px 8px", fontSize: 12, fontWeight: 600 }}>
            {currentQ.id}
          </span>
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{currentQ.construct}</span>
          {currentQ.reversed && <span style={{ color: "#F59E0B", fontSize: 11 }}>⚠️ 反向题</span>}
        </div>
        <p style={{ fontSize: 16, lineHeight: 1.7, margin: "12px 0" }}>{currentQ.text}</p>

        {/* NPS */}
        {currentQ.scale_type === "nps" ? (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {Array.from({ length: 11 }, (_, i) => (
              <button type="button" key={i} onClick={() => setAnswer(currentQ.id, String(i), i)}
                aria-pressed={currentAnswer?.option_index === i}
                style={{
                  width: 44, height: 44, borderRadius: 8, fontSize: 16, cursor: "pointer",
                  background: currentAnswer?.option_index === i ? "var(--primary)" : "#F1F5F9",
                  color: currentAnswer?.option_index === i ? "#fff" : "#475569",
                  border: currentAnswer?.option_index === i ? "2px solid var(--primary)" : "1px solid var(--border)",
                }}>
                {i}
              </button>
            ))}
            <span style={{ fontSize: 11, color: "var(--text-muted)", alignSelf: "center", marginLeft: 8 }}>
              0=不可能推荐 · 10=一定会推荐
            </span>
          </div>
        ) : currentQ.scale_type === "multiple_choice" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {currentQ.options.map((opt, i) => {
              const selected = currentAnswer?.value ? currentAnswer.value.split("|").includes(opt) : false;
              return (
                <button type="button" key={i} onClick={() => {
                  const cur = currentAnswer?.value ? currentAnswer.value.split("|").filter(Boolean) : [];
                  setAnswer(currentQ.id, selected ? cur.filter((v: string) => v !== opt).join("|") : [...cur, opt].join("|"), i);
                }}
                  aria-pressed={selected}
                  style={{
                    padding: "12px 16px", textAlign: "left", fontSize: 15, cursor: "pointer", borderRadius: 8,
                    background: selected ? "#EEF2FF" : "#F9FAFB",
                    border: selected ? "2px solid var(--primary)" : "1px solid var(--border)",
                  }}>
                  {selected ? "☑ " : "☐ "}{opt}
                </button>
              );
            })}
          </div>
        ) : currentQ.scale_type === "ranking" ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            <p>请按重要性排序：</p>
            {currentQ.options.map((opt, i) => {
              const rank = currentAnswer?.value ? currentAnswer.value.split("|").indexOf(opt) : -1;
              return (
                <button type="button" key={i} onClick={() => {
                  const cur = currentAnswer?.value ? currentAnswer.value.split("|").filter(Boolean) : [];
                  setAnswer(currentQ.id, cur.includes(opt) ? cur.filter((v: string) => v !== opt).join("|") : [...cur, opt].join("|"));
                }}
                  aria-pressed={rank >= 0}
                  style={{ display: "block", width: "100%", padding: "10px 14px", marginBottom: 4, textAlign: "left", fontSize: 14, cursor: "pointer", borderRadius: 8,
                    background: rank >= 0 ? "#EEF2FF" : "#F9FAFB", border: rank >= 0 ? "2px solid var(--primary)" : "1px solid var(--border)" }}>
                  {rank >= 0 ? `${rank + 1}. ` : ""}{opt}
                </button>
              );
            })}
          </div>
        ) : currentQ.scale_type === "open" ? (
          <textarea value={currentAnswer?.value || ""} onChange={(e) => setAnswer(currentQ.id, e.target.value)}
            aria-label="开放题回答" placeholder="请输入回答..." rows={4}
            style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid var(--border)", resize: "vertical" }} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {currentQ.options.map((opt, i) => (
              <button type="button" key={i} onClick={() => setAnswer(currentQ.id, opt, i)}
                aria-pressed={currentAnswer?.option_index === i}
                style={{ padding: "12px 16px", textAlign: "left", fontSize: 15, cursor: "pointer", borderRadius: 8,
                  background: currentAnswer?.option_index === i ? "#EEF2FF" : "#F9FAFB",
                  border: currentAnswer?.option_index === i ? "2px solid var(--primary)" : "1px solid var(--border)" }}>
                {opt}
              </button>
            ))}
          </div>
        )}
      </div>

      {submitError && <div className="error-banner" role="alert" aria-live="assertive">{submitError}</div>}

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button type="button" onClick={handlePrev} disabled={currentIndex === 0} className="btn-secondary" style={{ fontSize: 13 }}>← 上一题</button>
        <button type="button" onClick={skipQuestion} className="btn-secondary" style={{ fontSize: 13, color: "#F59E0B" }}>跳过 ▸</button>
        <div style={{ flex: 1 }} />
        {currentIndex < questions.length - 1 ? (
          <button type="button" onClick={handleNext} className="btn-primary" style={{ fontSize: 13 }}>下一题 →</button>
        ) : (
          <button type="button" onClick={handleSubmit} disabled={submitting} className="btn-primary" style={{ fontSize: 13, background: "#059669" }}>
            {submitting ? "提交中..." : "✓ 提交问卷"}
          </button>
        )}
      </div>

      {currentIndex === questions.length - 1 && (
        <div style={{ marginTop: 16 }}>
          <label htmlFor="respondent-label" className="visually-hidden">受访者标识（可选）</label>
          <input id="respondent-label" value={respondentLabel} onChange={(e) => setRespondentLabel(e.target.value)}
            placeholder="受访者标识（如：受访者A，可选）"
            style={{ width: "100%", padding: "8px 12px", fontSize: 13, borderRadius: 6, border: "1px solid var(--border)" }} />
        </div>
      )}
    </div>
  );
}
