
/** Interview mode presets from the white paper Table 3 */
export interface InterviewMode {
  id: string;
  icon: string;
  name: string;
  description: string;
  suitableFor: string;
  duration: string;
  structure: string;
  structureLevel: "low" | "medium" | "high" | "none";
  recordingStrategy: string;
}

export const INTERVIEW_MODES: InterviewMode[] = [
  {
    id: "deep_one_on_one",
    icon: "🎙️",
    name: "深度一对一",
    description: "精英访谈、敏感话题、生命史",
    suitableFor: "关键知情人、社区领袖、个人经历深挖",
    duration: "60-120分钟",
    structure: "低结构 · 开放式",
    structureLevel: "low",
    recordingStrategy: "全程双设备录音（主录音笔+手机备份）",
  },
  {
    id: "focus_group",
    icon: "👥",
    name: "焦点小组",
    description: "社区共识、需求调研、方案评估",
    suitableFor: "5-8人小组讨论、利益相关方座谈",
    duration: "90-150分钟",
    structure: "中结构 · 主题引导",
    structureLevel: "medium",
    recordingStrategy: "多麦克风阵列 + 现场笔记记录发言顺序",
  },
  {
    id: "street_intercept",
    icon: "🚶",
    name: "街头拦截",
    description: "公众意见、快速摸底、随机抽样",
    suitableFor: "公共场所快速问卷调查、民意探测",
    duration: "3-10分钟",
    structure: "高结构 · 固定问卷",
    structureLevel: "high",
    recordingStrategy: "手机录音 + 平板/手机同步录入问卷",
  },
  {
    id: "online_video",
    icon: "💻",
    name: "在线视频",
    description: "远程访谈、跨国调研、专家咨询",
    suitableFor: "异地受访者、国际比较研究、时间受限场景",
    duration: "30-60分钟",
    structure: "中结构 · 屏幕共享辅助",
    structureLevel: "medium",
    recordingStrategy: "会议软件录制（腾讯会议/Zoom）+ 本地备份录音",
  },
  {
    id: "field_casual",
    icon: "🌿",
    name: "田野漫谈",
    description: "参与观察、非正式聊天、日常互动",
    suitableFor: "长期田野驻点、社区融入、自然情境对话",
    duration: "不限时 · 片段累积",
    structure: "无结构 · 随遇而谈",
    structureLevel: "none",
    recordingStrategy: "事后田野笔记 + 关键语录回录（征得同意后）",
  },
];

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
