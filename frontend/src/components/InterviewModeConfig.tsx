
import { INTERVIEW_MODES, type InterviewMode } from "../types/interview";

interface Props {
  selected: string | null;
  onSelect: (mode: InterviewMode) => void;
}

export default function InterviewModeConfig({ selected, onSelect }: Props) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h4 style={{ margin: "0 0 4px", fontSize: 15, color: "var(--text)" }}>
        📋 访谈模式
      </h4>
      <p style={{ margin: "0 0 12px", fontSize: 12, color: "var(--text-muted)" }}>
        选择访谈模式以获取针对性的录音策略和操作建议
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
          gap: 10,
        }}
      >
        {INTERVIEW_MODES.map((mode) => {
          const isActive = selected === mode.id;
          return (
            <div
              key={mode.id}
              onClick={() => onSelect(mode)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(mode);
                }
              }}
              role="button"
              tabIndex={0}
              aria-label={`选择访谈模式：${mode.name}`}
              aria-pressed={isActive}
              style={{
                padding: "14px 16px",
                border: isActive
                  ? "2px solid var(--primary)"
                  : "1px solid var(--border)",
                borderRadius: 10,
                cursor: "pointer",
                background: isActive ? "#EEF2FF" : "var(--surface)",
                transition: "all 0.15s",
              }}
            >
              <div style={{ fontSize: 22, marginBottom: 4 }}>{mode.icon}</div>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>
                {mode.name}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.4 }}>
                {mode.description}
              </div>
              <div
                style={{
                  marginTop: 8,
                  paddingTop: 8,
                  borderTop: "1px solid var(--border)",
                  fontSize: 11,
                  color: "var(--text-muted)",
                  lineHeight: 1.5,
                }}
              >
                <div>⏱ {mode.duration}</div>
                <div>📐 {mode.structure}</div>
                <div style={{ marginTop: 2, color: "var(--primary)", fontSize: 10 }}>
                  🎤 {mode.recordingStrategy}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {selected && (
        <SelectedModeDetail mode={INTERVIEW_MODES.find((m) => m.id === selected)!} />
      )}
    </div>
  );
}

function SelectedModeDetail({ mode }: { mode: InterviewMode }) {
  return (
    <div
      style={{
        marginTop: 12,
        padding: "14px 18px",
        background: "#EEF2FF",
        border: "1px solid #C7D2FE",
        borderRadius: 10,
        fontSize: 13,
        lineHeight: 1.7,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 4 }}>
        ✅ 已选择「{mode.name}」模式
      </div>
      <div>
        <strong>适用场景：</strong>
        {mode.suitableFor}
      </div>
      <div>
        <strong>建议录音策略：</strong>
        {mode.recordingStrategy}
      </div>
      <div style={{ marginTop: 6, fontSize: 11, color: "#4B5563" }}>
        💡 提示：录音开始后，AI将根据此模式调整提示频率和内容侧重。
        {mode.structureLevel === "low" || mode.structureLevel === "none"
          ? "低结构访谈中AI提示将更注重追问时机和沉默包容。"
          : mode.structureLevel === "high"
          ? "高结构访谈中AI提示将更注重问卷完整性和跳题逻辑。"
          : "中结构访谈中AI提示将兼顾引导和灵活追问。"}
      </div>
    </div>
  );
}
