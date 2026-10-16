import { useState } from "react";
import { NavLink } from "react-router-dom";
import { useApp } from "../context/AppContext";
import config from "../config";

const phases = [
  {
    label: "首页",
    icon: "🏠",
    items: [{ path: "/", label: "工作台首页" }],
    defaultOpen: true,
  },
  {
    label: "调查前",
    icon: "📋",
    items: [
      { path: "/identity", label: "身份设置" },
      { path: "/topic", label: "选题设计" },
      { path: "/questionnaire", label: "问卷设计" },
      { path: "/methodology", label: "方法论规划" },
      { path: "/scenarios", label: "场景工坊" },
    ],
    defaultOpen: true,
  },
  {
    label: "调查中",
    icon: "🎙",
    items: [
      { path: "/fieldwork", label: "田野工具" },
      { path: "/copilot", label: "AI 助手" },
    ],
    defaultOpen: false,
  },
  {
    label: "调查后",
    icon: "📊",
    items: [
      { path: "/analysis", label: "数据分析" },
      { path: "/export", label: "成果导出" },
      { path: "/reflection", label: "反思画像" },
    ],
    defaultOpen: false,
  },
  {
    label: "成果库",
    icon: "📚",
    items: [
      { path: "/library", label: "调查档案" },
      { path: "/literature", label: "文献检索" },
      { path: "/memories", label: "AI 记忆" },
    ],
    defaultOpen: false,
  },
  {
    label: "社区",
    icon: "🌐",
    items: [
      { path: "/community", label: "调研者社区" },
    ],
    defaultOpen: true,
  },
  {
    label: "协作研究",
    icon: "🤝",
    items: [{ path: "/collaboration", label: "协作工作台" }],
    defaultOpen: true,
    feature: "collaborationV1",
  },
];

const themeOptions = [
  { id: "academic", label: "学术", icon: "📖" },
  { id: "government", label: "政务", icon: "🏛" },
  { id: "youth", label: "青春", icon: "🌱" },
];

export default function Sidebar() {
  const { theme, setTheme, user } = useApp();
  const [openPhases, setOpenPhases] = useState<Set<string>>(
    new Set(phases.filter((p) => p.defaultOpen).map((p) => p.label))
  );

  const toggle = (label: string) => {
    setOpenPhases((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  };

  return (
    <aside className="app-sidebar">
      <div className="sidebar-brand">AI 社会调查</div>
      <nav className="sidebar-nav">
        {phases.filter((phase) => !phase.feature || config.collaborationV1Enabled).map((phase, phaseIndex) => {
          const isOpen = openPhases.has(phase.label);
          const itemsId = `sidebar-phase-items-${phaseIndex}`;
          return (
            <div key={phase.label} className="phase-group">
              <button
                type="button"
                className="phase-header"
                onClick={() => toggle(phase.label)}
                aria-expanded={isOpen}
                aria-controls={itemsId}
              >
                <span className="phase-icon">{phase.icon}</span>
                <span className="phase-label">{phase.label}</span>
                <span className={`phase-arrow ${isOpen ? "open" : ""}`}>▾</span>
              </button>
              {isOpen && (
                <div id={itemsId} className="phase-items">
                  {phase.items.map((item) => (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      end={item.path === "/"}
                      className={({ isActive }) => `phase-item ${isActive ? "active" : ""}`}
                    >
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {user?.role === "admin" && (
          <NavLink
            to="/admin"
            className={({ isActive }) => `phase-item admin-nav-link ${isActive ? "active" : ""}`}
            style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "10px 16px", marginTop: 4,
              borderRadius: "var(--radius)", textDecoration: "none",
              fontWeight: 500, fontSize: 14,
            }}
          >
            ⚙️ 管理面板
          </NavLink>
        )}
      </nav>
      <div style={{ padding: "12px 16px", borderTop: "1px solid var(--border)", marginTop: "auto" }}>
        <NavLink to="/settings" style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "6px 8px", marginBottom: 12,
          borderRadius: "var(--radius)", textDecoration: "none",
          color: "var(--text-muted)", fontSize: 13,
          border: "1px solid var(--border)",
        }}>
          <span>⚙️</span> 设置
        </NavLink>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>界面风格</div>
        <div style={{ display: "flex", gap: 4 }}>
          {themeOptions.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => setTheme(opt.id)}
              title={opt.label}
              aria-label={`切换到${opt.label}风格`}
              aria-pressed={theme === opt.id}
              style={{
                flex: 1,
                padding: "6px 4px",
                border: theme === opt.id ? "2px solid var(--primary)" : "1px solid var(--border)",
                borderRadius: "var(--radius)",
                background: theme === opt.id ? "var(--primary-light)" : "var(--surface)",
                cursor: "pointer",
                fontSize: 11,
                color: theme === opt.id ? "var(--primary)" : "var(--text-muted)",
                fontWeight: theme === opt.id ? 600 : 400,
                transition: "all 0.12s",
              }}
            >
              {opt.icon} {opt.label}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
