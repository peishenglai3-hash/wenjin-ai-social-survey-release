import { useState, useMemo } from "react";
import api from "../api/client";
import { streamAI } from "../api/stream";
import { useApp } from "../hooks/useApp";
import { safeHtml } from "../utils/sanitize";
import QuickNav from "../components/QuickNav";

interface ParsedQuestion {
  id: string;
  construct: string;
  text: string;
  options: string[];
  scale_type: string;
  reversed: boolean;
  intent: string;
}

interface ParsedQuestionnaire {
  title: string;
  constructs: { name: string; definition: string; dimensions: string[] }[];
  scales: { name: string; source: string; alpha: number; items_count: number }[];
  questions: ParsedQuestion[];
  total_items: number;
  estimated_time_minutes: number;
  attention_checks: number;
}

interface ReliabilityWarning {
  type: "low_alpha" | "no_reverse" | "social_desirability" | "unbalanced";
  construct: string;
  message: string;
}

const STEPS = [
  { id: "full", label: "完整生成", desc: "一键生成完整问卷方案", icon: "📋" },
  { id: "concepts", label: "核心构念", desc: "梳理理论框架", icon: "🧠" },
  { id: "scales", label: "量表推荐", desc: "对比成熟量表", icon: "📐" },
  { id: "questions", label: "题项生成", desc: "生成具体题目", icon: "✍️" },
  { id: "review", label: "方法论审阅", desc: "信效度评估", icon: "🔍" },
];

const QUESTION_TYPES = [
  { id: "single_choice", label: "单选题", icon: "⭕" },
  { id: "multiple_choice", label: "多选题", icon: "☑️" },
  { id: "matrix_single", label: "矩阵单选题", icon: "📊" },
  { id: "ranking", label: "排序题", icon: "🔢" },
  { id: "nps", label: "NPS净推荐值", icon: "⭐" },
  { id: "open", label: "开放题", icon: "💬" },
];

function parseQuestionnaireJSON(text: string): ParsedQuestionnaire | null {
  try {
    const jsonMatch = text.split("```questionnaire_json\n");
    if (jsonMatch.length > 1) {
      const jsonStr = jsonMatch[1].split("\n```")[0];
      return JSON.parse(jsonStr);
    }
  } catch { /* parse error */ }
  return null;
}

function parseBatchQuestions(text: string): string {
  const lines = text.trim().split("\n").filter(Boolean);
  return lines.map((line) => {
    const parts = line.split("|").map((s) => s.trim());
    if (parts.length >= 2) {
      return `- 题干: ${parts[0]}\n  - 选项: ${parts.slice(1).join(", ")}`;
    }
    return `- ${line}`;
  }).join("\n");
}

function deriveWarnings(parsed: ParsedQuestionnaire): ReliabilityWarning[] {
  const warnings: ReliabilityWarning[] = [];
  const constructQuestions = new Map<string, ParsedQuestion[]>();
  for (const q of parsed.questions) {
    const arr = constructQuestions.get(q.construct) || [];
    arr.push(q);
    constructQuestions.set(q.construct, arr);
  }

  for (const scale of parsed.scales) {
    if (scale.alpha < 0.7) {
      warnings.push({
        type: "low_alpha",
        construct: scale.name,
        message: `量表"${scale.name}"的Cronbach's α为${scale.alpha}，低于0.7的可接受阈值。建议考虑替换或增加题项。`,
      });
    }
  }

  for (const [construct, questions] of constructQuestions) {
    const hasReverse = questions.some((q) => q.reversed);
    if (questions.length >= 3 && !hasReverse) {
      warnings.push({
        type: "no_reverse",
        construct,
        message: `构念"${construct}"有${questions.length}道题但缺少反向题，建议增加1-2道以控制响应偏差。`,
      });
    }
    const sensitiveKeywords = ["道德", "政治", "信仰", "收入", "犯罪", "性", "宗教"];
    const hasSensitive = questions.some((q) =>
      sensitiveKeywords.some((kw) => q.text.includes(kw)),
    );
    if (hasSensitive) {
      warnings.push({
        type: "social_desirability",
        construct,
        message: `构念"${construct}"涉及敏感话题，存在社会期望偏差风险。建议加入Marlowe-Crowne社会期望量表条目或采用间接提问。`,
      });
    }
  }

  return warnings;
}

export default function QuestionnaireDesign() {
  const { profile, project, setProject } = useApp();
  const [topic, setTopic] = useState(project?.research_direction || "");
  const [population, setPopulation] = useState("");
  const [paradigm, setParadigm] = useState(project?.paradigm || "quantitative");
  const [existingScales, setExistingScales] = useState("");
  const [step, setStep] = useState("full");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [showCardView, setShowCardView] = useState(false);

  const [selectedTypes, setSelectedTypes] = useState<string[]>(["single_choice", "matrix_single", "open"]);
  const [batchText, setBatchText] = useState("");
  const [showBatchImport, setShowBatchImport] = useState(false);
  const [projectBackground, setProjectBackground] = useState("");

  const experienceLevel = profile?.experience_level || "beginner";
  const parsed = useMemo(() => parseQuestionnaireJSON(result), [result]);
  const warnings = useMemo(() => parsed ? deriveWarnings(parsed) : [], [parsed]);

  const levelLabels: Record<string, string> = {
    beginner: "新手模式 · AI出完整问卷 + 设计意图说明",
    intermediate: "进阶模式 · AI出框架 + 备选方案供选择",
    advanced: "专家模式 · AI做方法论审阅 + 信效度风险提示",
  };

  const toggleType = (typeId: string) => {
    setSelectedTypes((prev) =>
      prev.includes(typeId) ? prev.filter((t) => t !== typeId) : [...prev, typeId],
    );
  };

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    setLoading(true);
    setResult("");
    setShowCardView(false);

    const batchContext = batchText.trim()
      ? `\n\n【批量导入题项】\n${parseBatchQuestions(batchText)}`
      : "";

    const backgroundContext = projectBackground.trim()
      ? `\n\n【项目背景】\n${projectBackground.trim()}`
      : "";

    const typeContext = selectedTypes.length > 0
      ? `\n\n【指定题型】请优先使用以下题型：${selectedTypes.map((t) => QUESTION_TYPES.find((qt) => qt.id === t)?.label).join("、")}。`
      : "";

    await streamAI(
      "/topic/questionnaire/stream",
      {
        research_topic: topic + backgroundContext + typeContext + batchContext,
        target_population: population,
        paradigm,
        experience_level: experienceLevel,
        existing_scales: existingScales,
        step,
      },
      (token) => setResult((prev) => prev + token),
      () => setLoading(false),
      (err) => { setResult(err); setLoading(false); },
    );
  };

  const handleSaveToProject = async () => {
    if (!project?.id || !result) return;
    try {
      // 1. Save raw text to project (existing behavior)
      await api.put(`/projects/${project.id}`, { questionnaire_design: result });

      // 2. If parsed JSON exists, save structured questionnaire
      if (parsed) {
        await api.post("/questionnaire/save", {
          project_id: project.id,
          title: parsed.title,
          constructs_json: JSON.stringify(parsed.constructs),
          questions_json: JSON.stringify(parsed.questions),
          scales_json: JSON.stringify(parsed.scales),
          total_items: parsed.total_items,
          estimated_time_minutes: parsed.estimated_time_minutes,
          raw_output: result,
          paradigm,
        }).catch(() => { /* silent — structured save is non-blocking */ });
      }

      setProject({ ...project, phase: "pre_survey" });
      alert(parsed ? "问卷已保存到项目（含结构化数据）" : "问卷设计已保存到项目");
    } catch { alert("保存失败"); }
  };

  const handleDownload = async (fileType: "docx" | "md") => {
    if (!result) return;
    setDownloading(fileType);
    try {
      const title = topic.trim().slice(0, 30) || "问卷设计";
      const res = await api.post("/topic/questionnaire/download", {
        content: result, file_type: fileType, title,
      }, { responseType: "blob" });
      const blob = new Blob([res.data], {
        type: fileType === "docx"
          ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          : "text/markdown",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `${title}.${fileType}`; a.click();
      URL.revokeObjectURL(url);
    } catch { alert(`${fileType.toUpperCase()} 下载失败`); }
    finally { setDownloading(null); }
  };

  const warningColors: Record<string, string> = {
    low_alpha: "#EF4444",
    no_reverse: "#F59E0B",
    social_desirability: "#8B5CF6",
    unbalanced: "#3B82F6",
  };

  return (
    <div className="page">
      <h2>问卷设计 · AI辅助生成</h2>
      <p className="subtitle">
        基于研究主题自动生成结构化问卷，含ISSP/SocioBench学术量表知识库
        {" · "}
        <span style={{ color: "var(--accent)", fontWeight: 500 }}>{levelLabels[experienceLevel]}</span>
      </p>

      <div className="split-page">
        <div className="split-left">
          {!profile?.id && (
            <div className="warning-banner">
              请先在「身份设置」中保存你的调查者档案。档案中的经验水平将决定AI的交互模式。
            </div>
          )}

          <div className="form-group">
            <label>研究主题</label>
            <input value={topic} onChange={(e) => setTopic(e.target.value)}
              placeholder="例如：大学生社交媒体使用与心理健康的关系" />
          </div>
          <div className="form-group">
            <label>目标人群</label>
            <input value={population} onChange={(e) => setPopulation(e.target.value)}
              placeholder="例如：在校大学生（18-25岁）" />
          </div>
          <div className="form-group">
            <label>研究范式</label>
            <select value={paradigm} onChange={(e) => setParadigm(e.target.value)}>
              <option value="quantitative">量化研究</option>
              <option value="qualitative">质性研究</option>
              <option value="mixed">混合方法</option>
            </select>
          </div>
          <div className="form-group">
            <label>已知量表（可选）</label>
            <input value={existingScales} onChange={(e) => setExistingScales(e.target.value)}
              placeholder="例如：已考虑使用GAD-7焦虑量表" />
          </div>

          <div className="form-group">
            <label>📋 项目背景</label>
            <textarea
              value={projectBackground}
              onChange={(e) => setProjectBackground(e.target.value)}
              placeholder={"描述研究项目的背景信息，AI将据此生成更贴合实际需求的问卷。\n\n例如：\n- 本项目依托XX街道社区治理创新试点，旨在评估居民对网格化管理改革的满意度。\n- 调查对象为参与了2025年旧改项目的200户居民。\n- 课题组前期质性访谈发现居民主要不满集中在信息公开不及时和补偿标准不透明。"}
              rows={5}
              style={{ width: "100%", fontSize: 13, fontFamily: "inherit", resize: "vertical" }}
            />
            <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
              填写越详细，AI生成的问卷与实际情况越贴合。留空则仅基于研究主题生成。
            </p>
          </div>

          {/* Question Type Selector */}
          <div className="form-group">
            <label>题型偏好（可多选）</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {QUESTION_TYPES.map((qt) => (
                <button key={qt.id} type="button" onClick={() => toggleType(qt.id)}
                  style={{
                    padding: "4px 10px", fontSize: 12, borderRadius: 16,
                    border: selectedTypes.includes(qt.id)
                      ? "2px solid var(--primary)" : "1px solid var(--border)",
                    background: selectedTypes.includes(qt.id)
                      ? "var(--primary-light)" : "var(--surface)",
                    color: selectedTypes.includes(qt.id)
                      ? "var(--primary)" : "var(--text-muted)",
                    cursor: "pointer", fontWeight: selectedTypes.includes(qt.id) ? 600 : 400,
                  }}>
                  {qt.icon} {qt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Batch Import */}
          <div className="form-group">
            <button type="button" className="btn-secondary"
              onClick={() => setShowBatchImport(!showBatchImport)} style={{ fontSize: 13 }}>
              {showBatchImport ? "隐藏批量导入" : "📥 批量导入题项（粘贴格式化文本）"}
            </button>
            {showBatchImport && (
              <div style={{ marginTop: 8 }}>
                <textarea value={batchText}
                  onChange={(e) => setBatchText(e.target.value)}
                  placeholder={"粘贴已格式化的题项，每行一题，用 | 分隔选项：\n\nQ1 您的年龄段 | 18-25岁 | 26-35岁 | 36-45岁 | 46岁以上\nQ2 您每天使用社交媒体的时长 | <1小时 | 1-3小时 | 3-6小时 | >6小时\nQ3 您是否曾因社交媒体使用感到焦虑 | 从未 | 偶尔 | 经常 | 总是"}
                  rows={6}
                  style={{ width: "100%", fontSize: 12, fontFamily: "monospace" }} />
                <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                  每行格式：题干 | 选项1 | 选项2 | ... 系统将自动构建为结构化题目并合并到AI生成的问卷中
                </p>
              </div>
            )}
          </div>

          {/* Step selector */}
          <div className="form-group">
            <label>生成步骤</label>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {STEPS.map((s) => (
                <button key={s.id} onClick={() => setStep(s.id)}
                  className={`card-btn ${step === s.id ? "selected" : ""}`}
                  style={{ textAlign: "left", padding: "8px 12px" }}>
                  <span style={{ marginRight: 6 }}>{s.icon}</span>
                  <strong>{s.label}</strong>
                  <span style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginLeft: 24 }}>
                    {s.desc}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <button onClick={handleGenerate} disabled={loading || !topic.trim()} className="btn-primary">
            {loading ? "AI生成中..." : `生成${STEPS.find(s => s.id === step)?.label || "问卷"}`}
          </button>

          {result && !loading && (
            <>
              <button onClick={handleSaveToProject} className="btn-secondary" style={{ marginLeft: 8 }}>
                保存到项目
              </button>
              {parsed && parsed.questions.length > 0 && (
                <button onClick={() => setShowCardView(!showCardView)}
                  className="btn-secondary" style={{ marginLeft: 8 }}>
                  {showCardView ? "查看完整报告" : `查看题项卡片 (${parsed.questions.length}题)`}
                </button>
              )}
            </>
          )}

          {loading && !result && (
            <div style={{ padding: 12, background: "var(--surface)", borderRadius: 8, textAlign: "center", fontSize: 13 }}>
              <span className="dot connecting" style={{ display: "inline-block", marginRight: 8 }} />
              正在连接 AI 服务...
            </div>
          )}
        </div>

        {/* ── Right: Output ── */}
        {result ? (
          <div className="split-right">
            {showCardView && parsed ? (
              <div>
                <div style={{ marginBottom: 16, padding: "12px 16px", background: "var(--primary-light)", borderRadius: 8 }}>
                  <strong>{parsed.title}</strong>
                  <span style={{ marginLeft: 12, fontSize: 13, color: "var(--text-muted)" }}>
                    {parsed.total_items}题 · 约{parsed.estimated_time_minutes}分钟 · {parsed.attention_checks}道注意力检测
                  </span>
                </div>

                {/* Reliability Warnings */}
                {warnings.length > 0 && (
                  <div style={{ marginBottom: 16, padding: "12px 16px", background: "#FFFBEB", borderRadius: 8, border: "1px solid #FDE68A" }}>
                    <strong style={{ fontSize: 14 }}>⚠️ 信效度风险提示 ({warnings.length})</strong>
                    {warnings.map((w, i) => (
                      <div key={i} style={{
                        marginTop: 8, padding: "8px 12px", background: "#fff", borderRadius: 6,
                        borderLeft: `3px solid ${warningColors[w.type] || "#999"}`, fontSize: 13, lineHeight: 1.5,
                      }}>
                        <span style={{
                          display: "inline-block", padding: "1px 6px", borderRadius: 3,
                          fontSize: 10, fontWeight: 600, marginRight: 8,
                          background: warningColors[w.type] + "20", color: warningColors[w.type],
                        }}>
                          {w.type === "low_alpha" ? "低信度" : w.type === "no_reverse" ? "缺反向题" : w.type === "social_desirability" ? "社会期望" : "不平衡"}
                        </span>
                        {w.message}
                      </div>
                    ))}
                  </div>
                )}

                {/* Constructs */}
                <details style={{ marginBottom: 16 }}>
                  <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 14 }}>
                    核心构念 ({parsed.constructs.length})
                  </summary>
                  <div style={{ marginTop: 8 }}>
                    {parsed.constructs.map((c, i) => (
                      <div key={i} style={{ padding: "8px 12px", marginBottom: 4, background: "#f9fafb", borderRadius: 6, borderLeft: "3px solid var(--primary)" }}>
                        <strong>{c.name}</strong>: {c.definition}
                        {c.dimensions.length > 0 && (
                          <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block" }}>
                            维度: {c.dimensions.join(" · ")}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </details>

                {/* Question cards */}
                {parsed.questions.map((q) => (
                  <div key={q.id} style={{
                    padding: "14px 16px", marginBottom: 10,
                    background: "var(--surface)", borderRadius: 10,
                    border: "1px solid var(--border)",
                    borderLeft: q.reversed ? "4px solid #F59E0B" : "4px solid var(--primary)",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                      <span style={{ background: "var(--primary)", color: "#fff", borderRadius: 6, padding: "2px 8px", fontSize: 13, fontWeight: 600 }}>{q.id}</span>
                      <span style={{ background: q.reversed ? "#FEF3C7" : "#E0E7FF", color: q.reversed ? "#92400E" : "#3730A3", borderRadius: 4, padding: "1px 6px", fontSize: 11 }}>{q.construct}</span>
                      <span style={{ background: "#F1F5F9", color: "#64748B", borderRadius: 4, padding: "1px 6px", fontSize: 10 }}>{q.scale_type}</span>
                      {q.reversed && <span style={{ color: "#F59E0B", fontSize: 12 }}>⚠️ 反向题</span>}
                    </div>
                    <p style={{ margin: "6px 0", fontSize: 14, lineHeight: 1.6 }}>{q.text}</p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                      {q.options.map((opt, i) => (
                        <span key={i} style={{ padding: "3px 10px", fontSize: 12, borderRadius: 12, background: "#F1F5F9", color: "#475569" }}>{opt}</span>
                      ))}
                    </div>
                    <p style={{ marginTop: 8, fontSize: 12, color: "var(--text-muted)", fontStyle: "italic" }}>{q.intent}</p>
                  </div>
                ))}

                <button onClick={() => setShowCardView(false)} className="btn-secondary" style={{ marginTop: 12 }}>
                  查看完整Markdown报告
                </button>
              </div>
            ) : (
              <>
                <div className="md-content" style={{ marginBottom: 16 }}
                  dangerouslySetInnerHTML={safeHtml(result.replace(/```questionnaire_json\n[\s\S]*?\n```/g, "").trim())}
                />
                <div className="button-row" style={{ flexWrap: "wrap" }}>
                  <button onClick={() => handleDownload("docx")} disabled={downloading !== null}
                    className="btn-secondary"
                    style={{ background: "var(--primary)", color: "#fff", border: "none" }}>
                    {downloading === "docx" ? "下载中..." : "下载 Word (.docx)"}
                  </button>
                  <button onClick={() => handleDownload("md")} disabled={downloading !== null}
                    className="btn-secondary">
                    {downloading === "md" ? "下载中..." : "下载 Markdown (.md)"}
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          <div className="split-right-empty">
            {loading
              ? "AI 正在生成结构化问卷...\n\n根据你的经验水平（" + levelLabels[experienceLevel] + "）调整输出风格"
              : "AI 生成的问卷方案将在此处实时展示\n\n包含ISSP学术量表推荐、完整题项（可切换卡片视图）、信效度保障策略等\n生成后可下载为 .docx 或 .md 文件\n\n🆕 新增：题型偏好选择 · 批量导入题项 · 信效度风险自动检测"}
          </div>
        )}
      </div>

      <QuickNav
        currentPath="/questionnaire"
        visible={!!result}
        nextPath="/methodology"
        nextLabel="方法论规划"
      />
    </div>
  );
}
