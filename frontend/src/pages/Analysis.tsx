import { useState } from "react";
import ReactEChartsCore from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import type { EChartsCoreOption } from "echarts/core";
import { BarChart, PieChart, ScatterChart, LineChart } from "echarts/charts";
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import api from "../api/client";
import { streamAI } from "../api/stream";
import { useApp } from "../hooks/useApp";
import CodebookPanel from "../components/CodebookPanel";
import QuickNav from "../components/QuickNav";

echarts.use([BarChart, PieChart, ScatterChart, LineChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer]);

const analysisTypes = [
  { id: "interview", label: "访谈分析", desc: "主题编码 · 叙事分析 · 扎根理论" },
  { id: "survey", label: "问卷分析", desc: "描述统计 · 推断检验 · 效应量" },
  { id: "mixed", label: "混合分析", desc: "量化+质性整合 · 联合展示" },
];

interface ChartSeries {
  [key: string]: unknown;
  name?: string;
  data?: unknown[];
}

interface ChartData {
  legend?: string[];
  categories?: string[];
  series?: ChartSeries[];
}

interface ChartConfig {
  title?: string;
  type: "bar" | "pie" | "scatter" | "line";
  data: unknown;
}

function isChartConfig(value: unknown): value is ChartConfig {
  if (typeof value !== "object" || value === null || !("type" in value)) return false;
  const type = value.type;
  return type === "bar" || type === "pie" || type === "scatter" || type === "line";
}

function getChartData(value: unknown): ChartData {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return {};
  const data = value as Record<string, unknown>;
  return {
    legend: Array.isArray(data.legend) ? data.legend.filter((item): item is string => typeof item === "string") : [],
    categories: Array.isArray(data.categories) ? data.categories.filter((item): item is string => typeof item === "string") : [],
    series: Array.isArray(data.series) ? data.series.filter((item): item is ChartSeries => typeof item === "object" && item !== null) : [],
  };
}

function parseChartJson(text: string): ChartConfig[] {
  const charts: ChartConfig[] = [];
  const jsonMatch = text.match(/```chartjson\n([\s\S]*?)\n```/g);
  if (jsonMatch) {
    for (const block of jsonMatch) {
      try {
        const json = JSON.parse(block.replace(/```chartjson\n?/g, "").replace(/```/g, ""));
        if (Array.isArray(json)) charts.push(...json.filter(isChartConfig));
        else if (isChartConfig(json)) charts.push(json);
      } catch {
        // skip broken chart json
      }
    }
  }
  return charts;
}

function chartToOption(c: ChartConfig): EChartsCoreOption {
  const data = getChartData(c.data);
  if (c.type === "pie") {
    return {
      title: { text: c.title, left: "center" },
      tooltip: { trigger: "item" },
      legend: { orient: "vertical", left: "left" },
      series: [{ type: "pie", radius: "50%", data: Array.isArray(c.data) ? c.data : [], emphasis: { itemStyle: { shadowBlur: 10 } } }],
    };
  }
  if (c.type === "scatter") {
    return {
      title: { text: c.title, left: "center" },
      tooltip: { trigger: "item" },
      xAxis: {},
      yAxis: {},
      series: [{ type: "scatter", data: Array.isArray(c.data) ? c.data : [] }],
    };
  }
  return {
    title: { text: c.title, left: "center" },
    tooltip: { trigger: "axis" },
    legend: { data: data.legend },
    xAxis: { type: "category", data: data.categories },
    yAxis: { type: "value" },
    series: (data.series || []).map((series) => ({ ...series, type: c.type })),
  };
}

export default function Analysis() {
  const { project } = useApp();
  const [content, setContent] = useState("");
  const [analysisType, setAnalysisType] = useState("interview");
  const [paradigm, setParadigm] = useState(project?.paradigm || "qualitative");
  const [result, setResult] = useState("");
  const [charts, setCharts] = useState<ChartConfig[]>([]);
  const [showCharts, setShowCharts] = useState(false);
  const [loading, setLoading] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<"analysis" | "codebook">("analysis");

  const handleRun = async () => {
    if (!content.trim() && !csvFile) return;
    setLoading(true);
    setResult("");
    setCharts([]);

    let payloadContent = content;
    if (csvFile) {
      const text = await csvFile.text();
      payloadContent = content + "\n\n[CSV数据]\n" + text;
    }

    let fullText = "";
    await streamAI(
      "/analysis/run/stream",
      {
        type: analysisType,
        content: payloadContent,
        paradigm,
        include_charts: !!csvFile,
      },
      (token) => {
        fullText += token;
        setResult(fullText);
      },
      () => {
        setLoading(false);
        const parsed = parseChartJson(fullText);
        if (parsed.length > 0) {
          setCharts(parsed);
          setShowCharts(true);
        }
      },
      (err) => { setResult(err); setLoading(false); },
    );
  };

  const handleDownload = async (fileType: "docx" | "md") => {
    if (!result) return;
    setDownloading(fileType);
    try {
      const title = "数据分析报告";
      const res = await api.post("/export/download-content", {
        content: result.replace(/```chartjson\n[\s\S]*?\n```/g, "").trim(),
        file_type: fileType,
        title,
      }, { responseType: "blob" });
      const blob = new Blob([res.data], {
        type: fileType === "docx"
          ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          : "text/markdown",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${title}.${fileType}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert(`${fileType.toUpperCase()} 下载失败`);
    } finally {
      setDownloading(null);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setCsvFile(file);
      if (!content) {
        setContent(`[已上传文件: ${file.name}]`);
      }
    }
  };

  return (
    <div className="page">
      <h2>数据分析</h2>
      <p className="subtitle">AI辅助质性/量化数据分析，支持图表可视化</p>

      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        <button
          onClick={() => setActiveTool("analysis")}
          className={`card-btn ${activeTool === "analysis" ? "selected" : ""}`}
          style={{ padding: "6px 16px", fontSize: 13 }}
        >
          📊 AI分析
        </button>
        <button
          onClick={() => setActiveTool("codebook")}
          className={`card-btn ${activeTool === "codebook" ? "selected" : ""}`}
          style={{ padding: "6px 16px", fontSize: 13 }}
        >
          📋 编码簿
        </button>
      </div>

      {activeTool === "codebook" ? (
        <CodebookPanel />
      ) : (
      <div className="split-page">
        {/* ── Left: Inputs ── */}
        <div className="split-left">
          <div className="form-group">
            <label>数据类型</label>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {analysisTypes.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setAnalysisType(t.id)}
                  className={`card-btn ${analysisType === t.id ? "selected" : ""}`}
                  style={{ textAlign: "left" }}
                >
                  <strong>{t.label}</strong>
                  <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block" }}>{t.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>研究范式</label>
            <select value={paradigm} onChange={(e) => setParadigm(e.target.value)}>
              <option value="qualitative">质性研究</option>
              <option value="quantitative">量化研究</option>
              <option value="mixed">混合方法</option>
            </select>
          </div>

          <div className="form-group">
            <label>分析内容</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="粘贴访谈文本、问卷数据摘要..."
              rows={8}
              style={{ width: "100%", padding: 12, borderRadius: 8, border: "1px solid var(--border)", resize: "vertical" }}
            />
          </div>

          <div className="form-group">
            <label>上传数据文件（CSV / Excel / JSON / TXT，可选）</label>
            <input
              type="file"
              accept=".csv,.txt,.xlsx,.xls,.json,.tsv"
              onChange={handleFileChange}
              style={{ padding: 8, fontSize: 13 }}
            />
            {csvFile && <span style={{ marginLeft: 8, fontSize: 12, color: "var(--text-muted)" }}>{csvFile.name} ({(csvFile.size / 1024).toFixed(1)} KB)</span>}
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
              支持 CSV、Excel (.xlsx)、JSON、TSV 格式。如数据包含图表，可用下方"图表截图"上传。
            </p>
          </div>

          <div className="form-group">
            <label>📊 图表截图（可选 — 上传含图表的截图，千问VL视觉分析）</label>
            <input
              type="file"
              accept="image/*"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = async () => {
                  const base64 = (reader.result as string).split(",")[1] || "";
                  setLoading(true);
                  setResult("");
                  try {
                    const res = await api.post("/image/analyze", {
                      image_base64: base64,
                      image_description: "这是一张数据图表截图，请提取其中的数据信息并进行数据分析。",
                      research_topic: project?.research_direction || "数据分析",
                      analysis_focus: "auto",
                    });
                    const chartAnalysis = res.data.analysis || "";
                    setContent((prev) => prev + "\n\n[图表AI解读]\n" + chartAnalysis);
                    setResult(chartAnalysis);
                  } catch {
                    setResult("图表分析失败，请尝试手动描述图表内容。");
                  } finally {
                    setLoading(false);
                  }
                };
                reader.readAsDataURL(file);
              }}
              style={{ padding: 8, fontSize: 13 }}
            />
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
              上传含图表的截图（统计图/趋势图等），AI提取关键数据并入分析。DeepSeek不支持识图，此功能使用千问VL视觉模型。
            </p>
          </div>

          <button onClick={handleRun} disabled={loading || (!content.trim() && !csvFile)} className="btn-primary">
            {loading ? "AI分析中..." : "开始分析"}
          </button>

          {loading && !result && (
            <div style={{ padding: 12, background: "var(--surface)", borderRadius: 8, textAlign: "center", fontSize: 13 }}>
              <span className="dot connecting" style={{ display: "inline-block", marginRight: 8 }} />
              正在连接 AI 分析服务...
            </div>
          )}
        </div>

        {/* ── Right: Output ── */}
        {result ? (
          <div className="split-right">
            {charts.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <button onClick={() => setShowCharts(!showCharts)} className="btn-secondary" style={{ marginBottom: 12 }}>
                  {showCharts ? "隐藏图表" : `显示 ${charts.length} 张可视化图表`}
                </button>
                {showCharts && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    {charts.map((c, i) => (
                      <div key={i} style={{ background: "var(--surface)", borderRadius: 12, padding: 12, border: "1px solid var(--border)" }}>
                        <ReactEChartsCore echarts={echarts} option={chartToOption(c)} style={{ height: 260 }} notMerge />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div className="md-content" style={{ whiteSpace: "pre-wrap", marginBottom: 16 }}>
              {result.replace(/```chartjson\n[\s\S]*?\n```/g, "").trim()}
              {loading && <span className="dot connecting" style={{ display: "inline-block", marginLeft: 4, verticalAlign: "middle" }} />}
            </div>
            <div className="button-row" style={{ flexWrap: "wrap" }}>
              <button
                onClick={() => handleDownload("docx")}
                disabled={downloading !== null}
                className="btn-secondary"
                style={{ background: "var(--primary)", color: "#fff", border: "none" }}
              >
                {downloading === "docx" ? "下载中..." : "下载 Word (.docx)"}
              </button>
              <button
                onClick={() => handleDownload("md")}
                disabled={downloading !== null}
                className="btn-secondary"
              >
                {downloading === "md" ? "下载中..." : "下载 Markdown (.md)"}
              </button>
            </div>
          </div>
        ) : (
          <div className="split-right-empty">
            {loading
              ? "AI 正在分析数据..."
              : "AI 分析结果将在此处实时展示\n\n支持主题编码、叙事分析、统计建议、可视化图表等"}
          </div>
        )}
      </div>
      )}

      <QuickNav
        currentPath="/analysis"
        visible={!!result}
        nextPath="/export"
        nextLabel="成果导出"
      />
    </div>
  );
}
