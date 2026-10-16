import { useState, useEffect } from "react";
import { useApp } from "../hooks/useApp";
import config from "../config";
import { streamAI } from "../api/stream";
import { getAuthHeaders } from "../utils/authFetch";
import { safeHtml } from "../utils/sanitize";

interface ScenarioTemplate {
  id: string; name: string; icon: string; category: string;
  description: string; features: string[];
  suitable_methods: string[]; common_pitfalls: string[];
  ethical_notes: string; recommended_tools: string;
}

export default function Scenarios() {
  const { theme } = useApp();
  const [templates, setTemplates] = useState<ScenarioTemplate[]>([]);
  const [selected, setSelected] = useState<ScenarioTemplate | null>(null);
  const [view, setView] = useState<"browse" | "wizard" | "result">("browse");
  const [streaming, setStreaming] = useState(false);
  const [result, setResult] = useState("");
  const [answers, setAnswers] = useState({
    location: "", target_group: "", duration: "",
    resources: "", goal: "", concerns: "",
  });

  useEffect(() => {
    fetch(`${config.apiBaseUrl}/api/v1/scenarios/templates`, { headers: getAuthHeaders() })
      .then(r => r.json()).then(d => setTemplates(d.scenarios || [])).catch(() => {});
  }, []);

  const openWizard = (template?: ScenarioTemplate) => {
    if (template) setSelected(template);
    setView("wizard"); setResult("");
  };

  const generate = async () => {
    setStreaming(true); setView("result"); setResult("");
    let full = "";
    await streamAI(
      "/scenarios/design/stream",
      {
        answers: {
          "调查地点": answers.location, "目标人群": answers.target_group,
          "预计时长": answers.duration, "可用资源": answers.resources,
          "研究目标": answers.goal, "特别关注": answers.concerns,
          ...(selected ? { "参考场景模板": selected.name } : {}),
        }, theme,
      },
      (token) => { full += token; setResult(full); },
      () => {},
      (err) => { if (!full) setResult(`❌ 生成失败: ${err}`); },
    );
    setStreaming(false);
  };

  const updateAnswer = (k: string, v: string) => setAnswers(a => ({ ...a, [k]: v }));

  return (
    <div className="page">
      <h2>🎬 场景工坊</h2>
      <p className="subtitle">浏览12个预设场景模板，或用AI定制你的专属调查场景方案</p>

      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {(["browse","wizard","result"] as const).map(v => (
          <button key={v} onClick={() => setView(v)}
            className={view === v ? "btn-primary" : "btn-secondary"}
            style={{ padding: "6px 16px" }}>
            {v === "browse" ? "📋 模板库" : v === "wizard" ? "🧙 定制向导" : "📄 生成结果"}
          </button>
        ))}
      </div>

      {view === "browse" && (
        <>
          <div className="card-row" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
            {templates.map(t => (
              <div key={t.id} className="card" style={{ cursor: "pointer" }}
                onClick={() => setSelected(t)}>
                <div style={{ fontSize: 24, marginBottom: 4 }}>{t.icon}</div>
                <h4>{t.name}</h4>
                <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>{t.description}</p>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  适合方法: {t.suitable_methods.slice(0,2).join("、")}
                </div>
              </div>
            ))}
          </div>
          {selected && (
            <div className="md-content" style={{ marginTop: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3>{selected.icon} {selected.name}</h3>
                <button className="btn-primary" onClick={() => openWizard(selected)}>以此模板开始定制 →</button>
              </div>
              <p>{selected.description}</p>
              <h4>场景特征</h4>
              <ul>{selected.features.map((f,i) => <li key={i}>{f}</li>)}</ul>
              <h4>推荐方法</h4>
              <ul>{selected.suitable_methods.map((m,i) => <li key={i}>{m}</li>)}</ul>
              <h4>⚠️ 常见陷阱</h4>
              <ul>{selected.common_pitfalls.map((p,i) => <li key={i}>{p}</li>)}</ul>
              <h4>伦理注意</h4><p>{selected.ethical_notes}</p>
              <h4>🛠 推荐工具</h4><p>{selected.recommended_tools}</p>
            </div>
          )}
        </>
      )}

      {view === "wizard" && (
        <div className="profile-form">
          <h3>🧙 场景定制向导</h3>
          <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
            {selected ? `基于「${selected.name}」模板进行定制` : "回答以下6个问题，AI将为你生成专属场景方案"}
          </p>
          <div className="form-group"><label>🔍 调查地点</label>
            <input placeholder="例如：武汉市洪山区某城中村" value={answers.location}
              onChange={e => updateAnswer("location", e.target.value)} /></div>
          <div className="form-group"><label>👥 目标人群</label>
            <input placeholder="例如：外来务工人员（30-50岁）" value={answers.target_group}
              onChange={e => updateAnswer("target_group", e.target.value)} /></div>
          <div className="form-group"><label>⏱ 预计时长</label>
            <input placeholder="例如：2周驻点 + 15次深度访谈" value={answers.duration}
              onChange={e => updateAnswer("duration", e.target.value)} /></div>
          <div className="form-group"><label>💰 可用资源</label>
            <input placeholder="例如：2人团队、5000元经费、有社区联系人" value={answers.resources}
              onChange={e => updateAnswer("resources", e.target.value)} /></div>
          <div className="form-group"><label>🎯 研究目标</label>
            <textarea rows={2} placeholder="例如：了解外来务工人员子女的教育选择困境及其社会机制"
              value={answers.goal} onChange={e => updateAnswer("goal", e.target.value)} /></div>
          <div className="form-group"><label>⚠️ 特别关注/担忧</label>
            <textarea rows={2} placeholder="例如：担心受访者不愿开口、方言沟通困难"
              value={answers.concerns} onChange={e => updateAnswer("concerns", e.target.value)} /></div>
          <div className="button-row">
            <button className="btn-primary" onClick={generate}
              disabled={streaming || !answers.location || !answers.goal}>
              {streaming ? "AI生成中..." : "🚀 生成场景方案"}</button>
            <button className="btn-secondary" onClick={() => setView("browse")}>返回模板库</button>
          </div>
        </div>
      )}

      {view === "result" && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h3>📄 场景方案</h3>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn-secondary" onClick={() => setView("wizard")}>调整参数</button>
              <button className="btn-secondary" onClick={() => setView("browse")}>返回模板库</button>
            </div>
          </div>
          {streaming && !result && (
            <div className="loading-spinner-container"><div className="loading-spinner"/><p>AI 正在生成场景方案...</p></div>
          )}
          {result && <div className="md-content" dangerouslySetInnerHTML={safeHtml(result)} />}
          {streaming && result && <span className="copilot-cursor" style={{ fontSize: 16 }}>▊</span>}
        </div>
      )}
    </div>
  );
}
