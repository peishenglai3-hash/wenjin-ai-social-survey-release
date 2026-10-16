import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../hooks/useApp";
import api from "../api/client";
import "./Community.css";

interface MySkill {
  id: number;
  name: string;
  description: string;
  category: string;
  skill_type: string;
  is_public: boolean;
  usage_count: number;
}

export default function PublishSkill() {
  const { profile } = useApp();
  const [mySkills, setMySkills] = useState<MySkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [readme, setReadme] = useState("");
  const [exampleInput, setExampleInput] = useState("");
  const [exampleOutput, setExampleOutput] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState("");
  const [successId, setSuccessId] = useState<number | null>(null);

  useEffect(() => {
    if (!profile?.id) return;
    (async () => {
      try {
        const res = await api.get("/skills/list", { params: { profile_id: profile.id } });
        const all = res.data.skills || [];
        setMySkills(all);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    })();
  }, [profile?.id]);

  async function handlePublish() {
    if (!selectedId || !profile?.id) return;
    setPublishing(true);
    setError("");
    try {
      const res = await api.post("/community/skills/publish", {
        profile_id: profile.id,
        skill_id: selectedId,
        readme: readme.trim() || undefined,
        example_input: exampleInput.trim() || undefined,
        example_output: exampleOutput.trim() || undefined,
      });
      if (res.data.ok) {
        setSuccessId(res.data.skill.id);
      } else {
        setError(res.data.error || "发布失败");
      }
    } catch {
      setError("网络错误，请重试");
    } finally {
      setPublishing(false);
    }
  }

  const selectedSkill = mySkills.find((s) => s.id === selectedId);

  if (successId) {
    return (
      <div className="community-page">
        <div className="empty-state" style={{ background: "#ecfdf5", border: "1px solid #a7f3d0", borderRadius: 14, padding: 40 }}>
          <div className="empty-icon">🎉</div>
          <h3 style={{ color: "#065f46" }}>发布成功！</h3>
          <p style={{ color: "#065f46" }}>你的技能已出现在调研者社区中</p>
          <div style={{ marginTop: 16, display: "flex", gap: 10, justifyContent: "center" }}>
            <Link to={`/community/skills/${successId}`} className="btn btn-primary" style={{ textDecoration: "none", padding: "8px 16px" }}>
              查看发布内容
            </Link>
            <Link to="/community" className="btn" style={{ textDecoration: "none", padding: "8px 16px", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)" }}>
              返回社区
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="community-page">
      <Link to="/community" className="back-link">← 返回社区首页</Link>
      <h2>发布技能到社区</h2>
      <p className="subtitle">选择一个你创建的技能，补全说明后发布到调研者社区</p>

      {loading ? (
        <div className="community-loading">加载中…</div>
      ) : mySkills.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🛠️</div>
          <h3>你还没有创建技能</h3>
          <p>在AI助手中使用对话创建技能后，再回来发布</p>
        </div>
      ) : (
        <>
          {/* Step 1: Select skill */}
          <div className="publish-section">
            <h3>第一步：选择要发布的技能</h3>
            <p className="help-text">从你的技能库中选择一个</p>
            <select
              value={selectedId || ""}
              onChange={(e) => {
                const id = parseInt(e.target.value);
                setSelectedId(id || null);
                if (id) {
                  const skill = mySkills.find((s) => s.id === id);
                  if (skill?.is_public) {
                    setError("该技能已发布，如需更新请先取消发布");
                  } else {
                    setError("");
                  }
                }
              }}
            >
              <option value="">-- 选择技能 --</option>
              {mySkills.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.category}) {s.is_public ? "[已发布]" : ""}
                </option>
              ))}
            </select>
          </div>

          {selectedSkill && (
            <>
              {/* Step 2: Write README */}
              <div className="publish-section">
                <h3>第二步：撰写使用说明</h3>
                <p className="help-text">描述这个技能的使用方法、适用场景、注意事项，帮助其他调研者快速上手</p>
                <textarea
                  value={readme}
                  onChange={(e) => setReadme(e.target.value)}
                  placeholder={"## 适用场景\n\n这个技能适用于…\n\n## 使用方法\n\n1. …\n2. …\n\n## 注意事项\n\n- …"}
                  style={{ minHeight: 140 }}
                />
              </div>

              {/* Step 3: Examples */}
              <div className="publish-section">
                <h3>第三步：提供示例（可选）</h3>
                <p className="help-text">展示一个典型输入和期望的AI输出，让其他调研者了解效果</p>
                <label style={{ fontSize: 13, fontWeight: 600, display: "block", marginBottom: 4 }}>示例输入：</label>
                <textarea
                  value={exampleInput}
                  onChange={(e) => setExampleInput(e.target.value)}
                  placeholder="例如：请帮我设计一份关于社区治理的问卷…"
                  style={{ minHeight: 80, marginBottom: 12 }}
                />
                <label style={{ fontSize: 13, fontWeight: 600, display: "block", marginBottom: 4 }}>示例输出：</label>
                <textarea
                  value={exampleOutput}
                  onChange={(e) => setExampleOutput(e.target.value)}
                  placeholder="例如：以下是三个维度的问卷框架…"
                  style={{ minHeight: 80 }}
                />
              </div>

              {/* Publish button */}
              {error && (
                <div style={{ padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#dc2626", fontSize: 13, marginBottom: 12 }}>
                  {error}
                </div>
              )}
              <button
                className="btn btn-primary"
                onClick={handlePublish}
                disabled={publishing || !selectedId || !!selectedSkill?.is_public}
                style={{ padding: "12px 32px", fontSize: 16, width: "100%" }}
              >
                {publishing ? "⏳ 发布中…" : "🚀 发布到社区"}
              </button>
            </>
          )}
        </>
      )}
    </div>
  );
}
