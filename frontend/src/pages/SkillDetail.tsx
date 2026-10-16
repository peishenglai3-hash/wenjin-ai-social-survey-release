import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApp } from "../hooks/useApp";
import api from "../api/client";
import "./Community.css";

interface SkillDetail {
  id: number;
  name: string;
  description: string;
  prompt_template: string;
  skill_type: string;
  category: string;
  tags: string[];
  usage_count: number;
  fork_count: number;
  rating_avg: number;
  rating_count: number;
  published_at: string | null;
  published_version: string;
  readme: string | null;
  example_input: string | null;
  example_output: string | null;
  forked_from_id: number | null;
  author_id: number;
  author: {
    id: number;
    role: string;
    experience_level: string;
    paradigm_preference: string;
  } | null;
  forked_from?: { id: number; name: string; author_id: number };
  forks: Array<{ id: number; name: string; author_id: number }>;
}

const ROLE_LABELS: Record<string, string> = {
  undergraduate: "本科生",
  graduate: "研究生",
  phd_candidate: "博士生",
  researcher: "研究员",
  faculty: "教师",
  practitioner: "实践者",
  other: "其他",
};

export default function SkillDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { profile } = useApp();
  const [skill, setSkill] = useState<SkillDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [forking, setForking] = useState(false);
  const [forkedId, setForkedId] = useState<number | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get(`/community/skills/${id}`);
        if (cancelled) return;
        if (res.data.error) {
          setSkill(null);
        } else {
          setSkill(res.data);
        }
      } catch {
        setSkill(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [id]);

  async function handleFork() {
    if (!profile?.id || !skill) return;
    setForking(true);
    try {
      const res = await api.post(`/community/skills/${skill.id}/fork`, {
        profile_id: profile.id,
      });
      if (res.data.ok) {
        setForkedId(res.data.skill.id);
      }
    } catch {
      // fork failed
    } finally {
      setForking(false);
    }
  }

  if (loading) return <div className="community-loading">加载中…</div>;
  if (!skill) {
    return (
      <div className="community-page">
        <Link to="/community/skills" className="back-link">← 返回技能市场</Link>
        <div className="empty-state">
          <div className="empty-icon">🔒</div>
          <h3>技能未找到</h3>
          <p>该技能不存在或未公开发布</p>
        </div>
      </div>
    );
  }

  const isOwn = profile?.id === skill.author_id;

  return (
    <div className="community-page">
      <Link to="/community/skills" className="back-link">← 返回技能市场</Link>

      <div className="skill-detail">
        <div className="detail-header">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <h2>{skill.name}</h2>
              <div className="detail-meta">
                <span>🏷 {skill.category}</span>
                <span>📦 v{skill.published_version}</span>
                <span>⭐ {skill.rating_avg > 0 ? `${skill.rating_avg.toFixed(1)} (${skill.rating_count})` : "暂无评分"}</span>
                <span>🍴 {skill.fork_count} Fork</span>
                <span>📊 {skill.usage_count} 次使用</span>
              </div>
            </div>
            {skill.forked_from && (
              <Link to={`/community/skills/${skill.forked_from.id}`} style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Forked from: {skill.forked_from.name}
              </Link>
            )}
          </div>
        </div>

        <div className="detail-body">
          {/* Description */}
          <div className="readme-section">
            <h3>📝 简介</h3>
            <p style={{ fontSize: 14, lineHeight: 1.6, color: "var(--text)", whiteSpace: "pre-wrap" }}>
              {skill.description || "暂无简介"}
            </p>
          </div>

          {/* README */}
          {skill.readme && (
            <div className="readme-section">
              <h3>📖 使用说明</h3>
              <div className="readme-content">{skill.readme}</div>
            </div>
          )}

          {/* Tags */}
          {skill.tags.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              {skill.tags.map((t: string) => (
                <span key={t} style={{
                  display: "inline-block", padding: "4px 10px", margin: "0 6px 6px 0",
                  background: "var(--primary-light, #eef2ff)", borderRadius: 20,
                  fontSize: 12, color: "var(--primary, #4f46e5)",
                }}>{t}</span>
              ))}
            </div>
          )}

          {/* Prompt Template */}
          <div className="prompt-preview">
            <h3>🔧 Prompt 模板</h3>
            <div className="prompt-code">{skill.prompt_template}</div>
          </div>

          {/* Examples */}
          {skill.example_input && (
            <div className="readme-section">
              <h3>📥 示例输入</h3>
              <div className="readme-content">{skill.example_input}</div>
            </div>
          )}
          {skill.example_output && (
            <div className="readme-section">
              <h3>📤 示例输出</h3>
              <div className="readme-content">{skill.example_output}</div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="detail-actions">
          {isOwn ? (
            <span style={{ fontSize: 13, color: "var(--text-muted)", padding: "8px 0" }}>
              ✅ 这是你发布的技能
            </span>
          ) : (
            <>
              <button
                className="btn btn-primary"
                onClick={handleFork}
                disabled={forking || forkedId !== null}
                style={{ padding: "10px 24px" }}
              >
                {forking ? "⏳ Fork中…" : forkedId ? "✅ 已Fork" : "🍴 Fork 到我的技能库"}
              </button>
              {forkedId && (
                <span style={{ fontSize: 13, color: "#059669", padding: "8px 0" }}>
                  已成功Fork！在你的技能库中查看
                </span>
              )}
            </>
          )}
        </div>

        {/* Author */}
        {skill.author && (
          <div className="author-card">
            <div className="author-avatar">👤</div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>
                {ROLE_LABELS[skill.author.role] || skill.author.role} · {skill.author.experience_level === "advanced" ? "资深" : skill.author.experience_level === "intermediate" ? "中级" : "初级"}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                偏好：{skill.author.paradigm_preference === "quantitative" ? "量化" : skill.author.paradigm_preference === "qualitative" ? "质性" : "混合方法"}
              </div>
            </div>
          </div>
        )}

        {/* Forks */}
        {skill.forks.length > 0 && (
          <div style={{ padding: "16px 24px", borderTop: "1px solid var(--border)" }}>
            <h3 style={{ fontSize: 14, margin: "0 0 8px" }}>🌿 此技能的Fork ({skill.forks.length})</h3>
            {skill.forks.map((f) => (
              <Link key={f.id} to={`/community/skills/${f.id}`} style={{ display: "block", fontSize: 13, padding: "4px 0", color: "var(--primary)" }}>
                {f.name}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
