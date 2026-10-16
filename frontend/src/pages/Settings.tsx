import { useState, useEffect, useCallback, useMemo } from "react";
import api from "../api/client";
import { useApp } from "../hooks/useApp";
import SpectrumSliders, { type SpectrumDim, type SpectrumGroup } from "../components/SpectrumSliders";

interface SettingsOptions {
  ai_model_pref: { id: string; label: string; desc: string }[];
  ai_hint_frequency: { id: string; label: string; desc: string }[];
  ui_font_size: { id: string; label: string }[];
  default_export_format: { id: string; label: string; theme: string }[];
  auto_save_interval: { id: string; label: string }[];
}

type SettingValue = string | number | boolean | null;

type TabId = "ai" | "ui" | "defaults" | "privacy";

const TABS: { id: TabId; label: string; icon: string; desc: string }[] = [
  { id: "ai", label: "AI 行为偏好", icon: "🧠", desc: "调整 AI 输出风格、温度、提示频率等" },
  { id: "ui", label: "界面与无障碍", icon: "🎨", desc: "字号、对比度、动画效果等视觉偏好" },
  { id: "defaults", label: "项目默认值", icon: "📋", desc: "新建项目时自动填入的默认选项" },
  { id: "privacy", label: "数据与隐私", icon: "🔒", desc: "自动保存、历史保留、数据导出" },
];

const SPECTRUM_GROUPS: SpectrumGroup[] = [
  { label: "方法论取向 · 研究设计与分析偏好", dimIds: ["theory_driven", "methodological_rigidity", "analysis_depth", "structure_preference"] },
  { label: "互动方式 · 在场与技术使用", dimIds: ["participation_level", "tech_dependency"] },
  { label: "表达风格 · 写作与学习偏好", dimIds: ["writing_style", "learning_preference"] },
];

export default function Settings() {
  const { profile, setProfile } = useApp();
  const [activeTab, setActiveTab] = useState<TabId>("ai");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const [spectrumDims, setSpectrumDims] = useState<SpectrumDim[]>([]);
  const [options, setOptions] = useState<SettingsOptions | null>(null);
  const [spectrum, setSpectrum] = useState<Record<string, number>>({});
  const [settings, setSettings] = useState<Record<string, SettingValue>>({});

  // Load defaults metadata + current settings
  useEffect(() => {
    const load = async () => {
      try {
        const metaRes = await api.get("/settings/defaults");
        setSpectrumDims(metaRes.data.spectrum_dimensions || []);
        setOptions(metaRes.data.options || null);

        if (profile?.id) {
          const res = await api.get(`/settings/${profile.id}`);
          if (res.data.spectrum) {
            setSpectrum(res.data.spectrum);
            for (const d of metaRes.data.spectrum_dimensions || []) {
              if (!(d.id in res.data.spectrum)) {
                setSpectrum((s) => ({ ...s, [d.id]: 3 }));
              }
            }
          }
          if (res.data.settings) setSettings(res.data.settings);
        } else {
          const defaults = metaRes.data.defaults || {};
          setSettings(defaults);
          const spec: Record<string, number> = {};
          for (const d of metaRes.data.spectrum_dimensions || []) spec[d.id] = 3;
          setSpectrum(spec);
        }
      } catch {
        // Offline fallback
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [profile?.id]);

  const showMsg = (type: "success" | "error", text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 3000);
  };

  const saveSpectrum = useCallback(async () => {
    if (!profile?.id) { showMsg("error", "请先保存身份档案后再调整光谱"); return; }
    setSaving(true);
    try {
      const res = await api.patch(`/settings/${profile.id}`, spectrum);
      if (res.data.spectrum) setSpectrum(res.data.spectrum);
      showMsg("success", "光谱已保存");
    } catch {
      showMsg("error", "保存失败，请重试");
    } finally { setSaving(false); }
  }, [profile?.id, spectrum]);

  const saveSettings = useCallback(async (updated: Record<string, SettingValue>) => {
    if (!profile?.id) { showMsg("error", "请先保存身份档案"); return; }
    setSaving(true);
    try {
      const res = await api.patch(`/settings/${profile.id}`, updated);
      if (res.data.settings) {
        setSettings(res.data.settings);
        setProfile({ ...profile, ...res.data.settings });
      }
      showMsg("success", "设置已保存");
    } catch {
      showMsg("error", "保存失败");
    } finally { setSaving(false); }
  }, [profile, setProfile]);

  const updateSetting = (key: string, value: SettingValue) => {
    const updated = { ...settings, [key]: value };
    setSettings(updated);
    saveSettings({ [key]: value });
  };

  const updateSpectrum = (dimId: string, value: number) => {
    setSpectrum((s) => ({ ...s, [dimId]: value }));
  };

  const handleReset = async () => {
    if (!profile?.id) return;
    if (!window.confirm("确定要重置所有设置为默认值吗？此操作不可撤销。")) return;
    setSaving(true);
    try {
      await api.post(`/settings/${profile.id}/reset`);
      const metaRes = await api.get("/settings/defaults");
      const defaults = metaRes.data.defaults || {};
      setSettings(defaults);
      const spec: Record<string, number> = {};
      for (const d of metaRes.data.spectrum_dimensions || []) spec[d.id] = 3;
      setSpectrum(spec);
      showMsg("success", "已重置所有设置");
    } catch {
      showMsg("error", "重置失败");
    } finally { setSaving(false); }
  };

  // ── Search logic ──
  const q = searchQuery.trim().toLowerCase();

  // Build a flat list of all searchable items across tabs
  const allSearchItems = useMemo(() => {
    const items: { tab: TabId; key: string; label: string; desc: string }[] = [];
    // AI tab: spectrum dims
    for (const dim of spectrumDims) {
      items.push({ tab: "ai", key: dim.id, label: dim.label, desc: `${dim.left} — ${dim.right} · ${dim.desc}` });
    }
    // AI tab: temperature
    items.push({ tab: "ai", key: "ai_temperature", label: "输出温度", desc: "控制 AI 创造力，越低越严谨" });
    // AI tab: model pref
    for (const opt of options?.ai_model_pref || []) {
      items.push({ tab: "ai", key: `ai_model_pref_${opt.id}`, label: `模型偏好 · ${opt.label}`, desc: opt.desc });
    }
    // AI tab: hint frequency
    for (const opt of options?.ai_hint_frequency || []) {
      items.push({ tab: "ai", key: `ai_hint_frequency_${opt.id}`, label: `提示频率 · ${opt.label}`, desc: opt.desc });
    }
    // UI tab
    for (const opt of options?.ui_font_size || []) {
      items.push({ tab: "ui", key: `ui_font_size_${opt.id}`, label: `字号 · ${opt.label}`, desc: "" });
    }
    items.push({ tab: "ui", key: "ui_high_contrast", label: "高对比度模式", desc: "增强色彩对比度，辅助视觉障碍用户" });
    // Defaults tab
    for (const opt of options?.default_export_format || []) {
      items.push({ tab: "defaults", key: `default_export_format_${opt.id}`, label: `导出格式 · ${opt.label}`, desc: "" });
    }
    for (const opt of options?.auto_save_interval || []) {
      items.push({ tab: "defaults", key: `auto_save_interval_${opt.id}`, label: `自动保存 · ${opt.label}`, desc: "" });
    }
    // Privacy tab
    items.push({ tab: "privacy", key: "history", label: "对话历史保留", desc: "" });
    items.push({ tab: "privacy", key: "export_data", label: "导出我的数据", desc: "" });
    items.push({ tab: "privacy", key: "reset", label: "重置所有设置", desc: "" });
    return items;
  }, [spectrumDims, options]);

  const searchResults = q
    ? allSearchItems.filter(
        (item) =>
          item.label.toLowerCase().includes(q) ||
          item.desc.toLowerCase().includes(q) ||
          item.key.toLowerCase().includes(q),
      )
    : [];

  // Filter spectrum dims by search when on AI tab
  const filteredSpectrumDims = q && activeTab === "ai"
    ? spectrumDims.filter((d) =>
        d.label.toLowerCase().includes(q) ||
        d.desc.toLowerCase().includes(q) ||
        d.id.toLowerCase().includes(q) ||
        d.left.toLowerCase().includes(q) ||
        d.right.toLowerCase().includes(q),
      )
    : spectrumDims;

  if (loading) {
    return <div className="page"><h2>设置</h2><p className="subtitle">加载中...</p></div>;
  }

  const renderTab = () => {
    switch (activeTab) {
      case "ai":
        return (
          <div>
            <h3>方法论光谱</h3>
            <p className="subtitle" style={{ fontSize: 13 }}>
              在以下 8 个维度上定位你的偏好。系统将根据你的光谱位置调整 AI 的行为方式。
              所有维度默认为中间值 3，只保存偏离中点的偏好。
            </p>
            <SpectrumSliders
              dims={filteredSpectrumDims}
              values={spectrum}
              onChange={updateSpectrum}
              showSave
              onSave={saveSpectrum}
              saving={saving}
              groups={q ? undefined : SPECTRUM_GROUPS}
            />

            <hr style={{ margin: "24px 0", borderColor: "var(--border)" }} />
            <h3>AI 输出参数</h3>

            <div className="form-group">
              <label>输出温度</label>
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 6px" }}>
                越低越保守严谨，越高越创意发散。当前：{settings.ai_temperature ?? 0.5}
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 11 }}>严谨 0.3</span>
                <input type="range" min={0.3} max={0.8} step={0.05}
                  value={typeof settings.ai_temperature === "number" ? settings.ai_temperature : 0.5}
                  onChange={(e) => updateSetting("ai_temperature", parseFloat(e.target.value))}
                  className="spectrum-slider-input" />
                <span style={{ fontSize: 11 }}>创意 0.8</span>
              </div>
            </div>

            <div className="form-group">
              <label>模型偏好</label>
              {(options?.ai_model_pref || []).map((opt) => (
                <label key={opt.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, cursor: "pointer" }}>
                  <input type="radio" name="ai_model_pref" value={opt.id}
                    checked={(settings.ai_model_pref || "auto") === opt.id}
                    onChange={() => updateSetting("ai_model_pref", opt.id)} />
                  <div>
                    <div style={{ fontWeight: 500 }}>{opt.label}</div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{opt.desc}</div>
                  </div>
                </label>
              ))}
            </div>

            <div className="form-group">
              <label>访谈提示频率</label>
              {(options?.ai_hint_frequency || []).map((opt) => (
                <label key={opt.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, cursor: "pointer" }}>
                  <input type="radio" name="ai_hint_frequency" value={opt.id}
                    checked={(settings.ai_hint_frequency || "standard") === opt.id}
                    onChange={() => updateSetting("ai_hint_frequency", opt.id)} />
                  <div>
                    <div style={{ fontWeight: 500 }}>{opt.label}</div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{opt.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>
        );

      case "ui":
        return (
          <div>
            <h3>界面偏好</h3>
            <div className="form-group">
              <label>字号</label>
              <div style={{ display: "flex", gap: 8 }}>
                {(options?.ui_font_size || []).map((opt) => (
                  <button key={opt.id} onClick={() => updateSetting("ui_font_size", opt.id)}
                    className={settings.ui_font_size === opt.id ? "btn-primary" : "btn-secondary"}
                    style={{ flex: 1 }}>{opt.label}</button>
                ))}
              </div>
            </div>
            <div className="form-group">
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={settings.ui_high_contrast === true}
                  onChange={(e) => updateSetting("ui_high_contrast", e.target.checked)} />
                高对比度模式
              </label>
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "4px 0 0 24px" }}>
                增强色彩对比度，辅助视觉障碍用户
              </p>
            </div>
          </div>
        );

      case "defaults":
        return (
          <div>
            <h3>新建项目默认值</h3>
            <p className="subtitle" style={{ fontSize: 13 }}>
              新建调查项目时自动使用以下默认选项。可在每个项目中单独修改。
            </p>
            <div className="form-group">
              <label>默认导出格式</label>
              <select value={typeof settings.default_export_format === "string" ? settings.default_export_format : "report"}
                onChange={(e) => updateSetting("default_export_format", e.target.value)}>
                {(options?.default_export_format || []).map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    [{opt.theme === "academic" ? "学术" : opt.theme === "government" ? "政务" : "青春"}] {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>自动保存间隔</label>
              <select value={typeof settings.auto_save_interval === "string" ? settings.auto_save_interval : "60s"}
                onChange={(e) => updateSetting("auto_save_interval", e.target.value)}>
                {(options?.auto_save_interval || []).map((opt) => (
                  <option key={opt.id} value={opt.id}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>
        );

      case "privacy":
        return (
          <div>
            <h3>数据与隐私</h3>
            <div className="form-group">
              <label>对话历史保留</label>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
                此设置将在正式版中启用。
              </p>
              <select disabled style={{ opacity: 0.5 }}><option>30天（默认）</option></select>
            </div>
            <div className="form-group">
              <button className="btn-secondary" disabled style={{ opacity: 0.5 }}>导出我的数据</button>
              <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 8 }}>
                下载所有项目、会话、分析结果的 JSON 包（v0.4 启用）
              </span>
            </div>
            <hr style={{ margin: "24px 0", borderColor: "var(--border)" }} />
            <div className="form-group">
              <button onClick={handleReset} className="btn-secondary"
                style={{ color: "#DC2626", borderColor: "#DC2626" }}>
                重置所有设置
              </button>
              <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 8 }}>
                将所有偏好和光谱恢复为默认值
              </span>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="page">
      <h2>设置</h2>
      <p className="subtitle">自定义你的 AI 行为、界面偏好和项目默认值</p>

      {/* ── Tab bar ── */}
      <div style={{ display: "flex", gap: 4, margin: "16px 0 8px", flexWrap: "wrap" }}>
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const tabMatchCount = q ? searchResults.filter((r) => r.tab === tab.id).length : 0;
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
              padding: "10px 16px",
              border: isActive ? "2px solid var(--primary)" : "1px solid var(--border)",
              borderRadius: "var(--radius)",
              background: isActive ? "var(--primary-light)" : "var(--surface)",
              cursor: "pointer", fontWeight: isActive ? 600 : 400,
              color: isActive ? "var(--primary)" : "var(--text)",
              transition: "all 0.12s", textAlign: "left", minWidth: 140,
              opacity: q && tabMatchCount === 0 ? 0.4 : 1,
            }}>
              <div style={{ fontSize: 16 }}>{tab.icon}</div>
              <div style={{ fontSize: 14, marginTop: 2 }}>
                {tab.label}
                {q && tabMatchCount > 0 && (
                  <span style={{ fontSize: 10, color: "var(--primary)", marginLeft: 4 }}>({tabMatchCount})</span>
                )}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{tab.desc}</div>
            </button>
          );
        })}
      </div>

      {/* ── Search bar ── */}
      <div style={{ marginBottom: 16 }}>
        <input
          type="text"
          placeholder="搜索设置项（如「温度」「光谱」「导出格式」）..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            width: "100%", maxWidth: 420, padding: "8px 14px",
            borderRadius: "var(--radius)", border: "1px solid var(--border)",
            fontSize: 13, background: "var(--surface)", color: "var(--text)",
          }}
        />
        {q && (
          <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 10 }}>
            找到 {searchResults.length} 项匹配
          </span>
        )}
      </div>

      {/* ── Cross-tab search quick-jump ── */}
      {q && searchResults.length > 0 && (
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 16,
          padding: "8px 12px", background: "var(--primary-light)", borderRadius: 8,
        }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: "24px" }}>跳转至：</span>
          {[...new Set(searchResults.map((r) => r.tab))].map((tabId) => {
            const tab = TABS.find((t) => t.id === tabId)!;
            const count = searchResults.filter((r) => r.tab === tabId).length;
            return (
              <button key={tabId} onClick={() => setActiveTab(tabId)} style={{
                padding: "3px 10px", fontSize: 12, borderRadius: 14,
                border: "1px solid var(--primary)", background: activeTab === tabId ? "var(--primary)" : "var(--surface)",
                color: activeTab === tabId ? "#fff" : "var(--primary)", cursor: "pointer",
              }}>
                {tab.icon} {tab.label} ({count})
              </button>
            );
          })}
        </div>
      )}

      {/* ── Message banner ── */}
      {message && (
        <div style={{
          padding: "8px 16px", borderRadius: 8, marginBottom: 16,
          background: message.type === "success" ? "#ECFDF5" : "#FEF2F2",
          color: message.type === "success" ? "#065F46" : "#991B1B",
          fontSize: 13, fontWeight: 500,
        }}>{message.text}</div>
      )}

      {/* ── Content area ── */}
      <div className="project-detail">
        {q && activeTab === "ai" && filteredSpectrumDims.length === 0 ? (
          <div style={{ textAlign: "center", padding: "32px 0", color: "var(--text-muted)" }}>
            <p>当前 tab 下没有匹配"<strong>{searchQuery}</strong>"的结果</p>
            <p style={{ fontSize: 13 }}>尝试切换上方 tab 或修改搜索词</p>
          </div>
        ) : (
          renderTab()
        )}
      </div>
    </div>
  );
}
