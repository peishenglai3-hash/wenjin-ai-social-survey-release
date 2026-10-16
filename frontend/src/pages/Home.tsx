import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../context/AppContext";
import config from "../config";
import { getAuthHeaders } from "../utils/authFetch";

interface DashboardData {
  needs_setup: boolean;
  profile?: {
    id: number;
    role: string;
    experience_level: string;
    paradigm_preference: string;
    theme_preference: string;
    spectrum: Record<string, number>;
    spectrum_summary: string;
  };
  project?: {
    id: number;
    title: string;
    research_direction: string | null;
    paradigm: string;
    phase: string;
    status: string;
    session_count: number;
    analysis_count: number;
  } | null;
  total_projects: number;
  tips: { dimension: string; score: number; left_label: string; right_label: string; tip: string }[];
  token_usage: { calls_7d: number; tokens_7d: number; cost_7d: number };
  workflow?: { name: string; stages: { id: string; label: string; icon: string; desc: string }[]; recommended_tools: string[] };
  next_step: { action: string; to: string; icon: string; desc: string };
}

const ROLE_LABELS: Record<string, string> = {
  undergraduate: "本科生", graduate: "硕士研究生", phd_candidate: "博士研究生",
  researcher: "研究人员", faculty: "教师", practitioner: "实务工作者", other: "其他",
};
const EXP_LABELS: Record<string, string> = {
  beginner: "新手起步", intermediate: "有一定经验", advanced: "经验丰富",
};
const PARADIGM_LABELS: Record<string, string> = {
  qualitative: "质性研究", quantitative: "量化研究", mixed: "混合方法",
};
const PHASE_LABELS: Record<string, string> = {
  pre_survey: "调查前", during_survey: "调查中", post_survey: "调查后", completed: "已完成",
};
const PHASE_ORDER = ["pre_survey", "during_survey", "post_survey", "completed"];

export default function Home() {
  const { profile, theme } = useApp();
  const navigate = useNavigate();
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const pid = profile?.id;
    if (!pid) { setLoading(false); return; }
    fetch(`${config.apiBaseUrl}/api/v1/dashboard/${pid}`, { headers: getAuthHeaders() })
      .then(r => r.json())
      .then(d => { setDash(d); setLoading(false); })
      .catch(() => { setLoading(false); });
  }, [profile?.id]);

  const needsSetup = !profile?.id;

  const greetings: Record<string, string> = {
    academic: "以学术之眼，观社会之微",
    government: "实事求是，调研为民",
    youth: "走进田野，认识社会",
  };
  const heroQuote = greetings[theme] || greetings.academic;

  const currentPhaseIdx = dash?.project ? PHASE_ORDER.indexOf(dash.project.phase) : -1;

  return (
    <div className="page page-dashboard">
      {/* ═══ Hero Section ═══ */}
      <div className="dashboard-hero">
        <div className="dashboard-hero-content">
          <h1 className="dashboard-hero-title">
            {loading ? "加载中..." : needsSetup ? "欢迎使用 AI 社会调查工作台" : `你好，${ROLE_LABELS[profile.role] || "研究者"}`}
          </h1>
          <p className="dashboard-hero-quote">{heroQuote}</p>
          {!loading && !needsSetup && dash?.profile && (
            <div className="dashboard-hero-meta">
              <span className="hero-tag">{EXP_LABELS[dash.profile.experience_level] || "新手"}</span>
              <span className="hero-tag">{PARADIGM_LABELS[dash.profile.paradigm_preference] || "质性"}</span>
              {dash.total_projects > 0 && <span className="hero-tag">📁 {dash.total_projects} 个项目</span>}
            </div>
          )}
        </div>
        {needsSetup && (
          <button className="btn-primary btn-hero-cta" onClick={() => navigate("/identity")}>
            👤 开始身份设置 →
          </button>
        )}
      </div>

      {/* ═══ Onboarding (no profile) ═══ */}
      {needsSetup && (
        <div className="onboarding-section">
          <div className="onboarding-steps">
            {[
              { step: 1, icon: "👤", title: "设置身份", desc: "告诉AI你是谁——身份、经验、偏好", to: "/identity" },
              { step: 2, icon: "🔍", title: "设计选题", desc: "AI辅助论证研究选题的价值与可行性", to: "/topic" },
              { step: 3, icon: "📝", title: "制作问卷", desc: "智能生成结构化问卷和量表", to: "/questionnaire" },
              { step: 4, icon: "🎙", title: "开展调查", desc: "录音转写、实时提示、田野辅助", to: "/fieldwork" },
            ].map(s => (
              <Link key={s.step} to={s.to} className="onboarding-step-card">
                <span className="onboarding-step-num">{s.step}</span>
                <span className="onboarding-step-icon">{s.icon}</span>
                <div>
                  <h4>{s.title}</h4>
                  <p>{s.desc}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {!needsSetup && (
        <div className="dashboard-grid">
          {/* ═══ Left Column ═══ */}
          <div className="dashboard-main">

            {/* Project Overview */}
            <section className="dash-card dash-project">
              <div className="dash-card-header">
                <h3>📋 {dash?.project ? "当前项目" : "项目概览"}</h3>
                {dash?.project && (
                  <Link to="/topic" className="dash-card-link">查看详情 →</Link>
                )}
              </div>
              {dash?.project ? (
                <>
                  <h4 className="dash-project-title">{dash.project.title}</h4>
                  {dash.project.research_direction && (
                    <p className="dash-project-direction">{dash.project.research_direction}</p>
                  )}
                  <div className="phase-progress">
                    {PHASE_ORDER.map((p, i) => (
                      <div key={p} className={`phase-dot ${i <= currentPhaseIdx ? "active" : ""} ${i === currentPhaseIdx ? "current" : ""}`}>
                        <span className="phase-dot-icon">
                          {i < currentPhaseIdx ? "✅" : i === currentPhaseIdx ? "📍" : "○"}
                        </span>
                        <span className="phase-dot-label">{PHASE_LABELS[p]}</span>
                      </div>
                    ))}
                  </div>
                  <div className="dash-project-stats">
                    <div className="stat-item">
                      <span className="stat-value">{dash.project.session_count}</span>
                      <span className="stat-label">访谈场次</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-value">{dash.project.analysis_count}</span>
                      <span className="stat-label">分析记录</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-value">{PARADIGM_LABELS[dash.project.paradigm] || dash.project.paradigm}</span>
                      <span className="stat-label">研究范式</span>
                    </div>
                  </div>
                  {dash.next_step && (
                    <button type="button" className="next-step-banner" onClick={() => navigate(dash.next_step.to)}>
                      <span style={{ fontSize: 20 }}>{dash.next_step.icon}</span>
                      <div>
                        <strong>{dash.next_step.action}</strong>
                        <span style={{ color: "var(--text-muted)", fontSize: 13, marginLeft: 8 }}>{dash.next_step.desc}</span>
                      </div>
                      <span style={{ marginLeft: "auto", color: "var(--primary)" }}>→</span>
                    </button>
                  )}
                </>
              ) : (
                <div className="dash-empty-state">
                  <p>还没有调查项目</p>
                  <button className="btn-primary" onClick={() => navigate("/topic")}>
                    🔍 创建第一个项目
                  </button>
                </div>
              )}
            </section>

            {/* Workflow Stages */}
            {dash?.workflow && (() => { const wf = dash.workflow; return (
              <section className="dash-card dash-workflow">
                <h3>🔀 {wf.name}</h3>
                <div className="workflow-stages">
                  {wf.stages.map((s, i) => (
                    <div key={s.id} className="workflow-stage-item">
                      <span className="workflow-stage-icon">{s.icon}</span>
                      <div className="workflow-stage-info">
                        <strong>{s.label}</strong>
                        <p>{s.desc}</p>
                      </div>
                      {i < wf.stages.length - 1 && <div className="workflow-stage-connector" />}
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: 12, fontSize: 13, color: "var(--text-muted)" }}>
                  🛠 推荐工具：{wf.recommended_tools.join(" · ")}
                </div>
              </section>
            ); })()}
          </div>

          {/* ═══ Right Column ═══ */}
          <div className="dashboard-side">

            {/* Quick Actions */}
            <section className="dash-card dash-quick-actions">
              <h3>⚡ 快速操作</h3>
              <div className="quick-actions-grid">
                {[
                  { to: "/identity", icon: "👤", label: "身份设置" },
                  { to: "/topic", icon: "🔍", label: "选题设计" },
                  { to: "/questionnaire", icon: "📝", label: "问卷设计" },
                  { to: "/methodology", icon: "📐", label: "方法论" },
                  { to: "/scenarios", icon: "🎬", label: "场景工坊" },
                  { to: "/fieldwork", icon: "🎙", label: "田野工具" },
                  { to: "/analysis", icon: "📊", label: "数据分析" },
                  { to: "/export", icon: "📄", label: "成果导出" },
                  { to: "/library", icon: "📚", label: "成果库" },
                  { to: "/settings", icon: "⚙️", label: "设置" },
                ].map(a => (
                  <Link key={a.to} to={a.to} className="quick-action-btn" title={a.label}>
                    <span className="quick-action-icon">{a.icon}</span>
                    <span className="quick-action-label">{a.label}</span>
                  </Link>
                ))}
              </div>
            </section>

            {/* Spectrum Tips */}
            {dash?.tips && dash.tips.length > 0 && (
              <section className="dash-card dash-tips">
                <h3>💡 光谱洞察</h3>
                <p className="dash-card-subtitle">基于你的方法论偏好，这些建议可能对你有帮助：</p>
                {dash.tips.map((t, i) => (
                  <div key={i} className="tip-item">
                    <div className="tip-header">
                      <span className="tip-dim">{t.left_label} ←→ {t.right_label}</span>
                      <span className="tip-score">{t.score}/5</span>
                    </div>
                    <p className="tip-text">{t.tip}</p>
                  </div>
                ))}
                <Link to="/settings" style={{ fontSize: 13, color: "var(--primary)" }}>
                  在设置中调整光谱 →
                </Link>
              </section>
            )}

            {/* Token Usage */}
            <section className="dash-card dash-tokens">
              <h3>📊 API 使用 (7天)</h3>
              <div className="token-mini-stats">
                <div className="token-stat">
                  <span className="token-stat-value">{dash?.token_usage?.calls_7d ?? 0}</span>
                  <span className="token-stat-label">调用次数</span>
                </div>
                <div className="token-stat">
                  <span className="token-stat-value">
                    {dash?.token_usage ? `${(dash.token_usage.tokens_7d / 1000).toFixed(0)}K` : "0"}
                  </span>
                  <span className="token-stat-label">Token用量</span>
                </div>
                <div className="token-stat">
                  <span className="token-stat-value">
                    ¥{dash?.token_usage?.cost_7d?.toFixed(2) ?? "0.00"}
                  </span>
                  <span className="token-stat-label">预估费用</span>
                </div>
              </div>
            </section>

            {/* Copilot tip */}
            <section className="dash-card dash-copilot-tip">
              <p style={{ margin: 0, fontSize: 14 }}>
                💬 <strong>需要帮助？</strong>点击右下角的 AI 助手按钮，随时提问关于调查方法、数据分析、论文写作的任何问题。
              </p>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
