import { useState, useEffect, useCallback } from "react";
import api from "../api/client";
import { DIM_LABELS_MAP } from "../types/spectrum";

interface EvolutionEntry {
  id: number; dimension: string; direction: number; confidence: number;
  previous_value: number | null; new_value: number | null; rationale: string; applied_at: string | null;
}
interface EvolutionData {
  profile_id: number; current_spectrum: Record<string, number>;
  evolution_summary: { total_shifts: number; by_dimension: Record<string, { shift_count: number; net_change: number }> };
  history: EvolutionEntry[];
}

export default function EvolutionTimeline({ profileId, className = "" }: { profileId: number; theme?: string; className?: string }) {
  const [data, setData] = useState<EvolutionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selDim, setSelDim] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const { data: d } = await api.get(`/reflection/evolution/${profileId}${selDim ? `?dimension=${selDim}` : ""}`);
      setData(d);
    } catch { setError("加载失败"); }
    finally { setLoading(false); }
  }, [profileId, selDim]);

  useEffect(() => { void Promise.resolve().then(fetch); }, [fetch]);

  if (loading) return (
    <div className={`evolution-card ${className}`}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 20, height: 20,
          border: "2px solid var(--primary-light)", borderTopColor: "var(--primary)",
          borderRadius: "50%", animation: "pulse 1s infinite",
        }} />
        <span style={{ fontSize: 14, color: "var(--text-muted)" }}>加载中…</span>
      </div>
    </div>
  );

  if (error || !data) return (
    <div className={`evolution-card ${className}`}>
      <p style={{ fontSize: 14, color: "#dc2626" }}>{error || "无数据"}</p>
    </div>
  );

  const { current_spectrum, evolution_summary, history } = data;

  return (
    <div className={`evolution-card ${className}`}>
      <h2 className="evolution-title">画像进化轨迹</h2>

      {/* Current spectrum */}
      <div style={{ marginBottom: 20 }}>
        <h3 className="evolution-section-header">当前光谱</h3>
        {Object.entries(current_spectrum).map(([dim, val]) => (
          <div key={dim} className="evolution-spectrum-row">
            <span className="evolution-spectrum-label">
              {DIM_LABELS_MAP[dim]?.split("↔")[0] ?? dim}
            </span>
            <div className="evolution-spectrum-bar">
              <div className="evolution-spectrum-fill" style={{ width: `${(val / 5) * 100}%` }} />
            </div>
            <span className="evolution-spectrum-value">{val}</span>
          </div>
        ))}
      </div>

      {/* Evolution summary */}
      {evolution_summary.total_shifts > 0 ? (
        <>
          {/* Dimension filter chips */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
            <button
              onClick={() => setSelDim(null)}
              className={`evolution-dim-chip${!selDim ? " evolution-dim-chip--active" : ""}`}>
              全部
            </button>
            {Object.keys(evolution_summary.by_dimension).map(d => (
              <button
                key={d}
                onClick={() => setSelDim(d === selDim ? null : d)}
                className={`evolution-dim-chip${d === selDim ? " evolution-dim-chip--active" : ""}`}>
                {DIM_LABELS_MAP[d]?.split("↔")[0] ?? d}
              </button>
            ))}
          </div>

          {/* Stat grid */}
          <div className="evolution-stat-grid">
            {Object.entries(evolution_summary.by_dimension).map(([dim, info]) => (
              <div key={dim} className="evolution-stat-card">
                <span className="evolution-stat-label">
                  {DIM_LABELS_MAP[dim]?.split("↔")[0] ?? dim}
                </span>
                <span className="evolution-stat-value" style={{
                  color: info.net_change > 0 ? "#059669" : info.net_change < 0 ? "#d97706" : "var(--text)",
                }}>
                  {info.net_change > 0 ? "+" : ""}{info.net_change}
                </span>
                <span className="evolution-stat-count">{info.shift_count} 次</span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="evolution-empty-state">
          <p className="evolution-empty-title">尚未有画像迭代记录</p>
          <p className="evolution-empty-desc">完成田野调查并开展反思后，画像将逐渐演化</p>
        </div>
      )}

      {/* Timeline */}
      {history.length > 0 && (
        <div>
          <h3 className="evolution-section-header">最近迭代</h3>
          {history.slice(0, 10).map(e => (
            <div key={e.id} className="evolution-timeline-item">
              <div className={`evolution-timeline-dot ${e.direction > 0 ? "evolution-timeline-dot--up" : "evolution-timeline-dot--down"}`} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <span style={{ fontWeight: 500, color: "var(--text)" }}>
                  {DIM_LABELS_MAP[e.dimension]?.split("↔")[0] ?? e.dimension}
                </span>
                <span style={{
                  marginLeft: 6,
                  color: e.direction > 0 ? "#059669" : "#d97706",
                }}>
                  {e.previous_value} → {e.new_value}
                </span>
                <span style={{ marginLeft: 6, color: "var(--text-muted)" }}>
                  {e.applied_at ? new Date(e.applied_at).toLocaleDateString("zh-CN") : ""}
                </span>
                {e.rationale && (
                  <p style={{ color: "var(--text-muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {e.rationale}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
