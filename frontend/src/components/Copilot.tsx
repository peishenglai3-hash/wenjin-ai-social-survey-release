import { useState, useRef, useEffect } from "react";
import { useApp } from "../context/AppContext";
import config from "../config";
import { safeHtml } from "../utils/sanitize";
import { getAuthHeaders } from "../utils/authFetch";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export default function Copilot() {
  const { profile, project, theme } = useApp();
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const messagesEnd = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  useEffect(() => {
    if (open && !minimized) inputRef.current?.focus();
  }, [open, minimized]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setStreaming(true);
    setStreamingText("");

    try {
      const resp = await fetch(`${config.apiBaseUrl}/api/v1/copilot/chat/stream`, {
        method: "POST",
        headers: { ...getAuthHeaders() },
        body: JSON.stringify({
          message: text,
          profile_id: profile?.id,
          project_id: project?.id,
          theme,
          extra_context: `当前页面: ${window.location.pathname}`,
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
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `❌ 出错了: ${err.message || "请稍后重试"}` },
      ]);
    } finally {
      setStreaming(false);
      setStreamingText("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const toggle = () => {
    if (minimized) {
      setMinimized(false);
    } else if (open) {
      setMinimized(true);
    } else {
      setOpen(true);
    }
  };

  return (
    <>
      <button
        onClick={toggle}
        title="AI 助手 (Survey Copilot)"
        className="copilot-fab"
        aria-label="AI 助手"
      >
        {open && !minimized ? (
          <span style={{ fontSize: 18 }}>✕</span>
        ) : (
          <span style={{ fontSize: 20 }}>💬</span>
        )}
      </button>

      {open && !minimized && (
        <div className="copilot-panel">
          <div className="copilot-header">
            <div>
              <span style={{ marginRight: 6 }}>🤖</span>
              <strong>Survey Copilot</strong>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              <button
                onClick={() => setMinimized(true)}
                title="最小化"
                aria-label="最小化 AI 助手"
                className="copilot-header-btn"
              >
                ▾
              </button>
              <button
                onClick={() => { setOpen(false); setMessages([]); }}
                title="关闭"
                aria-label="关闭 AI 助手"
                className="copilot-header-btn"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="copilot-messages">
            {messages.length === 0 && !streaming && (
              <div className="copilot-welcome">
                <p>👋 你好！我是你的调查助手。</p>
                <p>我可以帮你：</p>
                <ul>
                  <li>解答调查方法论问题</li>
                  <li>推荐适合你场景的研究方法</li>
                  <li>分析访谈中遇到的困难</li>
                  <li>帮助理解社会学概念</li>
                </ul>
                {profile && (
                  <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
                    当前模式: {theme === "academic" ? "📖 学术" : theme === "government" ? "🏛 政务" : "🌱 青春"}
                    {project ? ` | 项目: ${project.title}` : ""}
                  </p>
                )}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`copilot-msg ${m.role}`}>
                <div className="copilot-msg-label">
                  {m.role === "user" ? "👤 你" : "🤖 助手"}
                </div>
                <div
                  className="copilot-msg-content"
                  dangerouslySetInnerHTML={safeHtml(m.content)}
                />
              </div>
            ))}
            {streaming && (
              <div className="copilot-msg assistant">
                <div className="copilot-msg-label">🤖 助手</div>
                <div
                  className="copilot-msg-content streaming"
                  dangerouslySetInnerHTML={safeHtml(streamingText)}
                />
                <span className="copilot-cursor">▊</span>
              </div>
            )}
            <div ref={messagesEnd} />
          </div>

          <div className="copilot-input-area">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              aria-label="输入问题"
              placeholder="输入你的问题..."
              disabled={streaming}
              className="copilot-input"
            />
            <button
              onClick={sendMessage}
              disabled={streaming || !input.trim()}
              className="copilot-send-btn"
            >
              {streaming ? "..." : "发送"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
