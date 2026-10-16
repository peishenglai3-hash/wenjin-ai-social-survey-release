import { useState } from "react";
import api from "../api/client";
import { streamAI } from "../api/stream";
import { useApp } from "../hooks/useApp";
import QuickNav from "../components/QuickNav";

interface FeasibilityScores {
  theorySupport: number;
  methodMatch: number;
  dataAvailability: number;
  innovation: number;
  ethicsRisk: number;
}

function parseFeasibilityScores(text: string): FeasibilityScores | null {
  try {
    const match = text.match(/```feasibility_json\n([\s\S]*?)\n```/);
    if (match) return JSON.parse(match[1]);
    return null;
  } catch { return null; }
}

const SCORE_DIMS: { key: keyof FeasibilityScores; label: string; desc: string }[] = [
  { key: "theorySupport", label: "理论支撑", desc: "已有理论/文献的充分程度" },
  { key: "methodMatch", label: "方法匹配", desc: "研究方法与问题的适配度" },
  { key: "dataAvailability", label: "数据可获得性", desc: "数据来源的可行与便利程度" },
  { key: "innovation", label: "创新性", desc: "相对于现有研究的边际贡献" },
  { key: "ethicsRisk", label: "伦理风险", desc: "研究对被试/田野的潜在风险（越低越好）" },
];

export default function TopicDesign() {
  const { profile, project, setProject } = useApp();
  const [query, setQuery] = useState(project?.research_direction || "");
  const [paradigm, setParadigm] = useState(project?.paradigm || "qualitative");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);

  // Comparison Mode
  const [compareMode, setCompareMode] = useState(false);
  const [compareResults, setCompareResults] = useState<string[]>([]);
  const [compareLoading, setCompareLoading] = useState(false);

  // Feasibility Scoring
  const [feasibility, setFeasibility] = useState<FeasibilityScores | null>(null);
  const [scoringLoading, setScoringLoading] = useState(false);

  async function handleAsk() {
    if (!query.trim()) return;
    setLoading(true);
    setResult("");
    setFeasibility(null);
    await streamAI(
      "/topic/assist/stream",
      { query, paradigm },
      (token) => setResult((prev) => prev + token),
      () => setLoading(false),
      (err) => { setResult(err); setLoading(false); },
    );
  }

  async function handleCompare() {
    if (!query.trim()) return;
    setCompareLoading(true);
    setCompareResults([]);
    const angles = [
      { paradigm: "qualitative", label: "【视角一：质性路径】\n" },
      { paradigm: "quantitative", label: "【视角二：量化路径】\n" },
      { paradigm: "mixed", label: "【视角三：混合方法路径】\n" },
    ];
    const results: string[] = ["", "", ""];
    try {
      await Promise.all(angles.map(async (angle, i) => {
        await streamAI(
          "/topic/assist/stream",
          { query: `${query}（${angle.label.trim()}）`, paradigm: angle.paradigm },
          (token) => { results[i] += token; setCompareResults([...results]); },
          () => {},
          (err) => { results[i] = `生成失败: ${err}`; setCompareResults([...results]); },
        );
      }));
    } finally { setCompareLoading(false); }
  }

  async function handleScoreFeasibility() {
    if (!result) return;
    setScoringLoading(true);
    setFeasibility(null);
    let scoringText = "";
    await streamAI(
      "/topic/assist/stream",
      {
        query: `基于以下选题论证，请对该选题进行五维度可行性评分（1-5分），以JSON格式输出：\n\n${result.slice(0, 3000)}\n\n请严格按照以下JSON格式输出：\n\`\`\`feasibility_json\n{"theorySupport": 4, "methodMatch": 3, "dataAvailability": 4, "innovation": 5, "ethicsRisk": 2}\n\`\`\``,
        paradigm,
      },
      (token) => { scoringText += token; },
      () => {
        setScoringLoading(false);
        const parsed = parseFeasibilityScores(scoringText);
        if (parsed) setFeasibility(parsed);
      },
      () => setScoringLoading(false),
    );
  }

  const handleDownload = async (fileType: "docx" | "md") => {
    if (!result) return;
    setDownloading(fileType);
    try {
      const title = query.trim().slice(0, 30) || "选题论证";
      const res = await api.post("/export/download-content", {
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
    } catch {
      alert(`${fileType.toUpperCase()} 下载失败`);
    } finally { setDownloading(null); }
  };

  async function handleSaveAsProject() {
    if (!result || !profile?.id) return;
    setSaving(true);
    try {
      const title = query.trim().slice(0, 50) || "未命名项目";
      const res = await api.post("/projects", {
        profile_id: profile.id, title, research_direction: query, paradigm,
      });
      const newProject = res.data;
      await api.put(`/projects/${newProject.id}`, { topic_argumentation: result });
      setProject({ ...newProject, topic_argumentation: result });
      alert(`项目"${title}"已创建！可前往问卷设计或方法论规划继续。`);
    } catch {
      alert("保存项目失败");
    } finally { setSaving(false); }
  }

  function ScoreBar({ value, label, desc }: { value: number; label: string; desc: string }) {
    const color = label === "伦理风险"
      ? value <= 2 ? "#10B981" : value <= 3 ? "#F59E0B" : "#EF4444"
      : value >= 4 ? "#10B981" : value >= 3 ? "#F59E0B" : "#EF4444";
    return (
      <div style={{ marginBottom: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
          <span style={{ fontSize: 13, fontWeight: 500 }}>{label}</span>
          <span style={{ fontSize: 13, color }}>{value}/5</span>
        </div>
        <div style={{ background: "#E5E7EB", borderRadius: 4, height: 8, overflow: "hidden" }}>
          <div style={{
            width: `${(value / 5) * 100}%`, height: "100%",
            background: color, borderRadius: 4, transition: "width 0.3s",
          }} />
        </div>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{desc}</span>
      </div>
    );
  }

  return (
    <div className="page">
      <h2>定需求 · 选题工作台</h2>
      <p className="subtitle">输入研究方向，AI 辅助选题论证与方法论建议（流式实时生成）</p>

      {!profile?.id && (
        <div className="warning-banner" style={{ marginBottom: 16 }}>
          请先在「身份设置」中保存你的调查者档案，才能创建项目。
        </div>
      )}

      <div className="split-page">
        <div className="split-left">
          <div className="form-group">
            <label>研究方向</label>
            <input value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="例如：城市社区老年居民的公共参与意愿及其影响因素"
              onKeyDown={(e) => e.key === "Enter" && handleAsk()} />
          </div>
          <div className="form-group">
            <label>研究范式</label>
            <select value={paradigm} onChange={(e) => setParadigm(e.target.value)}>
              <option value="qualitative">质性研究</option>
              <option value="quantitative">量化研究</option>
              <option value="mixed">混合方法</option>
            </select>
          </div>

          <div className="form-group">
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input type="checkbox" checked={compareMode}
                onChange={(e) => setCompareMode(e.target.checked)} />
              <span>对比模式 — 同时生成3个视角的选题方案</span>
            </label>
          </div>

          {!compareMode ? (
            <button onClick={handleAsk} disabled={loading || !query.trim()} className="btn-primary">
              {loading ? "AI思考中..." : "开始论证"}
            </button>
          ) : (
            <button onClick={handleCompare} disabled={compareLoading || !query.trim()}
              className="btn-primary" style={{ background: "var(--accent)" }}>
              {compareLoading ? "AI 正在生成3个视角..." : "生成三视角对比"}
            </button>
          )}

          {result && !loading && (
            <>
              <button onClick={handleSaveAsProject} disabled={saving} className="btn-secondary">
                {saving ? "保存中..." : "保存为项目 → 继续问卷设计"}
              </button>
              <button onClick={handleScoreFeasibility} disabled={scoringLoading}
                className="btn-secondary" style={{ borderColor: "var(--accent)", color: "var(--accent)" }}>
                {scoringLoading ? "评分中..." : feasibility ? "重新评分" : "五维可行性评分"}
              </button>
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

          {loading && !result && (
            <div style={{ padding: 12, background: "var(--surface)", borderRadius: 8, textAlign: "center", fontSize: 13 }}>
              <span className="dot connecting" style={{ display: "inline-block", marginRight: 8 }} />
              正在连接 AI 服务...
            </div>
          )}
        </div>

        <div className="split-right" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {feasibility && (
            <div style={{
              padding: "16px 20px", background: "linear-gradient(135deg, #f0f9ff, #faf5ff)",
              borderRadius: 10, border: "1px solid #E0E7FF",
            }}>
              <h4 style={{ margin: "0 0 12px 0", fontSize: 15 }}>选题可行性五维评分</h4>
              {SCORE_DIMS.map((d) => (
                <ScoreBar key={d.key} value={feasibility[d.key]} label={d.label} desc={d.desc} />
              ))}
              <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8, textAlign: "center" }}>
                评分由AI基于学术方法论基准生成，仅供参考。最终判断请结合导师意见和实际情况。
              </p>
            </div>
          )}

          {compareResults.length > 0 && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
              {compareResults.map((text, i) => (
                <div key={i} style={{
                  padding: 12, background: "var(--surface)", borderRadius: 8,
                  border: "1px solid var(--border)", fontSize: 12, maxHeight: 400, overflowY: "auto",
                }}>
                  <div className="md-content" style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
                    {text || (compareLoading ? "生成中..." : "")}
                  </div>
                </div>
              ))}
            </div>
          )}

          {result && compareResults.length === 0 && (
            <div className="md-content" style={{ whiteSpace: "pre-wrap" }}>
              {result}
              {loading && <span className="dot connecting" style={{ display: "inline-block", marginLeft: 4, verticalAlign: "middle" }} />}
            </div>
          )}

          {!result && compareResults.length === 0 && (
            <div className="split-right-empty">
              {loading || compareLoading
                ? "AI 正在生成选题论证报告..."
                : "AI 选题论证报告将在此处实时展示\n\n输入研究方向并点击「开始论证」\n\n试试「对比模式」同时查看3个视角的方案"}
            </div>
          )}
        </div>
      </div>

      <QuickNav
        currentPath="/topic"
        visible={!!result}
        nextPath="/questionnaire"
        nextLabel="问卷设计"
      />
    </div>
  );
}
