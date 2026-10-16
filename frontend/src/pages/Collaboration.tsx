import { useEffect, useState, type FormEvent } from "react";
import config from "../config";
import {
  createResearchArtifact,
  listCollaborationMembers,
  listResearchArtifacts,
} from "../api/collaboration";
import type { CollaborationMember, ResearchArtifact } from "../api/collaboration";
import { useApp } from "../context/AppContext";

const artifactKinds = [
  ["research_plan", "研究计划"],
  ["questionnaire", "问卷"],
  ["fieldnote_summary", "田野摘要"],
  ["analysis_summary", "分析摘要"],
  ["report_draft", "报告草稿"],
  ["other", "其他"],
] as const;

export default function Collaboration() {
  const { project } = useApp();
  const [members, setMembers] = useState<CollaborationMember[]>([]);
  const [artifacts, setArtifacts] = useState<ResearchArtifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [artifactKey, setArtifactKey] = useState("");
  const [artifactTitle, setArtifactTitle] = useState("");
  const [artifactKind, setArtifactKind] = useState("other");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!config.collaborationV1Enabled || !project) return;
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([listCollaborationMembers(project.id), listResearchArtifacts(project.id)])
      .then(([memberData, artifactData]) => {
        if (!active) return;
        setMembers(memberData.members);
        setArtifacts(artifactData.artifacts);
      })
      .catch(() => {
        if (active) setError("协作数据加载失败，请确认项目权限和网络状态。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [project]);

  if (!config.collaborationV1Enabled) {
    return (
      <div className="page">
        <h2>协作研究模式</h2>
        <div className="onboarding-card">
          <h3>功能默认关闭</h3>
          <p>管理员可在前端构建环境设置 VITE_COLLABORATION_V1_ENABLED=true 后启用协作入口。</p>
          <p className="hint">V1 只提供显式保存、成员权限和脱敏研究产物版本，不启用实时共同编辑。</p>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="page">
        <h2>协作研究模式</h2>
        <div className="onboarding-card">
          <h3>请先选择或创建调查项目</h3>
          <p>协作成员和研究产物都绑定到具体项目，系统不会在没有项目上下文时发起请求。</p>
        </div>
      </div>
    );
  }

  const submitArtifact = async (event: FormEvent) => {
    event.preventDefault();
    const key = artifactKey.trim().toLowerCase();
    const title = artifactTitle.trim();
    if (!/^[a-z0-9][a-z0-9_-]{0,99}$/.test(key) || !title) {
      setError("产物键只能使用小写字母、数字、下划线或连字符，且标题不能为空。");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const result = await createResearchArtifact(project.id, {
        artifact_key: key,
        kind: artifactKind,
        title,
      });
      setArtifacts((current) => [result.artifact, ...current.filter((item) => item.id !== result.artifact.id)]);
      setArtifactKey("");
      setArtifactTitle("");
    } catch {
      setError("研究产物创建失败，请检查项目角色或使用不同的产物键。");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="page">
      <h2>协作研究模式</h2>
      <p className="subtitle">{project.title} · 显式保存、可审计、脱敏版本协作</p>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {loading ? <p className="hint">正在加载协作元数据...</p> : (
        <>
          <section className="onboarding-card" aria-labelledby="collaboration-members">
            <h3 id="collaboration-members">项目成员（{members.length}）</h3>
            <div className="badge-row">
              {members.map((member) => (
                <span className="badge" key={member.id}>Profile {member.profile_id} · {member.role}</span>
              ))}
            </div>
            <p className="hint">成员列表只显示权限元数据；邀请、角色调整和审计记录仍由后端受保护接口控制。</p>
          </section>

          <section className="onboarding-card" aria-labelledby="collaboration-artifacts" style={{ marginTop: 16 }}>
            <h3 id="collaboration-artifacts">研究产物</h3>
            <form onSubmit={submitArtifact} style={{ display: "grid", gap: 8, margin: "12px 0 20px" }}>
              <div className="input-row">
                <input value={artifactKey} onChange={(event) => setArtifactKey(event.target.value)} placeholder="产物键，如 research-plan" maxLength={100} />
                <input value={artifactTitle} onChange={(event) => setArtifactTitle(event.target.value)} placeholder="产物标题" maxLength={200} />
                <select value={artifactKind} onChange={(event) => setArtifactKind(event.target.value)} aria-label="产物类型">
                  {artifactKinds.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
                <button type="submit" disabled={creating}>{creating ? "创建中..." : "新建产物"}</button>
              </div>
            </form>
            {artifacts.length === 0 ? <p className="hint">暂无研究产物。创建后可在后端接口继续提交脱敏版本、批注和审核任务。</p> : (
              <div className="library-grid">
                {artifacts.map((artifact) => (
                  <div className="library-card" key={artifact.id}>
                    <h4>{artifact.title}</h4>
                    <p className="hint">{artifact.artifact_key} · {artifact.kind}</p>
                    <span className="badge">{artifact.status}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
          <p className="hint" style={{ marginTop: 16 }}>安全边界：V1 不做实时共同编辑，不上传原始访谈文本/音频，不把协作成员自动扩展到旧单人核心数据。</p>
        </>
      )}
    </div>
  );
}
