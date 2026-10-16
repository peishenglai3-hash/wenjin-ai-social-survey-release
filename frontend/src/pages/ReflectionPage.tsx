import { useSearchParams } from "react-router-dom";
import { useApp } from "../hooks/useApp";
import ReflectionPanel from "../components/ReflectionPanel";

/**
 * ReflectionPage — thin wrapper that mounts the existing ReflectionPanel component.
 *
 * ReflectionPanel was fully implemented but had no route or page that rendered it.
 * This page reads profileId from AppContext and optional projectId/sourceSessionId
 * from URL query params.
 */
export default function ReflectionPage() {
  const { profile, project } = useApp();
  const [searchParams] = useSearchParams();

  const profileId = profile?.id;
  const projectId = project?.id || (searchParams.get("projectId") ? Number(searchParams.get("projectId")) : undefined);
  const sourceSessionId = searchParams.get("sourceSessionId")
    ? Number(searchParams.get("sourceSessionId"))
    : undefined;

  if (!profileId) {
    return (
      <div className="page">
        <h2>反思画像</h2>
        <p className="subtitle">基于社会学反思性原理的结构化迭代反思工具</p>
        <div className="placeholder-panel" style={{ textAlign: "center", padding: 48 }}>
          <p>请先在「身份设置」中创建你的调查者档案，才能使用反思功能。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <h2>反思画像</h2>
      <p className="subtitle">
        基于社会学反思性原理（法国实用主义、常人方法学、布迪厄反思社会学），在调查完成后进行结构化反思，
        生成迭代洞察和光谱偏移建议。
      </p>
      <ReflectionPanel
        profileId={profileId}
        projectId={projectId}
        sourceSessionId={sourceSessionId}
        onComplete={(conclusion) => {
          console.log("[Reflection] Complete:", conclusion.summary);
        }}
      />
    </div>
  );
}
