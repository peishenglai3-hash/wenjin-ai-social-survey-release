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
