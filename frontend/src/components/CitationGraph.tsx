/**
 * CitationGraph — ECharts force-directed citation graph visualization.
 *
 * Props:
 *  - nodes: { id, name, year, citations, symbolSize }[]
 *  - edges: { source, target }[]
 *  - onNodeClick: callback when a paper node is clicked
 */
import { useEffect, useRef } from "react";
import * as echarts from "echarts";

interface GraphNode {
  id: string;
  name: string;
  year: number | null;
  citations: number;
  symbolSize: number;
}

interface GraphEdge {
  source: string;
  target: string;
}

interface CitationGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  seedDoi: string;
  onNodeClick?: (doi: string) => void;
  height?: number;
}

interface ChartEventParams {
  dataType?: string;
  data?: unknown;
}

function isChartEventParams(value: unknown): value is ChartEventParams {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isGraphNode(value: unknown): value is GraphNode {
  return typeof value === "object" && value !== null && "id" in value && "name" in value;
}

function isGraphEdge(value: unknown): value is GraphEdge {
  return typeof value === "object" && value !== null && "source" in value && "target" in value;
}

export default function CitationGraph({
  nodes,
  edges,
  seedDoi,
  onNodeClick,
  height = 500,
}: CitationGraphProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current || nodes.length === 0) return;

    if (!instanceRef.current) {
      instanceRef.current = echarts.init(chartRef.current);
    }

    const chart = instanceRef.current;

    const option: echarts.EChartsOption = {
      tooltip: {
        formatter: (params: unknown) => {
          if (!isChartEventParams(params)) return "";
          if (params.dataType === "node") {
            if (!isGraphNode(params.data)) return "";
            return `<b>${params.data.name}</b><br/>Year: ${params.data.year || "N/A"} · Citations: ${params.data.citations}<br/><small>${params.data.id}</small>`;
          }
          if (!isGraphEdge(params.data)) return "";
          return `${params.data.source} → ${params.data.target}`;
        },
      },
      legend: {
        data: ["种子论文", "关联论文"],
        top: 10,
        textStyle: { fontSize: 11 },
      },
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          force: {
            repulsion: 300,
            edgeLength: [100, 250],
            gravity: 0.1,
            friction: 0.6,
          },
          data: nodes.map((n) => ({
            ...n,
            category: n.id === seedDoi ? 0 : 1,
          })),
          edges: edges.map((e) => ({
            source: e.source,
            target: e.target,
            lineStyle: { color: "#cbd5e1", width: 1, curveness: 0.2, opacity: 0.6 },
          })),
          categories: [
            { name: "种子论文", itemStyle: { color: "#4f46e5" } },
            { name: "关联论文", itemStyle: { color: "#0ea5e9" } },
          ],
          lineStyle: { color: "source", curveness: 0.2 },
          emphasis: {
            focus: "adjacency",
            lineStyle: { width: 2 },
          },
          itemStyle: {
            borderColor: "#fff",
            borderWidth: 1,
            shadowBlur: 10,
            shadowColor: "rgba(0,0,0,0.1)",
          },
          label: {
            show: false,
            position: "right",
            fontSize: 10,
          },
        },
      ],
    };

    chart.setOption(option, true);

    if (onNodeClick) {
      chart.off("click");
      chart.on("click", (params: unknown) => {
        if (!isChartEventParams(params)) return;
        if (params.dataType === "node" && isGraphNode(params.data) && params.data.id) {
          onNodeClick(params.data.id);
        }
      });
    }

    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [nodes, edges, seedDoi, onNodeClick]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      instanceRef.current?.dispose();
      instanceRef.current = null;
    };
  }, []);

  if (nodes.length === 0) {
    return (
      <div style={{
        height, display: "flex", alignItems: "center", justifyContent: "center",
        background: "var(--surface)", borderRadius: 12, border: "1px solid var(--border)",
        color: "var(--text-muted)", fontSize: 14,
      }}>
        暂无引用图数据 — 请输入种子论文 DOI 生成
      </div>
    );
  }

  return (
    <div
      ref={chartRef}
      style={{ height, width: "100%", background: "var(--surface)", borderRadius: 12, border: "1px solid var(--border)" }}
    />
  );
}
