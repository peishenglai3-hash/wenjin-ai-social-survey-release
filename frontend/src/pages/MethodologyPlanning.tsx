import { useState, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import api from "../api/client";
import { streamAI } from "../api/stream";
import { useApp } from "../hooks/useApp";
import QuickNav from "../components/QuickNav";

export default function MethodologyPlanning() {
  const { profile, project } = useApp();
  const location = useLocation();
  const [guidance, setGuidance] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);

  const handleGenerate = useCallback(async () => {
    if (!profile) return;
    setLoading(true);
    setGuidance("");
    await streamAI(
      "/profile/guidance/stream",
      profile as unknown as Record<string, unknown>,
      (token) => setGuidance((prev) => prev + token),
      () => setLoading(false),
      (err) => { setGuidance(err); setLoading(false); },
    );
  }, [profile]);

  // Auto-trigger guidance generation when navigated from Identity page
  useEffect(() => {
    const state = location.state as { autoGenerate?: boolean } | null;
    if (state?.autoGenerate && profile && !guidance && !loading) {
      void Promise.resolve().then(handleGenerate);
      // Clear the state so it doesn't re-trigger on re-renders
      window.history.replaceState({}, document.title);
    }
  }, [location.state, profile, guidance, loading, handleGenerate]);

  const handleDownload = async (fileType: "docx" | "md") => {
    if (!guidance) return;
    setDownloading(fileType);
    try {
      const title = "方法论指导";
      const res = await api.post("/export/download-content", {
        content: guidance,
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

  const handleSave = async () => {
    if (!project?.id) return;
    try {
      const content = guidance + (notes ? "\n\n---\n\n## 个人笔记\n\n" + notes : "");
      await api.put(`/projects/${project.id}`, { methodology_guidance: content });
      alert("方法论规划已保存到项目");
    } catch {
      alert("保存失败");
    }
  };

  return (
    <div className="page">
      <h2>方法论规划</h2>
      <p className="subtitle">基于你的身份画像，AI 生成个性化的调查方法论方案</p>

      {!profile && (
        <div className="warning-banner" style={{ marginBottom: 16 }}>
          请先在「身份设置」中完成个人档案，再生成方法论指导。
        </div>
      )}

      <div className="split-page">
        {/* ── Left: Inputs ── */}
        <div className="split-left">
          <button onClick={handleGenerate} disabled={loading} className="btn-primary">
            {loading ? "生成中..." : guidance ? "重新生成" : "生成方法论方案"}
          </button>
          {guidance && (
            <>
              <button onClick={handleSave} className="btn-secondary">保存到项目</button>
              <div className="button-row" style={{ flexWrap: "wrap" }}>
                <button
                  onClick={() => handleDownload("docx")}
                  disabled={downloading !== null}
                  className="btn-secondary"
                  style={{ background: "var(--primary)", color: "#fff", border: "none" }}
                >
                  {downloading === "docx" ? "下载中..." : "下载 Word (.docx)"}
                </button>
                <button
                  onClick={() => handleDownload("md")}
                  disabled={downloading !== null}
                  className="btn-secondary"
                >
                  {downloading === "md" ? "下载中..." : "下载 Markdown (.md)"}
                </button>
              </div>
            </>
          )}
          <div className="form-group">
            <label>个人笔记与补充</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="记录你的方法论思考、调整计划、特殊注意事项..."
              rows={8}
              style={{ width: "100%", padding: 12, borderRadius: 8, border: "1px solid var(--border)", resize: "vertical" }}
            />
          </div>
          {loading && !guidance && (
            <div style={{ padding: 12, background: "var(--surface)", borderRadius: 8, textAlign: "center", fontSize: 13 }}>
              <span className="dot connecting" style={{ display: "inline-block", marginRight: 8 }} />
              正在连接 AI 服务...
            </div>
          )}
        </div>

        {/* ── Right: Output ── */}
        {guidance ? (
          <div className="split-right">
            <div className="md-content" style={{ whiteSpace: "pre-wrap" }}>{guidance}</div>
          </div>
        ) : (
          <div className="split-right-empty">
            {loading
              ? "AI 正在根据你的身份画像生成方法论方案..."
              : "个性化方法论指导将在此处展示\n\n包含调查方法推荐、常见误区提醒、分步骤流程、伦理注意事项等"}
          </div>
        )}
      </div>

      <QuickNav
        currentPath="/methodology"
        visible={!!guidance}
        nextPath="/fieldwork"
        nextLabel="田野工具"
      />
    </div>
  );
}
