import { useState, useMemo, useRef } from "react";
import api from "../api/client";
import { streamAI } from "../api/stream";
import { useApp } from "../hooks/useApp";
import { validateFile } from "../utils/uploadValidation";
import QuickNav from "../components/QuickNav";

interface Format {
  id: string;
  label: string;
  desc: string;
  theme: string;
}

const allFormats: Format[] = [
  // Academic
  { id: "paper_outline", label: "论文大纲", desc: "学术论文标准章节框架", theme: "academic" },
  { id: "report", label: "调查报告", desc: "摘要-方法-发现-讨论-建议", theme: "academic" },
  { id: "proposal", label: "项目申报书", desc: "课题/项目申请书填写辅助", theme: "academic" },
  // Government — 公文写作
  { id: "official_document", label: "公文写作", desc: "按《党政机关公文处理工作条例》撰写规范公文", theme: "government" },
  { id: "policy_brief", label: "政策建议专报", desc: "精炼的政策建议，便于领导批示", theme: "government" },
  { id: "gov_report", label: "政务调研报告", desc: "基本情况-问题-对策的规范调研报告", theme: "government" },
  // Youth — 知识总结
  { id: "knowledge_summary", label: "知识总结", desc: "面向初学者的社会调查/田野调查核心知识梳理", theme: "youth" },
  { id: "learning_report", label: "学习探索报告", desc: "第一人称的学习探索与反思报告", theme: "youth" },
  { id: "reflection", label: "实践反思", desc: "社会实践心得体会撰写", theme: "youth" },
];

export default function Export() {
  const { theme: mode } = useApp();
  const [content, setContent] = useState("");
  const [formatId, setFormatId] = useState("report");
  const [notes, setNotes] = useState("");
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);

  // Reference file upload state
  const [refFile, setRefFile] = useState<File | null>(null);
  const [refText, setRefText] = useState("");
  const [refUploading, setRefUploading] = useState(false);
  const [refError, setRefError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Filter formats by current mode
  const formats = useMemo(() => {
    const modeFormats = allFormats.filter((f) => f.theme === mode);
    return modeFormats.length > 0 ? modeFormats : allFormats;
  }, [mode]);

  // Auto-select first format when mode changes
  const currentFormat = formats.find((f) => f.id === formatId)
    ? formatId
    : formats[0]?.id || "report";

  const handleGenerate = async () => {
    if (!content.trim() && !refText) return;
    setLoading(true);
    setOutput("");

    // Build combined content: user's text + uploaded reference file text
    let combinedContent = content;
    if (refText) {
      const refLabel = refFile ? `\n\n---\n参考文件: ${refFile.name}\n---\n` : "\n\n---\n参考材料:\n---\n";
      combinedContent = content
        ? content + refLabel + refText
        : refLabel + refText;
    }

    await streamAI(
      "/export/generate/stream",
      { format: currentFormat, content: combinedContent, notes, theme: mode },
      (token) => setOutput((prev) => prev + token),
      () => setLoading(false),
      (err) => { setOutput(err); setLoading(false); },
    );
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const result = validateFile(file, "reference");
    if (!result.ok) {
      setRefError(result.reason || "文件校验失败");
      const input = e.target as HTMLInputElement;
      input.value = "";
      return;
    }

    setRefFile(file);
    setRefError("");
    setRefUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post("/export/upload-reference", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      if (res.data.status === "ok") {
        setRefText(res.data.text);
      } else {
        setRefError(res.data.message || "提取失败");
        setRefText("");
      }
    } catch {
      setRefError("上传失败，请重试");
      setRefText("");
    } finally {
      setRefUploading(false);
    }
  };

  const handleRemoveRef = () => {
    setRefFile(null);
    setRefText("");
    setRefError("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDownloadFile = async (fileType: "docx" | "xlsx") => {
    if (!output) return;
    setDownloading(fileType);
    try {
      const res = await api.post("/export/generate-file", {
        format: currentFormat, content, notes, file_type: fileType, theme: mode,
      }, { responseType: "blob" });

      const blob = new Blob([res.data], {
        type: fileType === "docx"
          ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${allFormats.find((f) => f.id === currentFormat)?.label || "导出"}.${fileType}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert(`${fileType.toUpperCase()} 文件下载失败`);
    } finally {
      setDownloading(null);
    }
  };

  const handleDownloadMd = () => {
    const blob = new Blob([output], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${allFormats.find((f) => f.id === currentFormat)?.label || "导出"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(output);
      alert("已复制到剪贴板");
    } catch {
      // fallback
    }
  };

  return (
    <div className="page">
      <h2>成果导出</h2>
      <p className="subtitle">
        {mode === "government" ? "按政务公文规范生成调研报告、政策建议专报等，支持 Markdown / Word / Excel 下载" :
         mode === "youth" ? "知识总结、学习报告、实践反思——将调查经历转化为可分享的学习成果，支持 Markdown / Word 下载" :
         "将调查材料系统化整合为学术成果，支持 Markdown / Word / Excel 下载"}
      </p>

      <div className="split-page">
        {/* ── Left: Inputs ── */}
        <div className="split-left">
          <div className="form-group">
            <label>选择导出格式</label>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {formats.map((f) => (
                <button
                  key={f.id}
                  onClick={() => setFormatId(f.id)}
                  className={`card-btn ${currentFormat === f.id ? "selected" : ""}`}
                  style={{ textAlign: "left" }}
                >
                  <strong>{f.label}</strong>
                  <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block" }}>{f.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>研究内容</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={
                mode === "government" ? "粘贴调研记录、座谈会纪要、问题分析等..." :
                mode === "youth" ? "粘贴你的观察笔记、学习心得、田野日记等..." :
                "粘贴选题论证、分析结果、访谈摘要等..."
              }
              rows={8}
              style={{ width: "100%", padding: 12, borderRadius: 8, border: "1px solid var(--border)", resize: "vertical" }}
            />
          </div>

          <div className="form-group">
            <label>补充说明（可选）</label>
            <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="特殊格式要求、字数限制等..." />
          </div>

          {/* ── Reference file upload ── */}
          <div className="form-group">
            <label>上传参考文件（可选）</label>
            <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 8px" }}>
              支持 .txt / .md / .docx / .pdf，最大 10MB。文件文本将作为 AI 生成的参考材料。
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.docx,.pdf"
              onChange={handleFileSelect}
              style={{ display: "none" }}
            />
            {!refFile ? (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => fileInputRef.current?.click()}
                disabled={refUploading}
                style={{ width: "100%" }}
              >
                {refUploading ? "提取文本中..." : "选择文件"}
              </button>
            ) : (
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "8px 12px", background: "var(--surface)", borderRadius: 8,
                border: refError ? "1px solid #DC2626" : "1px solid var(--border)",
              }}>
                <span style={{ flex: 1, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {refError ? `❌ ${refError}` : `📎 ${refFile.name} (${refText.length} 字)`}
                </span>
                <button type="button" onClick={handleRemoveRef}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 16 }}>
                  ✕
                </button>
              </div>
            )}
          </div>

          <button onClick={handleGenerate} disabled={loading || (!content.trim() && !refText)} className="btn-primary">
            {loading ? "AI生成中..." : "生成文档"}
          </button>

          {loading && !output && (
            <div style={{ padding: 12, background: "var(--surface)", borderRadius: 8, textAlign: "center", fontSize: 13 }}>
              <span className="dot connecting" style={{ display: "inline-block", marginRight: 8 }} />
              正在连接 AI 服务...
            </div>
          )}
        </div>

        {/* ── Right: Output ── */}
        {output ? (
          <div className="split-right">
            <div className="md-content" style={{ whiteSpace: "pre-wrap", marginBottom: 16 }}>
              {output}
              {loading && <span className="dot connecting" style={{ display: "inline-block", marginLeft: 4, verticalAlign: "middle" }} />}
            </div>
            <div className="button-row" style={{ flexWrap: "wrap" }}>
              <button onClick={handleCopy} className="btn-secondary">复制到剪贴板</button>
              <button onClick={handleDownloadMd} className="btn-secondary">下载 .md</button>
              <button
                onClick={() => handleDownloadFile("docx")}
                disabled={downloading !== null}
                className="btn-secondary"
                style={{ background: "var(--primary)", color: "#fff", border: "none" }}
              >
                {downloading === "docx" ? "下载中..." : "下载 Word"}
              </button>
              <button
                onClick={() => handleDownloadFile("xlsx")}
                disabled={downloading !== null}
                className="btn-secondary"
                style={{ background: "#065F46", color: "#fff", border: "none" }}
              >
                {downloading === "xlsx" ? "下载中..." : "下载 Excel"}
              </button>
            </div>
          </div>
        ) : (
          <div className="split-right-empty">
            {loading
              ? "AI 正在生成文档..."
              : "AI 生成的文档将在此处实时展示\n\n支持论文大纲、调查报告、项目申报书、实践反思四种格式\n生成后可下载为 .md / .docx / .xlsx"}
          </div>
        )}
      </div>

      <QuickNav
        currentPath="/export"
        visible={!!output}
        nextPath="/library"
        nextLabel="调查档案"
      />
    </div>
  );
}
