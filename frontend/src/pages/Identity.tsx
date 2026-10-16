import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";
import { useApp } from "../hooks/useApp";
import SpectrumSliders, { type SpectrumDim } from "../components/SpectrumSliders";
import "./Identity.css";

interface Option {
  id: string;
  label: string;
}

interface ExtractedProfile {
  parse_error?: boolean;
  extraction_confidence?: number;
  profile_summary?: string;
  role?: string;
  experience_level?: string;
  paradigm_preference?: string;
  scenario_preference?: string;
  mbti?: string;
  gender?: string;
  age_range?: string;
  mode?: string;
  theme_preference?: string;
  theory_driven?: number;
  methodological_rigidity?: number;
  analysis_depth?: number;
  structure_preference?: number;
  participation_level?: number;
  tech_dependency?: number;
  writing_style?: number;
  learning_preference?: number;
}

type ProfileMode = "quick" | "deep";

export default function Identity() {
  const { profile, setProfile } = useApp();
  const navigate = useNavigate();

  // ── Shared state ──
  const [activeMode, setActiveMode] = useState<ProfileMode>("quick");
  const [saving, setSaving] = useState(false);
  const [loadingGuidance, setLoadingGuidance] = useState(false);
  const [saved, setSaved] = useState(false);

  const [form, setForm] = useState({
    mode: profile?.mode || "personal",
    gender: profile?.gender || "",
    role: profile?.role || "undergraduate",
    experience_level: profile?.experience_level || "beginner",
    age_range: profile?.age_range || "",
    mbti: profile?.mbti || "",
    paradigm_preference: profile?.paradigm_preference || "qualitative",
    scenario_preference: profile?.scenario_preference || "community_interview",
    theme_preference: profile?.theme_preference || "academic",
  });

  const [spectrumDims, setSpectrumDims] = useState<SpectrumDim[]>([]);
  const [spectrum, setSpectrum] = useState<Record<string, number>>({});
  const [defaults, setDefaults] = useState<Record<string, Option[]>>({});

  // ── Quick Profile (Keyword Mode) state ──
  const [keywords, setKeywords] = useState<string[]>([]);
  const [keywordInput, setKeywordInput] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [extracted, setExtracted] = useState<ExtractedProfile | null>(null);
  const [extractError, setExtractError] = useState("");

  // ── Keyword input handlers ──
  const addKeyword = (raw: string) => {
    const kw = raw.replace(/[,，、\s]+/g, "").trim();
    if (!kw) return;
    if (kw.length > 15) {
      setExtractError("每个关键词不超过15个字");
      return;
    }
    if (keywords.length >= 5) {
      setExtractError("最多输入5个关键词");
      return;
    }
    if (keywords.includes(kw)) {
      setExtractError("关键词不能重复");
      return;
    }
    setKeywords((prev) => [...prev, kw]);
    setKeywordInput("");
    setExtractError("");
  };

  const removeKeyword = (index: number) => {
    setKeywords((prev) => prev.filter((_, i) => i !== index));
    setExtractError("");
  };

  const handleKeywordKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === "," || e.key === "、" || e.key === " ") {
      e.preventDefault();
      addKeyword(keywordInput);
    } else if (e.key === "Backspace" && !keywordInput && keywords.length > 0) {
      removeKeyword(keywords.length - 1);
    }
  };

  // ── Load defaults + spectrum metadata ──
  useEffect(() => {
    api.get("/profile/defaults").then((r) => setDefaults(r.data)).catch(() => {});
    api.get("/settings/defaults").then((r) => {
      setSpectrumDims(r.data.spectrum_dimensions || []);
      const spec: Record<string, number> = {};
      for (const d of r.data.spectrum_dimensions || []) {
        spec[d.id] = Number(profile?.[d.id as keyof typeof profile]) || 3;
      }
      setSpectrum(spec);
    }).catch(() => {});
  }, [profile]);

  // ── If user already has a profile, pre-fill and switch to deep mode ──
  useEffect(() => {
    if (profile?.id && profile.role) {
      setActiveMode("deep");
      setSaved(true);
    }
  }, [profile]);

  const update = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  // ── Quick Profile: AI Extraction from Keywords ──
  const handleExtract = async () => {
    if (keywords.length < 3) {
      setExtractError("请至少输入3个关键词，例如：博士生、田野调查、质性研究");
      return;
    }
    setExtracting(true);
    setExtractError("");
    setExtracted(null);
    try {
      const res = await api.post("/profile/quick-keywords", { keywords });
      if (res.data.error) {
        setExtractError(res.data.error);
      } else {
        setExtracted(res.data);
        // Pre-fill the form with extracted values (so Deep mode sees them too)
        setForm({
          mode: res.data.mode || "personal",
          gender: res.data.gender || "",
          role: res.data.role || "undergraduate",
          experience_level: res.data.experience_level || "beginner",
          age_range: res.data.age_range || "",
          mbti: res.data.mbti || "",
          paradigm_preference: res.data.paradigm_preference || "qualitative",
          scenario_preference: res.data.scenario_preference || "community_interview",
          theme_preference: res.data.theme_preference || "academic",
        });
        setSpectrum({
          theory_driven: res.data.theory_driven ?? 3,
          methodological_rigidity: res.data.methodological_rigidity ?? 3,
          analysis_depth: res.data.analysis_depth ?? 3,
          structure_preference: res.data.structure_preference ?? 3,
          participation_level: res.data.participation_level ?? 3,
          tech_dependency: res.data.tech_dependency ?? 3,
          writing_style: res.data.writing_style ?? 3,
          learning_preference: res.data.learning_preference ?? 3,
        });
      }
    } catch {
      setExtractError("AI提取失败，请检查网络后重试，或切换到详细画像手动填写");
    } finally {
      setExtracting(false);
    }
  };

  // ── Save profile ──
  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = profile?.id
        ? { ...form, ...spectrum, id: profile.id }
        : { ...form, ...spectrum };
      const res = await api.post("/profile", payload);
      setProfile(res.data);
      setSaved(true);
    } catch {
      alert("保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  // ── Get methodology guidance ──
  const handleGuidance = async () => {
    setLoadingGuidance(true);
    try {
      const payload = profile?.id ? { ...form, ...spectrum, id: profile.id } : { ...form, ...spectrum };
      const res = await api.post("/profile", payload);
      setProfile(res.data);
      navigate("/methodology", { state: { autoGenerate: true } });
    } catch {
      alert("保存失败，请重试");
    } finally {
      setLoadingGuidance(false);
    }
  };

  // ── Select helper for Deep mode ──
  const select = (label: string, key: string, options: Option[]) => (
    <div className="form-group" key={key}>
      <label>{label}</label>
      <select value={form[key as keyof typeof form] || ""} onChange={(e) => update(key, e.target.value)}>
        <option value="">请选择</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>{o.label}</option>
        ))}
      </select>
    </div>
  );

  // ── Human-readable labels ──
  const roleLabels: Record<string, string> = {
    undergraduate: "本科生", graduate: "硕士研究生", phd_candidate: "博士研究生",
    researcher: "研究人员", faculty: "教师", practitioner: "实务工作者", other: "其他",
  };
  const expLabels: Record<string, string> = {
    beginner: "新手", intermediate: "有一定经验", advanced: "经验丰富",
  };
  const paradigmLabels: Record<string, string> = {
    qualitative: "质性研究", quantitative: "量化研究", mixed: "混合方法",
  };
  const scenarioLabels: Record<string, string> = {
    community_interview: "社区访谈", rural_fieldwork: "乡村田野",
    questionnaire_survey: "问卷调研", online_survey: "在线调查", other: "其他场景",
  };

  return (
    <div className="page identity-page">
      <h2>身份设置 · 配置你的调查画像</h2>
      <p className="subtitle">系统将根据你的个人信息提供差异化的方法论指导</p>

      {/* ── Tab Switcher ── */}
      <div className="identity-tabs">
        <button
          className={`identity-tab ${activeMode === "quick" ? "active" : ""}`}
          onClick={() => setActiveMode("quick")}
        >
          <span className="tab-icon">🚀</span>
          <span className="tab-label">一键画像</span>
          <span className="tab-desc">AI智能提取·约2分钟</span>
        </button>
        <button
          className={`identity-tab ${activeMode === "deep" ? "active" : ""}`}
          onClick={() => setActiveMode("deep")}
        >
          <span className="tab-icon">📋</span>
          <span className="tab-label">详细画像</span>
          <span className="tab-desc">全面配置·5-10分钟</span>
        </button>
      </div>

      {/* ── Content Area ── */}
      <div className="identity-content">
        {/* ======== QUICK PROFILE MODE ======== */}
        {activeMode === "quick" && (
          <div className="quick-profile-section">
            <div className="quick-intro">
              <h3>输入3-5个关键词，AI自动构建画像</h3>
              <p>
                用关键词描述你的身份、方法和风格。例如：
                <span className="kw-example">博士生</span>
                <span className="kw-example">田野调查</span>
                <span className="kw-example">质性研究</span>
                <span className="kw-example">社区</span>
                —— 按回车或逗号添加，3-5个即可。
              </p>
            </div>

            <div className="quick-input-area">
              <div className={`keyword-tag-input ${extracting ? "disabled" : ""}`}>
                {keywords.map((kw, i) => (
                  <span key={i} className="keyword-tag">
                    {kw}
                    <button
                      type="button"
                      className="tag-remove"
                      onClick={() => removeKeyword(i)}
                      disabled={extracting}
                      aria-label={`移除关键词 ${kw}`}
                    >
                      ×
                    </button>
                  </span>
                ))}
                {keywords.length < 5 && (
                  <input
                    className="keyword-input-field"
                    value={keywordInput}
                    onChange={(e) => {
                      setKeywordInput(e.target.value);
                      setExtractError("");
                    }}
                    onKeyDown={handleKeywordKeyDown}
                    onBlur={() => {
                      if (keywordInput.trim()) addKeyword(keywordInput);
                    }}
                    placeholder={keywords.length === 0 ? "输入关键词，按回车添加..." : keywords.length < 3 ? `还需 ${3 - keywords.length} 个关键词...` : "继续添加或点击提取..."}
                    disabled={extracting}
                    maxLength={15}
                  />
                )}
              </div>
              <div className="quick-input-footer">
                <span className={`kw-count ${keywords.length >= 3 ? "ready" : ""}`}>
                  {keywords.length}/5 关键词{keywords.length < 3 ? `（至少3个）` : " ✅"}
                </span>
                <button
                  className="btn-primary btn-extract"
                  onClick={handleExtract}
                  disabled={extracting || keywords.length < 3}
                >
                  {extracting ? (
                    <>
                      <span className="spinner" /> AI分析中...
                    </>
                  ) : (
                    "✨ AI提取画像"
                  )}
                </button>
              </div>
              {extractError && <div className="quick-error">{extractError}</div>}
            </div>

            {/* ── Extracted Results ── */}
            {extracted && !extracted.parse_error && (
              <div className="quick-results">
                <div className="results-header">
                  <h3>✅ AI提取结果</h3>
                  <span className="confidence-badge">
                    置信度：{Math.round((extracted.extraction_confidence || 0) * 100)}%
                  </span>
                </div>

                {extracted.profile_summary && (
                  <div className="profile-summary-card">
                    <span className="summary-icon">💡</span>
                    <p>{extracted.profile_summary}</p>
                  </div>
                )}

                <div className="extracted-chips">
                  <div className="chip-row">
                    <span className="chip-label">身份角色</span>
                    <span className="chip value">{extracted.role ? roleLabels[extracted.role] || extracted.role : ""}</span>
                  </div>
                  <div className="chip-row">
                    <span className="chip-label">调查经验</span>
                    <span className="chip value">{extracted.experience_level ? expLabels[extracted.experience_level] || extracted.experience_level : ""}</span>
                  </div>
                  <div className="chip-row">
                    <span className="chip-label">研究范式</span>
                    <span className="chip value">{extracted.paradigm_preference ? paradigmLabels[extracted.paradigm_preference] || extracted.paradigm_preference : ""}</span>
                  </div>
                  <div className="chip-row">
                    <span className="chip-label">常用场景</span>
                    <span className="chip value">{extracted.scenario_preference ? scenarioLabels[extracted.scenario_preference] || extracted.scenario_preference : ""}</span>
                  </div>
                  {extracted.mbti && (
                    <div className="chip-row">
                      <span className="chip-label">MBTI</span>
                      <span className="chip value mbti">{extracted.mbti}</span>
                    </div>
                  )}
                  {extracted.gender && extracted.gender !== "prefer_not" && (
                    <div className="chip-row">
                      <span className="chip-label">性别</span>
                      <span className="chip value">{extracted.gender === "male" ? "男" : extracted.gender === "female" ? "女" : extracted.gender}</span>
                    </div>
                  )}
                  {extracted.age_range && extracted.age_range !== "prefer_not" && (
                    <div className="chip-row">
                      <span className="chip-label">年龄段</span>
                      <span className="chip value">{extracted.age_range.replace("_", "-")}岁</span>
                    </div>
                  )}
                </div>

                {/* Mini spectrum preview */}
                {spectrumDims.length > 0 && (
                  <div className="quick-spectrum-preview">
                    <h4>🎚 方法论光谱（AI推断）</h4>
                    <div className="spectrum-mini-grid">
                      {spectrumDims.map((dim) => {
                        const val = spectrum[dim.id] ?? 3;
                        return (
                          <div key={dim.id} className="spectrum-mini-item">
                            <span className="spec-label">{dim.label}</span>
                            <div className="spec-bar-track">
                              <div
                                className={`spec-bar-fill spec-bar-${val}`}
                                style={{ width: `${(val / 5) * 100}%` }}
                              />
                            </div>
                            <span className="spec-val">{val}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                <div className="quick-actions">
                  <button
                    className="btn-primary"
                    onClick={handleSave}
                    disabled={saving}
                  >
                    {saving ? "保存中..." : "💾 确认并保存画像"}
                  </button>
                  <button
                    className="btn-secondary"
                    onClick={() => setActiveMode("deep")}
                  >
                    切换到详细画像微调 →
                  </button>
                </div>
              </div>
            )}

            {/* Parse error fallback */}
            {extracted?.parse_error && (
              <div className="quick-results">
                <div className="results-header">
                  <h3>⚠️ AI提取未完全成功</h3>
                </div>
                <p style={{ color: "var(--text-muted)", marginBottom: 16 }}>
                  AI未能完整解析你的描述。建议切换到"详细画像"手动填写，或修改描述后重试。
                </p>
                <button className="btn-primary" onClick={() => setActiveMode("deep")}>
                  切换到详细画像 →
                </button>
              </div>
            )}
          </div>
        )}

        {/* ======== DEEP PROFILE MODE ======== */}
        {activeMode === "deep" && (
          <div className="profile-form">
            <div className="form-row">
              {select("工作模式", "mode", defaults.modes || [])}
              {select("性别", "gender", defaults.genders || [])}
            </div>
            <div className="form-row">
              {select("身份/角色", "role", defaults.roles || [])}
              {select("调查经验", "experience_level", defaults.experience_levels || [])}
            </div>
            <div className="form-row">
              {select("年龄范围", "age_range", defaults.age_ranges || [])}
              <div className="form-group">
                <label>MBTI（可选）</label>
                <input
                  value={form.mbti}
                  onChange={(e) => update("mbti", e.target.value.toUpperCase().slice(0, 4))}
                  placeholder="例如: INFJ"
                  maxLength={4}
                />
              </div>
            </div>
            <div className="form-row">
              {select("研究范式偏好", "paradigm_preference", defaults.paradigms || [])}
              {select("常用调查场景", "scenario_preference", defaults.scenarios || [])}
            </div>
            <div className="form-row">
              {select("界面风格", "theme_preference", defaults.themes || [])}
            </div>

            {/* Spectrum Sliders */}
            {spectrumDims.length > 0 && (
              <div className="spectrum-section">
                <SpectrumSliders
                  dims={spectrumDims}
                  values={spectrum}
                  onChange={(dimId, value) => setSpectrum((s) => ({ ...s, [dimId]: value }))}
                  header={
                    <>
                      <h3>🎚 方法论光谱</h3>
                      <p>
                        在以下维度上滑动定位你的偏好。默认为中间值 3。系统将根据光谱调整 AI 行为。
                      </p>
                    </>
                  }
                />
              </div>
            )}

            <div className="button-row">
              <button onClick={handleSave} disabled={saving} className="btn-primary">
                {saving ? "保存中..." : profile?.id ? "更新档案" : "保存档案"}
              </button>
              <button onClick={handleGuidance} disabled={loadingGuidance} className="btn-secondary">
                {loadingGuidance ? "生成中..." : "获取方法论指导"}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Saved confirmation */}
      {saved && (
        <div className="saved-banner">
          ✅ 档案已保存 — 可以前往「选题设计」开始你的调查项目
        </div>
      )}
    </div>
  );
}
