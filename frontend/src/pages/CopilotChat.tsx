import { useState, useRef, useEffect } from "react";
import { useApp } from "../hooks/useApp";
import config from "../config";
import { safeHtml } from "../utils/sanitize";
import { getAuthHeaders } from "../utils/authFetch";
import { getErrorMessage } from "../utils/errors";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

const SUGGESTED_QUESTIONS: Record<string, string[]> = {
  academic: [
    "如何确定我的研究问题是否有理论贡献？",
    "质性编码时遇到歧义怎么办？",
    "混合方法中如何整合量化和质性发现？",
    "如何撰写方法论部分的局限性说明？",
  ],
  government: [
    "如何将调研发现转化为政策建议？",
    "利益相关方分析应该从哪些维度入手？",
    "SWOT分析在实际调研中如何操作？",
    "如何保证政策调研的客观性？",
  ],
  youth: [
    "第一次做访谈，有什么开场白技巧？",
    "如何从访谈笔记中提炼关键发现？",
    "问卷调查和深度访谈各有什么优劣？",
    "怎样判断自己收集的数据是否足够？",
  ],
};

export default function CopilotChat() {
  const { profile, project, theme } = useApp();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [savingSkill, setSavingSkill] = useState(false);
  const [skillModal, setSkillModal] = useState<{ open: boolean; userMsg?: string; aiMsg?: string }>({ open: false });
  const [skillForm, setSkillForm] = useState({ name: "", description: "", category: "general" });
  const [projectBackground, setProjectBackground] = useState("");
  const [showBackground, setShowBackground] = useState(false);
  const messagesEnd = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const questions = SUGGESTED_QUESTIONS[theme] || SUGGESTED_QUESTIONS.academic;

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const sendMessage = async (text?: string) => {
    const msg = (text || input).trim();
    if (!msg || streaming) return;

    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setInput("");
    setStreaming(true);
    setStreamingText("");

    try {
      const resp = await fetch(`${config.apiBaseUrl}/api/v1/copilot/chat/stream`, {
        method: "POST",
        headers: { ...getAuthHeaders() },
        body: JSON.stringify({
          message: msg,
          profile_id: profile?.id,
          project_id: project?.id,
          theme,
          extra_context: `当前页面: 智能助手全屏对话${projectBackground.trim() ? `\n项目背景: ${projectBackground.trim()}` : ""}`,
        }),
      });

      const reader = resp.body?.getReader();
      if (!reader) throw new Error("No stream");

      const decoder = new TextDecoder();
      let full = "";
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (data === "[DONE]") continue;
            try {
              const parsed = JSON.parse(data);
              if (parsed.token) {
                full += parsed.token;
                setStreamingText(full);
              }
            } catch { /* partial chunk */ }
          }
        }
      }

      setMessages((prev) => [...prev, { role: "assistant", content: full }]);
    } catch (error: unknown) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `❌ 出错了: ${getErrorMessage(error, "请稍后重试")}` },
      ]);
    } finally {
      setStreaming(false);
      setStreamingText("");
    }
  };

  const openSkillModal = (aiMsg: string) => {
    // Find the user message just before this AI response
    const aiIndex = messages.findIndex((m) => m.role === "assistant" && m.content === aiMsg);
    const userMsg = aiIndex > 0 ? messages[aiIndex - 1]?.content : "";
    setSkillForm({ name: "", description: "", category: "general" });
    setSkillModal({ open: true, userMsg, aiMsg });
  };

  const saveAsSkill = async () => {
    if (!skillForm.name.trim() || savingSkill) return;
    setSavingSkill(true);
    try {
      const resp = await fetch(`${config.apiBaseUrl}/api/v1/skills/save`, {
        method: "POST",
        headers: { ...getAuthHeaders() },
        body: JSON.stringify({
          profile_id: profile?.id,
          name: skillForm.name,
          description: skillForm.description,
          prompt_template: "", // Auto-generate from dialogue
          category: skillForm.category,
          user_message: skillModal.userMsg,
          assistant_reply: skillModal.aiMsg,
        }),
      });
      const data = await resp.json();
      if (data.ok) {
        alert(`✅ 技能「${data.skill.name}」已保存！\n可在"我的技能"中随时调用。`);
        setSkillModal({ open: false });
      } else {
        alert(`❌ 保存失败: ${data.error}`);
      }
    } catch (error: unknown) {
      alert(`❌ 网络错误: ${getErrorMessage(error, "请稍后重试")}`);
    } finally {
      setSavingSkill(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearChat = () => {
    if (messages.length > 0 && !confirm("清除所有对话记录？")) return;
    setMessages([]);
    setStreamingText("");
  };

  const themeLabel = theme === "academic" ? "📖 学术模式" : theme === "government" ? "🏛 政务模式" : "🌱 青春模式";

  return (
    <div className="copilot-page">
      <div className="copilot-page-header">
        <div>
          <h2>🤖 AI 智能助手</h2>
          <p className="subtitle">
            {themeLabel}
            {project ? ` · 当前项目: ${project.title}` : " · 可随时提问社会调查相关问题"}
          </p>
        </div>
        <button onClick={clearChat} className="btn-ghost" title="清除对话">
          🗑 清空对话
        </button>
      </div>

      {/* ── Collapsible Project Background ── */}
      <div style={{
        marginBottom: 12, border: "1px solid var(--border)", borderRadius: 8,
        background: showBackground ? "var(--surface)" : "transparent",
      }}>
        <button
          onClick={() => setShowBackground(!showBackground)}
          style={{
            width: "100%", padding: "8px 12px", border: "none", background: "none",
            cursor: "pointer", fontSize: 13, fontWeight: 500, display: "flex",
            alignItems: "center", gap: 6, color: showBackground ? "var(--primary)" : "var(--text-muted)",
          }}
        >
          <span>{showBackground ? "▼" : "▶"}</span>
          📋 项目背景
          {projectBackground.trim() && !showBackground && (
            <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>
              （已填写 {projectBackground.length} 字）
            </span>
          )}
        </button>
        {showBackground && (
          <div style={{ padding: "0 12px 12px" }}>
            <textarea
              value={projectBackground}
              onChange={(e) => setProjectBackground(e.target.value)}
              placeholder={"描述研究项目的背景信息，AI将据此生成更贴合实际的访谈提纲和方法建议。\n\n例如：\n- 本项目依托XX街道社区治理创新试点，计划对基层干部和居民代表进行半结构化访谈。\n- 研究问题聚焦于数字化治理工具如何改变基层权力关系。\n- 访谈对象包括街道办分管领导、社区书记、网格员和居民代表，预计15-20人。"}
              rows={4}
              style={{ width: "100%", fontSize: 12, fontFamily: "inherit", resize: "vertical" }}
            />
            <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
              填写后，每次提问都会自动附加上下文。留空不影响正常使用。
            </p>
          </div>
        )}
      </div>

      <div className="copilot-page-body">
        {messages.length === 0 && !streaming ? (
          <div className="copilot-page-welcome">
            <div className="copilot-welcome-icon">💬</div>
            <h3>有什么我可以帮你的？</h3>
            <p>选择一个话题开始，或直接在下方输入你的问题</p>
            <div className="copilot-suggestions">
              {questions.map((q, i) => (
                <button
                  key={i}
                  className="copilot-suggestion-chip"
                  onClick={() => sendMessage(q)}
                  disabled={streaming}
                >
                  {q}
                </button>
              ))}
              <button
                className="copilot-suggestion-chip copilot-suggestion-more"
                onClick={() => {
                  setInput("");
                  inputRef.current?.focus();
                }}
              >
                ✍️ 自己输入问题...
              </button>
            </div>
          </div>
        ) : (
          <div className="copilot-chat-list">
            {messages.map((m, i) => (
              <div key={i} className={`copilot-msg ${m.role}`}>
                <div className="copilot-msg-avatar">
                  {m.role === "user" ? "👤" : "🤖"}
                </div>
                <div className="copilot-msg-body">
                  <div className="copilot-msg-label">
                    {m.role === "user" ? "你" : "AI 助手"}
                    {m.role === "assistant" && (
                      <button
                        className="copilot-save-skill-btn"
                        title="将此回复保存为可复用的技能模板"
                        onClick={() => openSkillModal(m.content)}
                      >
                        ⚡ 保存为技能
                      </button>
                    )}
                  </div>
                  <div
                    className="copilot-msg-content"
                    dangerouslySetInnerHTML={safeHtml(m.content)}
                  />
                </div>
              </div>
            ))}
            {streaming && (
              <div className="copilot-msg assistant">
                <div className="copilot-msg-avatar">🤖</div>
                <div className="copilot-msg-body">
                  <div className="copilot-msg-label">AI 助手</div>
                  <div
                    className="copilot-msg-content streaming"
                    dangerouslySetInnerHTML={safeHtml(streamingText)}
                  />
                  <span className="copilot-cursor">▊</span>
                </div>
              </div>
            )}
            <div ref={messagesEnd} />
          </div>
        )}
      </div>

      {/* ── Save Skill Modal ── */}
      {skillModal.open && (
        <div className="copilot-modal-overlay" onClick={() => setSkillModal({ open: false })}>
          <div className="copilot-modal" onClick={(e) => e.stopPropagation()}>
            <h3>⚡ 保存为我的技能</h3>
            <p className="copilot-modal-desc">
              将此对话转化为可复用的提示词模板。AI 会自动将具体的变量替换为 {'{变量}'} 占位符。
            </p>
            <label>技能名称 <span style={{ color: "red" }}>*</span></label>
            <input
              type="text"
              value={skillForm.name}
              onChange={(e) => setSkillForm({ ...skillForm, name: e.target.value })}
              placeholder="例如：访谈提纲生成器"
              className="copilot-modal-input"
              autoFocus
            />
            <label>简短描述（可选）</label>
            <input
              type="text"
              value={skillForm.description}
              onChange={(e) => setSkillForm({ ...skillForm, description: e.target.value })}
              placeholder="一句话说明这个技能的用途"
              className="copilot-modal-input"
            />
            <label>分类</label>
            <select
              value={skillForm.category}
              onChange={(e) => setSkillForm({ ...skillForm, category: e.target.value })}
              className="copilot-modal-input"
            >
              <option value="general">通用</option>
              <option value="questionnaire">问卷设计</option>
              <option value="interview">访谈</option>
              <option value="analysis">数据分析</option>
              <option value="writing">写作</option>
              <option value="methodology">方法论</option>
            </select>
            <div className="copilot-modal-actions">
              <button className="btn-ghost" onClick={() => setSkillModal({ open: false })}>
                取消
              </button>
              <button
                className="copilot-page-send-btn"
                onClick={saveAsSkill}
                disabled={savingSkill || !skillForm.name.trim()}
              >
                {savingSkill ? "⏳ 保存中..." : "💾 保存技能"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="copilot-page-input-area">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={streaming ? "AI 正在回复..." : "输入你的问题，按 Enter 发送..."}
          disabled={streaming}
          className="copilot-page-input"
        />
        <button
          onClick={() => sendMessage()}
          disabled={streaming || !input.trim()}
          className="copilot-page-send-btn"
        >
          {streaming ? "⏳" : "发送"}
        </button>
      </div>
    </div>
  );
}
