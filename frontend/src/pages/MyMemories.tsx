import { useState, useEffect, useCallback } from "react";
import { useApp } from "../hooks/useApp";
import api from "../api/client";

interface MemoryItem {
  id: number;
  category: string;
  key: string;
  value: string;
  confidence: number;
  importance: number;
  hit_count: number;
  source: string;
  created_at: string | null;
  last_hit_at: string | null;
}

const CAT_LABELS: Record<string, string> = {
  preference: "偏好",
  interest: "兴趣",
  expertise: "擅长",
  habit: "习惯",
  goal: "目标",
  constraint: "限制",
  methodology: "方法论立场",
  tool: "工具",
  pitfall: "常见问题",
  note: "备注",
};

const SORT_OPTIONS = [
  { value: "confidence", label: "置信度 ↓" },
  { value: "importance", label: "重要度 ↓" },
  { value: "recent", label: "最新" },
  { value: "hits", label: "引用次数 ↓" },
];

export default function MyMemories() {
  const { profile } = useApp();
  const pid = profile?.id || 1;

  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterCat, setFilterCat] = useState("");
  const [sortBy, setSortBy] = useState("confidence");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");

  const fetchMemories = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/memory/list", { params: { profile_id: pid } });
      setMemories(res.data.memories || []);
    } catch {
      /* offline / error */
    } finally {
      setLoading(false);
    }
  }, [pid]);

  useEffect(() => {
    void Promise.resolve().then(fetchMemories);
  }, [fetchMemories]);

  const confirmMemory = async (id: number) => {
    await api.post("/memory/confirm", { memory_id: id, profile_id: pid });
    setMemories((prev) =>
      prev.map((m) => (m.id === id ? { ...m, confidence: Math.min(1, m.confidence + 0.3) } : m))
    );
  };

  const suppressMemory = async (id: number) => {
    await api.post("/memory/suppress", { memory_id: id, profile_id: pid });
    setMemories((prev) => prev.filter((m) => m.id !== id));
  };

  const deleteMemory = async (id: number) => {
    if (!confirm("确定要删除这条记忆吗？")) return;
    await api.post("/memory/delete", { memory_id: id, profile_id: pid });
    setMemories((prev) => prev.filter((m) => m.id !== id));
  };

  const startEdit = (m: MemoryItem) => {
    setEditingId(m.id);
    setEditValue(m.value);
  };

  const saveEdit = async (id: number) => {
    await api.post("/memory/edit", { memory_id: id, profile_id: pid, value: editValue });
    setMemories((prev) =>
      prev.map((m) => (m.id === id ? { ...m, value: editValue } : m))
    );
    setEditingId(null);
  };

  // ── Filter & sort ──
  const categories = [...new Set(memories.map((m) => m.category))];

  let filtered = filterCat ? memories.filter((m) => m.category === filterCat) : memories;

  switch (sortBy) {
    case "importance":
      filtered = [...filtered].sort((a, b) => b.importance - a.importance);
      break;
    case "recent":
      filtered = [...filtered].sort(
        (a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
      );
      break;
    case "hits":
      filtered = [...filtered].sort((a, b) => b.hit_count - a.hit_count);
      break;
    default: // confidence
      filtered = [...filtered].sort((a, b) => b.confidence - a.confidence);
  }

  const grouped: Record<string, MemoryItem[]> = {};
  for (const m of filtered) {
    (grouped[m.category] ||= []).push(m);
  }

  return (
    <div className="page">
      <h2>🧠 AI 对我的理解</h2>
      <p className="subtitle">
        这些是AI从对话中自动提取的关于你的长期记忆。你可以确认、编辑或忽略它们。
      </p>

      {/* Filter bar */}
      <div className="memory-filter-bar">
        <select value={filterCat} onChange={(e) => setFilterCat(e.target.value)}>
          <option value="">全部类别</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {CAT_LABELS[c] || c}
            </option>
          ))}
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <span style={{ fontSize: 12, color: "var(--text-muted)", alignSelf: "center" }}>
          共 {memories.length} 条记忆
        </span>
      </div>

      {/* Loading */}
      {loading && (
        <div className="loading-spinner-container">
          <div className="loading-spinner" />
          <span style={{ color: "var(--text-muted)", marginTop: 12 }}>
            加载记忆数据...
          </span>
        </div>
      )}

      {/* Empty state */}
      {!loading && memories.length === 0 && (
        <div className="onboarding-card" style={{ textAlign: "center", padding: "40px 20px" }}>
          <span style={{ fontSize: 48 }}>🧠</span>
          <h3 style={{ margin: "16px 0 8px" }}>AI 还没有关于你的记忆</h3>
          <p style={{ color: "var(--text-muted)", maxWidth: 420, margin: "0 auto 20px" }}>
            与 <strong>AI 助手</strong> 多对话几次后，系统会自动从对话中提取你的研究偏好、方法论立场、常用工具等持久信息。
          </p>
          <a href="/copilot" style={{ color: "var(--primary)", fontWeight: 500 }}>
            → 去和 AI 聊天
          </a>
        </div>
      )}

      {/* Grouped memory cards */}
      {!loading &&
        Object.entries(grouped).map(([cat, items]) => (
          <div key={cat} className="memory-category-group">
            <h3 className="memory-category-header">
              {CAT_LABELS[cat] || cat}
              <span style={{ fontWeight: 400, fontSize: 13, color: "var(--text-muted)", marginLeft: 8 }}>
                {items.length} 条
              </span>
            </h3>
            {items.map((m) => (
              <div key={m.id} className={`memory-card ${(m.confidence || 0) < 0.15 ? "suppressed" : ""}`}>
                <div className="memory-card-header">
                  <span className="memory-key">{m.key}</span>
                  <span
                    className={`memory-confidence-badge ${(m.confidence || 0) < 0.15 ? "suppressed" : ""}`}
                  >
                    {Math.round((m.confidence || 0) * 100)}%
                  </span>
                </div>

                {editingId === m.id ? (
                  <div className="memory-edit-form">
                    <input
                      type="text"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      autoFocus
                    />
                    <button onClick={() => saveEdit(m.id)}>💾 保存</button>
                    <button onClick={() => setEditingId(null)}>取消</button>
                  </div>
                ) : (
                  <p className="memory-value">{m.value}</p>
                )}

                <div className="memory-meta">
                  <span className="memory-stars">
                    {"★".repeat(m.importance || 0)}
                    {"☆".repeat(5 - (m.importance || 0))}
                  </span>
                  <span>引用 {m.hit_count || 0} 次</span>
                  <span>{m.source}</span>
                  {m.last_hit_at && (
                    <span>最近: {new Date(m.last_hit_at).toLocaleDateString("zh")}</span>
                  )}
                </div>

                <div className="memory-actions">
                  <button onClick={() => startEdit(m)} title="编辑内容">
                    ✏️ 编辑
                  </button>
                  <button onClick={() => confirmMemory(m.id)} title="确认这条记忆">
                    👍 确认
                  </button>
                  <button onClick={() => suppressMemory(m.id)} title="不再关注">
                    🙈 忽略
                  </button>
                  <button onClick={() => deleteMemory(m.id)} title="删除">
                    🗑
                  </button>
                </div>
              </div>
            ))}
          </div>
        ))}
    </div>
  );
}
