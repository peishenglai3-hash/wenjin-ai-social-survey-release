/**
 * HintOverlay — Non-intrusive coaching prompt overlay.
 *
 * Two display modes:
 *  - "sidebar": Persistent panel with scrollable hint history
 *  - "toast": Floating toast notifications (auto-dismiss after 8s)
 */

import { useState, useEffect, useRef, useCallback } from "react";
import type { Hint } from "../types/hints";

interface HintOverlayProps {
  hints: Hint[];
  mode?: "sidebar" | "toast";
  onDismiss?: (id: string) => void;
  maxVisible?: number;
}
const CAT_ICONS: Record<string, string> = {
  follow_up: "🔍", rapport: "🤝", redirect: "↩️", probe: "🎯", wrap_up: "🏁", general: "💡",
};
const CAT_LABELS: Record<string, string> = {
  follow_up: "追问", rapport: "关系", redirect: "引导", probe: "深入", wrap_up: "收尾", general: "建议",
};
const URGENCY: Record<string, string> = { low: "#6B7280", medium: "#F59E0B", high: "#EF4444" };

export default function HintOverlay({
  hints, mode = "sidebar", onDismiss, maxVisible = 5,
}: HintOverlayProps) {
  const [toasts, setToasts] = useState<Hint[]>([]);
  const prevRef = useRef(0);

  useEffect(() => {
    if (mode !== "toast") return;
    if (hints.length > prevRef.current) {
      const fresh = hints.slice(prevRef.current);
      setToasts((p) => [...p, ...fresh].slice(-maxVisible));
      fresh.forEach((h) => setTimeout(() => {
        setToasts((p) => p.filter((t) => t.id !== h.id));
        onDismiss?.(h.id);
      }, 8000));
    }
    prevRef.current = hints.length;
  }, [hints, mode, maxVisible, onDismiss]);

  const dismiss = useCallback((id: string) => {
    setToasts((p) => p.filter((t) => t.id !== id));
    onDismiss?.(id);
  }, [onDismiss]);

  if (mode === "sidebar") {
    const visible = hints.slice(-maxVisible);
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}>
          💡 AI 实时提示 ({hints.length})
        </div>
        {visible.length === 0 && (
          <div style={{ padding: 16, textAlign: "center", fontSize: 12, color: "var(--text-muted)", background: "var(--surface)", borderRadius: 8, border: "1px dashed var(--border)" }}>
            访谈开始后，AI提示将在此显示...
          </div>
        )}
        {visible.map((h) => (
          <div key={h.id} style={{
            padding: "10px 12px", background: "var(--surface)", borderRadius: 8,
            border: "1px solid var(--border)",
            borderLeft: `3px solid ${URGENCY[h.urgency || "low"]}`,
            fontSize: 13, lineHeight: 1.5,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <span>{CAT_ICONS[h.category || "general"]}</span>
              <span style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 600 }}>
                {CAT_LABELS[h.category || "general"]}
              </span>
              {h.urgency === "high" && (
                <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 4, background: "#FEE2E2", color: "#DC2626", marginLeft: "auto" }}>紧急</span>
              )}
            </div>
            <div>{h.text}</div>
            <div style={{ fontSize: 9, color: "var(--text-muted)", marginTop: 4 }}>
              {new Date(h.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div style={{ position: "fixed", top: 80, right: 16, zIndex: 1000, display: "flex", flexDirection: "column", gap: 8, maxWidth: 320 }}>
      {toasts.map((h) => (
        <div key={h.id} onClick={() => dismiss(h.id)} style={{
          padding: "10px 14px", background: "var(--surface)", borderRadius: 10,
          border: "1px solid var(--border)", boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
          cursor: "pointer", fontSize: 13, lineHeight: 1.5,
          borderLeft: `3px solid ${URGENCY[h.urgency || "low"]}`,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <span>{CAT_ICONS[h.category || "general"]}</span>
            <span style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 600 }}>
              {CAT_LABELS[h.category || "general"]}
            </span>
            <span style={{ fontSize: 9, color: "var(--text-muted)", marginLeft: "auto" }}>
              {new Date(h.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>
          <div>{h.text}</div>
        </div>
      ))}
    </div>
  );
}
