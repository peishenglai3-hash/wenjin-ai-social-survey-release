/**
 * CodebookPanel — qualitative coding codebook manager.
 * Tree view + detail editor + AI suggestion panel.
 */
import { useState, useEffect, useCallback, type FC } from "react";
import { useApp } from "../hooks/useApp";
import ConfidenceBadge from "./ConfidenceBadge";
import {
  fetchCodebook,
  createCode,
  updateCode,
  deleteCode,
  suggestCodes,
  exportCodebook,
} from "../api/coding";
import type { CodebookCode, AISuggestion } from "../types/coding";
import { getErrorMessage } from "../utils/errors";

const PARADIGMS: Record<string, string> = {
  "": "全部范式",
  thematic_analysis: "主题分析",
  grounded_theory: "扎根理论",
  content_analysis: "内容分析",
  framework_analysis: "框架分析",
};

const DEFAULT_COLOR = "#3B82F6";

interface CodeForm {
  name: string;
  definition: string;
  example: string;
  exclusion_criteria: string;
  parent_code_id: number | null;
  paradigm: string;
  color: string;
}

const emptyForm: CodeForm = {
  name: "",
  definition: "",
  example: "",
  exclusion_criteria: "",
  parent_code_id: null,
  paradigm: "thematic_analysis",
  color: DEFAULT_COLOR,
};

const CodebookPanel: FC = () => {
  const { project } = useApp();
  const projectId = project?.id || 0;

  // ── State ──
  const [codes, setCodes] = useState<CodebookCode[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [paradigm, setParadigm] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Edit form
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<CodeForm>(emptyForm);
  const [saving, setSaving] = useState(false);

  // AI suggestions
  const [showAI, setShowAI] = useState(false);
  const [aiTranscript, setAiTranscript] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiSuggestions, setAiSuggestions] = useState<AISuggestion[]>([]);
  const [aiError, setAiError] = useState("");

  // ── Load codes ──
  const loadCodes = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const data = await fetchCodebook(projectId, paradigm || undefined);
      setCodes(data.codes || []);
    } catch (error: unknown) {
      setError(getErrorMessage(error, "加载编码簿失败"));
    } finally {
      setLoading(false);
    }
  }, [projectId, paradigm]);

  useEffect(() => {
    void Promise.resolve().then(loadCodes);
  }, [loadCodes]);

  // ── Tree helpers ──
  const rootCodes = codes.filter((c) => !c.parent_code_id);
  const childrenOf = (parentId: number) => codes.filter((c) => c.parent_code_id === parentId);

  // ── Select code ──
  const selectCode = (code: CodebookCode) => {
    setSelectedId(code.id);
    setEditing(false);
    setShowAI(false);
  };

  // ── Start editing ──
  const startEdit = (code?: CodebookCode) => {
    if (code) {
      setForm({
        name: code.name,
        definition: code.definition,
        example: code.example,
        exclusion_criteria: code.exclusion_criteria,
        parent_code_id: code.parent_code_id,
        paradigm: code.paradigm,
        color: code.color,
      });
      setSelectedId(code.id);
    } else {
      setForm({ ...emptyForm });
      setSelectedId(null);
    }
    setEditing(true);
    setShowAI(false);
  };

  // ── Save ──
  const handleSave = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      if (selectedId && codes.find((c) => c.id === selectedId)) {
        await updateCode(selectedId, form);
      } else {
        await createCode(projectId, form);
      }
      setEditing(false);
      await loadCodes();
    } catch (error: unknown) {
      setError(getErrorMessage(error, "保存失败"));
    } finally {
      setSaving(false);
    }
  };

  // ── Delete ──
  const handleDelete = async (id: number) => {
    if (!confirm("确定删除此编码？子编码将保留但失去父级关系。")) return;
    try {
      await deleteCode(id);
      if (selectedId === id) {
        setSelectedId(null);
        setEditing(false);
      }
      await loadCodes();
    } catch (error: unknown) {
      setError(getErrorMessage(error, "删除失败"));
    }
  };

  // ── AI Suggest ──
  const handleAISuggest = async () => {
    if (!aiTranscript.trim()) return;
    setAiLoading(true);
    setAiError("");
    setAiSuggestions([]);
    try {
      const data = await suggestCodes(
        aiTranscript,
        project?.research_direction || "社会调查",
        projectId,
        paradigm || undefined,
      );
      setAiSuggestions(data.suggestions || []);
    } catch (error: unknown) {
      setAiError(getErrorMessage(error, "AI建议请求失败"));
    } finally {
      setAiLoading(false);
    }
  };

  const handleAdoptSuggestion = async (s: AISuggestion) => {
    try {
      await createCode(projectId, {
        name: s.name,
        definition: s.definition,
        example: s.example || "",
        paradigm: s.paradigm || paradigm || "thematic_analysis",
        color: DEFAULT_COLOR,
      });
      await loadCodes();
      setAiSuggestions((prev) => prev.filter((x) => x.name !== s.name));
    } catch (error: unknown) {
      setError(getErrorMessage(error, "添加建议编码失败"));
    }
  };

  // ── Export ──
  const handleExport = async () => {
    try {
      const md = await exportCodebook(projectId, "markdown");
      const blob = new Blob([md], { type: "text/markdown; charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `codebook_project_${projectId}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("导出失败");
    }
  };

  const selected = codes.find((c) => c.id === selectedId);

  // ── Render ──
  if (!projectId) {
    return (
      <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
        请先在首页创建或选择一个项目
      </div>
    );
  }

  return (
    <div>
      {/* ── Toolbar ── */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
        <select
          value={paradigm}
          onChange={(e) => { setParadigm(e.target.value); setSelectedId(null); setEditing(false); }}
          style={{ width: "auto", minWidth: 120 }}
        >
          {Object.entries(PARADIGMS).map(([v, label]) => (
            <option key={v} value={v}>{label}</option>
          ))}
        </select>
        <button onClick={() => startEdit()} className="btn-primary" style={{ fontSize: 13 }}>
          ＋ 添加编码
        </button>
        <button onClick={() => { setShowAI(!showAI); setEditing(false); }} className="btn-secondary" style={{ fontSize: 13 }}>
          🤖 AI建议
        </button>
        <button onClick={handleExport} disabled={codes.length === 0} className="btn-secondary" style={{ fontSize: 13 }}>
          📥 导出
        </button>
        <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: "auto" }}>
          {codes.length} 个编码
        </span>
      </div>

      {error && (
        <div style={{ padding: "8px 12px", background: "#fee2e2", color: "#dc2626", borderRadius: 8, marginBottom: 12, fontSize: 13 }}>
          {error}
          <button onClick={() => setError("")} style={{ marginLeft: 8, cursor: "pointer", background: "none", border: "none", color: "#dc2626" }}>✕</button>
        </div>
      )}

      <div className="split-page">
        {/* ── Left: Code Tree ── */}
        <div className="split-left" style={{ maxHeight: "calc(100vh - 280px)", overflowY: "auto" }}>
          {loading ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--text-muted)" }}>加载中...</div>
          ) : codes.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
              <p>编码簿为空</p>
              <p style={{ marginTop: 4 }}>点击"＋ 添加编码"创建第一个编码，或使用"🤖 AI建议"从转录文本中提取</p>
            </div>
          ) : (
            <div>
              {rootCodes.map((code) => (
                <TreeNode
                  key={code.id}
                  code={code}
                  children={childrenOf(code.id)}
                  selectedId={selectedId}
                  onSelect={selectCode}
                  depth={0}
                />
              ))}
            </div>
          )}
        </div>

        {/* ── Right: Detail / Edit / AI ── */}
        <div className="split-right" style={{ maxHeight: "calc(100vh - 280px)", overflowY: "auto" }}>
          {showAI ? (
            /* ── AI Suggestion Panel ── */
            <div>
              <h4 style={{ marginTop: 0 }}>🤖 AI 编码建议</h4>
              <div className="form-group">
                <label>粘贴访谈转录文本</label>
                <textarea
                  value={aiTranscript}
                  onChange={(e) => setAiTranscript(e.target.value)}
                  placeholder="将访谈转录文本粘贴到这里，AI将建议适合的编码..."
                  rows={6}
                  style={{ width: "100%", padding: 12, borderRadius: 8, border: "1px solid var(--border)", resize: "vertical" }}
                />
              </div>
              <button onClick={handleAISuggest} disabled={aiLoading || !aiTranscript.trim()} className="btn-primary">
                {aiLoading ? "分析中..." : "开始分析"}
              </button>

              {aiError && (
                <div style={{ marginTop: 12, padding: 8, background: "#fee2e2", borderRadius: 8, color: "#dc2626", fontSize: 13 }}>
                  {aiError}
                </div>
              )}

              {aiSuggestions.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 8 }}>
                    💡 {aiSuggestions.length} 条建议编码
                  </p>
                  {aiSuggestions.map((s, i) => (
                    <div
                      key={i}
                      style={{
                        padding: 12,
                        background: "var(--surface)",
                        border: "1px solid var(--border)",
                        borderRadius: 8,
                        marginBottom: 8,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <strong style={{ color: "var(--primary)" }}>{s.name}</strong>
                        {s.confidence !== undefined && (
                          <ConfidenceBadge confidence={s.confidence} size="sm" />
                        )}
                      </div>
                      <p style={{ fontSize: 13, margin: "4px 0", color: "var(--text)" }}>{s.definition}</p>
                      {s.example && (
                        <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
                          示例: {s.example}
                        </p>
                      )}
                      <button
                        onClick={() => handleAdoptSuggestion(s)}
                        className="btn-primary"
                        style={{ fontSize: 12, marginTop: 8, padding: "3px 12px" }}
                      >
                        ＋ 添加到编码簿
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : editing ? (
            /* ── Edit Form ── */
            <div>
              <h4 style={{ marginTop: 0 }}>
                {selectedId && codes.find((c) => c.id === selectedId) ? "编辑编码" : "新建编码"}
              </h4>
              <div className="form-group">
                <label>编码名称 *</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="例如: 社会适应策略"
                  style={{ width: "100%" }}
                />
              </div>
              <div className="form-group">
                <label>定义</label>
                <textarea
                  value={form.definition}
                  onChange={(e) => setForm({ ...form, definition: e.target.value })}
                  placeholder="此编码的详细定义..."
                  rows={3}
                  style={{ width: "100%", padding: 8, borderRadius: 8, border: "1px solid var(--border)", resize: "vertical" }}
                />
              </div>
              <div className="form-group">
                <label>示例</label>
                <textarea
                  value={form.example}
                  onChange={(e) => setForm({ ...form, example: e.target.value })}
                  placeholder="文本示例..."
                  rows={2}
                  style={{ width: "100%", padding: 8, borderRadius: 8, border: "1px solid var(--border)", resize: "vertical" }}
                />
              </div>
              <div className="form-group">
                <label>排除标准</label>
                <input
                  value={form.exclusion_criteria}
                  onChange={(e) => setForm({ ...form, exclusion_criteria: e.target.value })}
                  placeholder="不应归入此编码的情况..."
                  style={{ width: "100%" }}
                />
              </div>
              <div style={{ display: "flex", gap: 12 }}>
                <div className="form-group" style={{ flex: 1 }}>
                  <label>范式</label>
                  <select value={form.paradigm} onChange={(e) => setForm({ ...form, paradigm: e.target.value })}>
                    {Object.entries(PARADIGMS).filter(([v]) => v !== "").map(([v, label]) => (
                      <option key={v} value={v}>{label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label>父编码</label>
                  <select
                    value={form.parent_code_id || ""}
                    onChange={(e) => setForm({ ...form, parent_code_id: e.target.value ? Number(e.target.value) : null })}
                  >
                    <option value="">无（根编码）</option>
                    {codes.filter((c) => c.id !== selectedId).map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>颜色</label>
                  <input
                    type="color"
                    value={form.color}
                    onChange={(e) => setForm({ ...form, color: e.target.value })}
                    style={{ width: 48, height: 36, padding: 2, cursor: "pointer" }}
                  />
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <button onClick={handleSave} disabled={saving || !form.name.trim()} className="btn-primary">
                  {saving ? "保存中..." : "保存"}
                </button>
                <button onClick={() => { setEditing(false); setSelectedId(null); }} className="btn-secondary">取消</button>
                {selectedId && codes.find((c) => c.id === selectedId) && (
                  <button
                    onClick={() => handleDelete(selectedId)}
                    className="btn-secondary"
                    style={{ color: "#dc2626", borderColor: "#dc2626", marginLeft: "auto" }}
                  >
                    删除
                  </button>
                )}
              </div>
            </div>
          ) : selected ? (
            /* ── Detail View ── */
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
                    <span
                      style={{
                        display: "inline-block",
                        width: 14,
                        height: 14,
                        borderRadius: 3,
                        background: selected.color || DEFAULT_COLOR,
                      }}
                    />
                    {selected.name}
                  </h3>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                    {PARADIGMS[selected.paradigm] || selected.paradigm} · 版本 {selected.version}
                    {selected.parent_code_id ? ` · 子编码` : ` · 根编码 (${childrenOf(selected.id).length} 个子编码)`}
                  </p>
                </div>
                <button onClick={() => startEdit(selected)} className="btn-secondary" style={{ fontSize: 13 }}>
                  ✏️ 编辑
                </button>
              </div>

              {selected.definition && (
                <div style={{ marginTop: 16 }}>
                  <strong style={{ fontSize: 13 }}>定义</strong>
                  <p style={{ fontSize: 14, marginTop: 4, lineHeight: 1.6 }}>{selected.definition}</p>
                </div>
              )}
              {selected.example && (
                <div style={{ marginTop: 12 }}>
                  <strong style={{ fontSize: 13 }}>示例</strong>
                  <p style={{ fontSize: 13, marginTop: 4, padding: 8, background: "var(--primary-light)", borderRadius: 6, fontStyle: "italic" }}>
                    "{selected.example}"
                  </p>
                </div>
              )}
              {selected.exclusion_criteria && (
                <div style={{ marginTop: 12 }}>
                  <strong style={{ fontSize: 13 }}>排除标准</strong>
                  <p style={{ fontSize: 13, marginTop: 4, color: "var(--text-muted)" }}>{selected.exclusion_criteria}</p>
                </div>
              )}

              {/* Child codes */}
              {childrenOf(selected.id).length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <strong style={{ fontSize: 13 }}>子编码</strong>
                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                    {childrenOf(selected.id).map((child) => (
                      <button
                        key={child.id}
                        onClick={() => selectCode(child)}
                        className="card-btn"
                        style={{ textAlign: "left", padding: "8px 12px" }}
                      >
                        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ width: 10, height: 10, borderRadius: 2, background: child.color, display: "inline-block" }} />
                          {child.name}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* ── Empty state ── */
            <div style={{ textAlign: "center", padding: 32, color: "var(--text-muted)", fontSize: 13 }}>
              <p style={{ fontSize: 40, margin: 0 }}>📋</p>
              <p style={{ marginTop: 12 }}>选择左侧编码查看详情</p>
              <p>或点击"＋ 添加编码"创建新编码</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/** Recursive tree node for a single code. */
const TreeNode: FC<{
  code: CodebookCode;
  children: CodebookCode[];
  selectedId: number | null;
  onSelect: (c: CodebookCode) => void;
  depth: number;
}> = ({ code, children, selectedId, onSelect, depth }) => {
  const isSelected = code.id === selectedId;
  const hasChildren = children.length > 0;

  return (
    <div>
      <button
        onClick={() => onSelect(code)}
        className={`card-btn ${isSelected ? "selected" : ""}`}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          width: "100%",
          textAlign: "left",
          padding: "6px 10px",
          marginBottom: 2,
          marginLeft: depth * 16,
          fontSize: 13,
          border: isSelected ? "1px solid var(--primary)" : "1px solid transparent",
        }}
      >
        <span
          style={{
            width: 10,
            height: 10,
            borderRadius: 2,
            background: code.color || DEFAULT_COLOR,
            flexShrink: 0,
            display: "inline-block",
          }}
        />
        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {code.name}
        </span>
        {hasChildren && (
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{children.length}</span>
        )}
      </button>
      {hasChildren &&
        children.map((child) => (
          <TreeNode
            key={child.id}
            code={child}
            children={[]}
            selectedId={selectedId}
            onSelect={onSelect}
            depth={depth + 1}
          />
        ))}
    </div>
  );
};

export default CodebookPanel;
