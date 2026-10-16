import { useState, useEffect, useCallback } from "react";
import api from "../api/client";
import { useApp } from "../hooks/useApp";

interface ProjectItem {
  id: number;
  title: string;
  research_direction: string | null;
  paradigm: string;
  phase: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

interface ProjectDetail {
  project: ProjectItem & {
    topic_argumentation?: string;
    questionnaire_design?: string;
    methodology_guidance?: string;
  };
  sessions: Array<{ id: number; notes?: string; summary_text?: string; created_at: string }>;
  analyses: Array<{ id: number; content: string }>;
  exports: Array<{ id: number; format: string; content: string }>;
}

interface KnowledgeCardItem {
  id: number;
  title: string;
  category: string;
  content: string;
  tags: string[];
  paradigm: string;
  phase: string;
  importance: number;
  reuse_count: number;
  relevance_score?: number;
  source_project_id: number | null;
  created_at: string | null;
}

const CAT_META: Record<string, { label: string; icon: string }> = {
  methodology: { label: "方法论", icon: "📐" },
  pitfall: { label: "避坑指南", icon: "⚠️" },
  tool: { label: "工具技巧", icon: "🛠" },
  ethics: { label: "伦理提醒", icon: "⚖️" },
  theory: { label: "理论洞察", icon: "💡" },
  workflow: { label: "流程优化", icon: "🔄" },
};

export default function SurveyLibrary() {
  const { profile } = useApp();
  const [activeTab, setActiveTab] = useState<"projects" | "knowledge">("projects");
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<ProjectDetail | null>(null);
  const [lessons, setLessons] = useState("");
  const [loadingLessons, setLoadingLessons] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Knowledge cards state
  const [cards, setCards] = useState<KnowledgeCardItem[]>([]);
  const [cardCategory, setCardCategory] = useState("");
  const [extractingCards, setExtractingCards] = useState(false);
  const [cardsLoading, setCardsLoading] = useState(false);

  useEffect(() => {
    api.get("/library").then((r) => setProjects(r.data.projects || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const fetchCards = useCallback(async () => {
    setCardsLoading(true);
    try {
      const params: Record<string, string | number> = { profile_id: profile?.id || 1 };
      if (cardCategory) params.category = cardCategory;
      const r = await api.get("/knowledge/cards", { params });
      setCards(r.data.cards || []);
    } catch { /* offline */ }
    finally { setCardsLoading(false); }
  }, [cardCategory, profile]);

  useEffect(() => {
    if (activeTab === "knowledge") void Promise.resolve().then(fetchCards);
  }, [activeTab, fetchCards]);

  const extractCards = async () => {
    if (!confirm("AI将分析所有已完成的项目，从中提取可复用的方法论知识卡片。这个过程可能需要几秒到几十秒。继续？")) return;
    setExtractingCards(true);
    try {
      const r = await api.post("/knowledge/extract", { profile_id: profile?.id || 1 });
      alert(`成功提取 ${r.data.cards_created} 张知识卡片！`);
      fetchCards();
    } catch { alert("提取失败，请重试"); }
    finally { setExtractingCards(false); }
  };

  const markReuse = async (cardId: number) => {
    await api.post(`/knowledge/cards/${cardId}/reuse`).catch(() => {});
    fetchCards();
  };

  const deleteCard = async (cardId: number) => {
    if (!confirm("删除此知识卡片？")) return;
    await api.delete(`/knowledge/cards/${cardId}`).catch(() => {});
    fetchCards();
  };

  const openDetail = async (id: number) => {
    setLoadingDetail(true);
    setSelected(null);
    setLessons("");
    try {
      const res = await api.get(`/library/${id}`);
      setSelected(res.data);
    } catch {
      alert("获取项目详情失败");
    } finally {
      setLoadingDetail(false);
    }
  };

  const generateLessons = async (id: number) => {
    setLoadingLessons(true);
    setLessons("");
    try {
      const res = await api.post(`/library/${id}/lessons`);
      setLessons(res.data.lessons || "");
    } catch {
      setLessons("生成失败，请重试");
    } finally {
      setLoadingLessons(false);
    }
  };

  const deleteProject = async (id: number) => {
    if (!confirm("确定删除此项目吗？所有关联数据将被永久删除。")) return;
    try {
      await api.delete(`/library/${id}`);
      setProjects((prev) => prev.filter((p) => p.id !== id));
      setSelected(null);
    } catch {
      alert("删除失败");
    }
  };

  const phaseLabels: Record<string, string> = {
    pre_survey: "调查前", during_survey: "调查中", post_survey: "调查后", completed: "已完成",
  };
  const paradigmLabels: Record<string, string> = {
    qualitative: "质性", quantitative: "量化", mixed: "混合",
  };

  const filtered = projects.filter(
    (p) => !search || p.title.includes(search) || (p.research_direction || "").includes(search)
  );

  return (
    <div className="page">
      <h2>调查档案库</h2>
      <p className="subtitle">回顾所有调查项目，总结经验，持续成长</p>

      {/* Tab switcher */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {([
          { id: "projects" as const, label: "📁 项目档案", desc: "浏览所有调查项目" },
          { id: "knowledge" as const, label: "🧠 知识卡片", desc: "跨项目方法论洞察" },
        ]).map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
            flex: 1, padding: "12px 16px", textAlign: "left",
            border: activeTab === t.id ? "2px solid var(--primary)" : "1px solid var(--border)",
            borderRadius: 10, cursor: "pointer", fontWeight: activeTab === t.id ? 600 : 400,
            background: activeTab === t.id ? "var(--primary-light)" : "var(--surface)",
            color: activeTab === t.id ? "var(--primary)" : "var(--text)",
          }}>
            <div style={{ fontSize: 15 }}>{t.label}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{t.desc}</div>
          </button>
        ))}
      </div>

      {/* ═══ Projects Tab ═══ */}
      {activeTab === "projects" && (<>
      <div className="input-row" style={{ marginBottom: 20 }}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索项目标题或研究方向..."
        />
      </div>

      {loading ? (
        <div className="loading-spinner-container">
          <div className="loading-spinner" />
          <p className="hint" style={{ marginTop: 12 }}>正在加载项目数据...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="onboarding-card">
          <h3>还没有任何调查项目</h3>
          <p>去「调查前 → 选题设计」开始你的第一个项目吧。</p>
        </div>
      ) : (
        <div className="library-grid">
          {filtered.map((p) => (
            <div key={p.id} className="library-card" onClick={() => openDetail(p.id)}>
              <h4>{p.title}</h4>
              {p.research_direction && <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "4px 0" }}>{p.research_direction.slice(0, 80)}...</p>}
              <div className="badge-row" style={{ marginTop: 8 }}>
                <span className="badge">{phaseLabels[p.phase] || p.phase}</span>
                <span className="badge">{paradigmLabels[p.paradigm] || p.paradigm}</span>
                <span className="badge">{p.status}</span>
              </div>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>{p.updated_at || p.created_at}</p>
            </div>
          ))}
        </div>
      )}

      {loadingDetail && <p className="hint" style={{ marginTop: 16 }}>加载详情中...</p>}

      {selected && (
        <div className="project-detail" style={{ marginTop: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3>{selected.project.title} — 项目详情</h3>
            <button onClick={() => deleteProject(selected.project.id)} style={{ background: "#DC2626", color: "#fff", border: "none", padding: "8px 16px", borderRadius: 6, cursor: "pointer" }}>删除项目</button>
          </div>

          {selected.project.topic_argumentation && (
            <details style={{ marginTop: 16 }}>
              <summary style={{ fontWeight: 600, cursor: "pointer" }}>选题论证</summary>
              <div className="md-content" style={{ marginTop: 8 }}>{selected.project.topic_argumentation}</div>
            </details>
          )}

          {selected.project.questionnaire_design && (
            <details style={{ marginTop: 12 }}>
              <summary style={{ fontWeight: 600, cursor: "pointer" }}>问卷设计</summary>
              <div className="md-content" style={{ marginTop: 8 }}>{selected.project.questionnaire_design}</div>
            </details>
          )}

          {selected.project.methodology_guidance && (
            <details style={{ marginTop: 12 }}>
              <summary style={{ fontWeight: 600, cursor: "pointer" }}>方法论规划</summary>
              <div className="md-content" style={{ marginTop: 8 }}>{selected.project.methodology_guidance}</div>
            </details>
          )}

          {selected.sessions.length > 0 && (
            <details style={{ marginTop: 12 }}>
              <summary style={{ fontWeight: 600, cursor: "pointer" }}>田野会话 ({selected.sessions.length}次)</summary>
              {selected.sessions.map((s) => (
                <div key={s.id} style={{ marginTop: 8, padding: 12, background: "var(--bg)", borderRadius: 8 }}>
                  {s.notes && <p><strong>笔记:</strong> {s.notes.slice(0, 200)}</p>}
                  {s.summary_text && <div className="md-content" style={{ marginTop: 8 }}>{s.summary_text.slice(0, 500)}</div>}
                  <p style={{ fontSize: 12, color: "var(--text-muted)" }}>{s.created_at}</p>
                </div>
              ))}
            </details>
          )}

          {selected.analyses.length > 0 && (
            <details style={{ marginTop: 12 }}>
              <summary style={{ fontWeight: 600, cursor: "pointer" }}>分析结果 ({selected.analyses.length}次)</summary>
              {selected.analyses.map((a) => (
                <div key={a.id} className="md-content" style={{ marginTop: 8 }}>{a.content.slice(0, 500)}...</div>
              ))}
            </details>
          )}

          {selected.exports.length > 0 && (
            <details style={{ marginTop: 12 }}>
              <summary style={{ fontWeight: 600, cursor: "pointer" }}>导出文档 ({selected.exports.length}份)</summary>
              {selected.exports.map((e) => (
                <div key={e.id} style={{ marginTop: 8 }}>
                  <span className="badge">{e.format}</span>
                  <div className="md-content" style={{ marginTop: 4 }}>{e.content.slice(0, 500)}...</div>
                </div>
              ))}
            </details>
          )}

          <div style={{ marginTop: 20 }}>
            <button onClick={() => generateLessons(selected.project.id)} disabled={loadingLessons} className="btn-primary">
              {loadingLessons ? "AI总结中..." : "AI 总结经验教训"}
            </button>
          </div>

          {lessons && <div className="md-content" style={{ marginTop: 16 }}>{lessons}</div>}
        </div>
      )}
      </>)}
      {/* End Projects Tab */}

      {/* ═══ Knowledge Cards Tab ═══ */}
      {activeTab === "knowledge" && (<>
        <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
          {["", "methodology", "pitfall", "tool", "ethics", "theory", "workflow"].map(cat => (
            <button key={cat} onClick={() => setCardCategory(cat)} style={{
              padding: "5px 12px", borderRadius: 20, fontSize: 12, cursor: "pointer",
              background: cardCategory === cat ? "var(--primary)" : "var(--surface)",
              color: cardCategory === cat ? "#fff" : "var(--text)",
              border: `1px solid ${cardCategory === cat ? "var(--primary)" : "var(--border)"}`,
            }}>
              {cat === "" ? "全部" : `${CAT_META[cat]?.icon || ""} ${CAT_META[cat]?.label || cat}`}
            </button>
          ))}
          <button onClick={extractCards} disabled={extractingCards} className="btn-primary" style={{ marginLeft: "auto", fontSize: 13 }}>
            {extractingCards ? "🤖 AI提取中..." : "🤖 提取知识卡片"}
          </button>
        </div>

        {cardsLoading ? (
          <div className="loading-spinner-container"><div className="loading-spinner"/><p>加载卡片...</p></div>
        ) : cards.length === 0 ? (
          <div className="onboarding-card">
            <h3>🧠 还没有知识卡片</h3>
            <p>完成一个调查项目后，点击「提取知识卡片」按钮，AI 将从你的项目经验中提炼可复用的方法论洞察。</p>
          </div>
        ) : (
          <div className="card-row" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
            {cards.map(c => (
              <div key={c.id} className="knowledge-card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                  <span style={{ fontSize: 12, padding: "2px 8px", borderRadius: 10, background: "var(--primary-light)", color: "var(--primary)" }}>
                    {CAT_META[c.category]?.icon} {CAT_META[c.category]?.label || c.category}
                  </span>
                  <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                    <span title="重要性" style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {"⭐".repeat(c.importance)}{"☆".repeat(5 - c.importance)}
                    </span>
                    <span title="复用次数" style={{ fontSize: 11, color: "var(--text-muted)" }}>🔄{c.reuse_count}</span>
                  </div>
                </div>
                <h4 style={{ margin: "4px 0 8px", fontSize: 15 }}>{c.title}</h4>
                <p style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.6, marginBottom: 8 }}>
                  {c.content.slice(0, 200)}{c.content.length > 200 ? "..." : ""}
                </p>
                {c.tags.length > 0 && (
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
                    {c.tags.map((t, i) => (
                      <span key={i} style={{ fontSize: 10, padding: "1px 6px", borderRadius: 4, background: "var(--bg)", color: "var(--text-muted)" }}>{t}</span>
                    ))}
                  </div>
                )}
                <div style={{ display: "flex", gap: 8, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
                  <button onClick={() => markReuse(c.id)} title="标记为已复用" style={{
                    fontSize: 12, padding: "4px 10px", border: "1px solid var(--border)", borderRadius: 6,
                    background: "transparent", cursor: "pointer", color: "var(--text-muted)",
                  }}>👍 有用</button>
                  <button onClick={() => deleteCard(c.id)} title="删除" style={{
                    fontSize: 12, padding: "4px 10px", border: "1px solid var(--border)", borderRadius: 6,
                    background: "transparent", cursor: "pointer", color: "var(--text-muted)",
                  }}>🗑 删除</button>
                  <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: "auto", alignSelf: "center" }}>
                    {c.created_at?.slice(0, 10)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </>)}
      {/* End Knowledge Cards Tab */}
    </div>
  );
}
