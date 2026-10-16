import { type ReactNode } from "react";


export interface SpectrumDim {
  id: string;
  label: string;
  left: string;
  right: string;
  desc: string;
}

export interface SpectrumGroup {
  label: string;
  dimIds: string[];
}

interface SpectrumSlidersProps {
  dims: SpectrumDim[];
  values: Record<string, number>;
  onChange: (dimId: string, value: number) => void;
  disabled?: boolean;
  /** Show a save button below the sliders */
  showSave?: boolean;
  onSave?: () => Promise<void>;
  saving?: boolean;
  /** Optional grouping for progressive disclosure */
  groups?: SpectrumGroup[];
  /** Optional header content (title + description) rendered above the sliders */
  header?: ReactNode;
}

/**
 * SpectrumSliders — reusable spectrum dimension slider panel.
 *
 * Renders 1–5 Likert-scale range sliders for sociological methodology
 * dimensions. Supports flat list or grouped progressive-disclosure
 * (collapsible <details> sections). Used by Settings and Identity pages.
 */
export default function SpectrumSliders({
  dims,
  values,
  onChange,
  disabled = false,
  showSave = false,
  onSave,
  saving = false,
  groups,
  header,
}: SpectrumSlidersProps) {
  const dimMap = new Map(dims.map((d) => [d.id, d]));

  const renderSlider = (dimId: string) => {
    const dim = dimMap.get(dimId);
    if (!dim) return null;
    const value = values[dimId] ?? 3;

    return (
      <div key={dimId} className="spectrum-slider">
        <div className="spectrum-slider-header">
          <span className="spectrum-slider-label">{dim.label}</span>
          <span className="spectrum-slider-value">{value}/5</span>
        </div>
        <p className="spectrum-slider-desc">{dim.desc}</p>
        <div className="spectrum-slider-row">
          <span className="spectrum-slider-left">{dim.left}</span>
          <input
            type="range"
            min={1}
            max={5}
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(dimId, parseInt(e.target.value, 10))}
            className="spectrum-slider-input"
          />
          <span className="spectrum-slider-right">{dim.right}</span>
        </div>
      </div>
    );
  };

  const renderSaveButton = () => {
    if (!showSave || !onSave) return null;
    return (
      <div className="spectrum-slider-save-row">
        <button onClick={onSave} disabled={saving || disabled} className="btn-primary">
          {saving ? "保存中..." : "保存光谱"}
        </button>
        <span className="spectrum-slider-save-hint">
          光谱自动保存到你的档案，影响 AI 在所有页面的行为
        </span>
      </div>
    );
  };

  // ── Grouped mode (progressive disclosure) ──
  if (groups && groups.length > 0) {
    return (
      <div className="spectrum-sliders">
        {header}
        {groups.map((group, gi) => {
          const groupDims = group.dimIds.filter((id) => dimMap.has(id));
          if (groupDims.length === 0) return null;
          const nonDefault = groupDims.filter((id) => (values[id] ?? 3) !== 3).length;
          return (
            <details key={gi} className="spectrum-group" open={gi === 0}>
              <summary className="spectrum-group-summary">
                <span>{group.label}</span>
                <span className="spectrum-group-badge">
                  {nonDefault}/{groupDims.length} 已设置
                </span>
              </summary>
              <div className="spectrum-group-body">
                {groupDims.map(renderSlider)}
              </div>
            </details>
          );
        })}
        {renderSaveButton()}
      </div>
    );
  }

  // ── Flat mode (all sliders visible) ──
  return (
    <div className="spectrum-sliders">
      {header}
      {dims.map((dim) => renderSlider(dim.id))}
      {renderSaveButton()}
    </div>
  );
}
