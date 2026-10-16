import { useEffect, useState, useCallback } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import api from "../api/client";
import "./Community.css";

interface SkillSummary {
  id: number;
  name: string;
  description: string;
  category: string;
  skill_type: string;
  usage_count: number;
  fork_count: number;
  rating_avg: number;
  rating_count: number;
  published_at: string | null;
  author_id: number;
  tags: string[];
}

const CATEGORY_LABELS: Record<string, string> = {
  questionnaire: "📋 问卷设计",
  interview: "🎙 访谈指南",
  analysis: "📊 数据分析",
  writing: "✍️ 写作辅助",
  methodology: "🔬 方法论",
  general: "🔧 通用工具",
};

const SKILL_TYPE_LABELS: Record<string, string> = {
  prompt_template: "Prompt 模板",
  rule_chain: "规则链",
  custom_workflow: "自定义工作流",
};

export default function SkillMarket() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const category = searchParams.get("category") || "";
  const skillType = searchParams.get("skill_type") || "";
  const sort = searchParams.get("sort") || "latest";
  const search = searchParams.get("q") || "";

  const fetchSkills = useCallback(async () => {
    setLoading(true);
    try {
      const endpoint = search ? "/community/skills/search" : "/community/skills";
      const params: Record<string, string | number> = search
        ? { q: search, page, page_size: 20 }
        : { sort, page, page_size: 20 };
      if (!search) {
        if (category) params.category = category;
        if (skillType) params.skill_type = skillType;
      }
      const res = await api.get(endpoint, { params });
      setSkills(res.data.skills || []);
      setTotal(res.data.total || 0);
      setTotalPages(res.data.total_pages || 1);
    } catch {
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }, [category, skillType, sort, search, page]);

  useEffect(() => {
    void Promise.resolve().then(fetchSkills);
  }, [fetchSkills]);

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    next.delete("page");
    setSearchParams(next);
    setPage(1);
  }

  return (
    <div className="community-page">
      <Link to="/community" className="back-link">← 返回社区首页</Link>
      <h2>技能市场</h2>
      <p className="subtitle">{total} 个已发布技能，发现适合你的调查工具</p>

      {/* Filters */}
      <div className="filter-bar">
        <input
          className="search-input"
          type="text"
          placeholder="搜索技能名称、描述、标签…"
          value={search}
          onChange={(e) => updateParam("q", e.target.value)}
        />
        <select value={category} onChange={(e) => updateParam("category", e.target.value)}>
          <option value="">全部分类</option>
          {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select value={skillType} onChange={(e) => updateParam("skill_type", e.target.value)}>
          <option value="">全部类型</option>
          {Object.entries(SKILL_TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select value={sort} onChange={(e) => updateParam("sort", e.target.value)}>
          <option value="latest">最新发布</option>
          <option value="popular">最多使用</option>
          <option value="rating">最高评分</option>
          <option value="forks">最多Fork</option>
        </select>
      </div>

      {/* Results */}
      {loading ? (
        <div className="community-loading">搜索中…</div>
      ) : skills.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🔍</div>
          <h3>{search ? `未找到与"${search}"相关的技能` : "没有找到技能"}</h3>
          <p>{search ? "试试其他关键词" : "成为第一个发布技能的人"}</p>
        </div>
      ) : (
        <>
          <div className="skill-card-grid">
            {skills.map((s) => (
              <div key={s.id} className="skill-card" onClick={() => navigate(`/community/skills/${s.id}`)}>
                <div className="card-header">
                  <h4 className="card-name">{s.name}</h4>
                  <span className="card-category">{CATEGORY_LABELS[s.category] || s.category}</span>
                </div>
                <p className="card-desc">{s.description || "暂无描述"}</p>
                {s.tags.length > 0 && (
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {s.tags.slice(0, 3).map((t: string) => (
                      <span key={t} style={{ fontSize: 11, color: "var(--text-muted)", background: "var(--bg)", padding: "2px 6px", borderRadius: 4 }}>{t}</span>
                    ))}
                  </div>
                )}
                <div className="card-meta">
                  <span>⭐ {s.rating_avg > 0 ? s.rating_avg.toFixed(1) : "—"}</span>
                  <span>🍴 {s.fork_count}</span>
                  <span>📊 {s.usage_count}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 24 }}>
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="btn" style={{ padding: "6px 14px" }}>
                上一页
              </button>
              <span style={{ padding: "6px 10px", fontSize: 14, color: "var(--text-muted)" }}>
                {page} / {totalPages}
              </span>
              <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="btn" style={{ padding: "6px 14px" }}>
                下一页
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
