/**
 * LiteratureSearch — Academic literature discovery page.
 *
 * Backend: GET/POST /api/v1/literature/search
 *          POST    /api/v1/literature/gap-analysis
 *          GET     /api/v1/literature/citations
 *          POST    /api/v1/literature/semantic-search  (Tier 2)
 *          GET     /api/v1/literature/citation-graph   (Tier 2)
 */
import { useState, useCallback, useEffect } from "react";
import config from "../config";
import { getAccessToken } from "../api/client";
import Skeleton from "../components/Skeleton";
import ErrorState from "../components/ErrorState";
import CitationGraph from "../components/CitationGraph";
import { trackPageView, trackSearch } from "../utils/analytics";

/* ── Types ─────────────────────────────────────────── */
interface PaperResult {
  title: string;
  authors: string[];
  year: number | null;
  doi: string | null;
  abstract: string;
  source: string;
  citation_count: number;
  journal: string;
  methodology_tags: string[];
  language: string;
  url: string;
}

interface GapResult {
  topic: string;
  papers_found: number;
  methodology_gaps: string[];
  region_gaps: string[];
  population_gaps: string[];
  temporal_gaps: string[];
  recommendations: string[];
}

interface SearchResponse {
  query: string;
  count: number;
  papers: PaperResult[];
}

/* ── Constants ─────────────────────────────────────── */
const SOURCE_LABELS: Record<string, string> = {
  openalex: "OpenAlex",
  semantic_scholar: "Semantic Scholar",
  idata: "iData/知网",
};

const METHOD_LABELS: Record<string, string> = {
  qualitative_interview: "深度访谈",
  ethnography: "民族志",
  case_study: "案例研究",
  survey_quantitative: "问卷调查",
  grounded_theory: "扎根理论",
  mixed_methods: "混合方法",
  content_analysis: "内容分析",
  experimental: "实验研究",
};

const LANG_OPTIONS = [
  { value: "all", label: "全部语言" },
  { value: "zh", label: "中文" },
  { value: "en", label: "英文" },
];

/* ── Component ─────────────────────────────────────── */
export default function LiteratureSearch() {
  // Analytics
  useEffect(() => {
    trackPageView("LiteratureSearch");
  }, []);

  // Search state
  const [query, setQuery] = useState("");
  const [papers, setPapers] = useState<PaperResult[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [searchedQuery, setSearchedQuery] = useState("");

  // Filters
  const [langPref, setLangPref] = useState("all");
  const [methodFilter, setMethodFilter] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");

  // UI state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gapResult, setGapResult] = useState<GapResult | null>(null);
  const [gapLoading, setGapLoading] = useState(false);
  const [expandedAbstract, setExpandedAbstract] = useState<number | null>(null);
  // ── Query expansion & streaming ──
  const [expandedQueries, setExpandedQueries] = useState<string[]>([]);
  const [expandingQuery, setExpandingQuery] = useState(false);
  const [useExpand, setUseExpand] = useState(false);
  const [useStream, setUseStream] = useState(true);
  const [useSemantic, setUseSemantic] = useState(false);

  // ── Citation Graph state ──
  const [graphDoi, setGraphDoi] = useState("");
  const [graphNodes, setGraphNodes] = useState<any[]>([]);
  const [graphEdges, setGraphEdges] = useState<any[]>([]);
  const [graphSeedDoi, setGraphSeedDoi] = useState("");
  const [graphLoading, setGraphLoading] = useState(false);
  const [showGraph, setShowGraph] = useState(false);

  /* ── Helper: get auth header ────────────────────── */
  const authHeaders = useCallback((): Record<string, string> => {
    const at = getAccessToken();
    return at && at !== "guest" ? { Authorization: `Bearer ${at}` } : {};
  }, []);

  /* ── Search ──────────────────────────────────────── */
  const doSearch = useCallback(
    async (e?: React.FormEvent) => {
      if (e) e.preventDefault();
      const trimmed = query.trim();
      if (!trimmed) return;

      setLoading(true);
      setError(null);
      setGapResult(null);
      setExpandedAbstract(null);

      try {
        const params = new URLSearchParams({
          query: trimmed,
          language_pref: langPref,
          top_n: "20",
        });
        if (methodFilter) params.set("methodology_filter", methodFilter);
        if (yearFrom) params.set("year_from", yearFrom);
        if (yearTo) params.set("year_to", yearTo);

        const resp = await fetch(
          `${config.apiBaseUrl}/api/v1/literature/search?${params}`,
          { headers: authHeaders() }
        );
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data: SearchResponse = await resp.json();
        setPapers(data.papers);
        setTotalCount(data.count);
        setSearchedQuery(data.query);
        trackSearch(trimmed, { langPref, methodFilter, yearFrom, yearTo }, data.count);
      } catch (err: any) {
        setError(err.message || "文献检索失败，请检查网络连接后重试");
        setPapers([]);
        setTotalCount(0);
      } finally {
        setLoading(false);
      }
    },
    [query, langPref, methodFilter, yearFrom, yearTo]
  );

  /* ── Gap Analysis ────────────────────────────────── */
  const doGapAnalysis = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed) return;

    setGapLoading(true);
    try {
      const resp = await fetch(
        `${config.apiBaseUrl}/api/v1/literature/gap-analysis`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ topic: trimmed }),
        }
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: GapResult = await resp.json();
      setGapResult(data);
    } catch {
      setGapResult({
        topic: trimmed,
        papers_found: 0,
        methodology_gaps: [],
        region_gaps: [],
        population_gaps: [],
        temporal_gaps: [],
        recommendations: ["分析请求失败，请稍后重试"],
      });
    } finally {
      setGapLoading(false);
    }
  }, [query]);

  /* ── Query Expansion ────────────────────────────────── */
  const doExpandQuery = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed) return;
    setExpandingQuery(true);
    try {
      const resp = await fetch(`${config.apiBaseUrl}/api/v1/literature/expand-query`, {
        method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ query: trimmed, n_variants: 4 }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setExpandedQueries(data.expanded_queries || []);
    } catch { setExpandedQueries([]); }
    finally { setExpandingQuery(false); }
  }, [query]);

  /* ── SSE Streaming Search ───────────────────────────── */
  const doStreamSearch = useCallback(async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setLoading(true); setError(null); setGapResult(null);
    setExpandedAbstract(null); setPapers([]); setTotalCount(0);

    try {
      const params = new URLSearchParams({ query: trimmed, language_pref: langPref, top_n: "30" });
      if (methodFilter) params.set("methodology_filter", methodFilter);
      if (yearFrom) params.set("year_from", yearFrom);
      if (yearTo) params.set("year_to", yearTo);
      if (useExpand) params.set("expand", "true");

      const url = `${config.apiBaseUrl}/api/v1/literature/search/stream?${params}`;
      const response = await fetch(url, { headers: authHeaders() });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (!response.body) throw new Error("SSE not supported");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const collected: PaperResult[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n"); buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === "paper") { collected.push(event.paper); setPapers([...collected]); setTotalCount(collected.length); setSearchedQuery(trimmed); }
              else if (event.type === "done") setTotalCount(event.total);
            } catch {}
          }
        }
      }
      trackSearch(trimmed, { langPref, methodFilter, yearFrom, yearTo }, collected.length);
    } catch (err: any) { setError(err.message || "流式检索失败"); }
    finally { setLoading(false); }
  }, [query, langPref, methodFilter, yearFrom, yearTo, useExpand]);

  /* ── Semantic Search ─────────────────────────────────── */
  const doSemanticSearch = useCallback(async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setLoading(true); setError(null); setGapResult(null);
    setExpandedAbstract(null); setPapers([]); setTotalCount(0);

    try {
      const resp = await fetch(`${config.apiBaseUrl}/api/v1/literature/semantic-search`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          query: trimmed,
          top_n: 20,
          language_filter: langPref !== "all" ? langPref : null,
          semantic_weight: 0.6,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setPapers(data.papers || []);
      setTotalCount(data.count || 0);
      setSearchedQuery(trimmed);
      trackSearch(trimmed, { langPref, method: "semantic" }, data.count);
    } catch (err: any) {
      setError(err.message || "语义检索失败");
      setPapers([]);
      setTotalCount(0);
    } finally { setLoading(false); }
  }, [query, langPref]);

  /* ── Citation Graph ─────────────────────────────────── */
  const doCitationGraph = useCallback(async (doi?: string) => {
    const targetDoi = doi || graphDoi.trim();
    if (!targetDoi) return;
    setGraphLoading(true); setShowGraph(true);
    setGraphNodes([]); setGraphEdges([]); setGraphSeedDoi(targetDoi);
    try {
      const params = new URLSearchParams({ seed_doi: targetDoi, depth: "2", max_nodes: "50" });
      const resp = await fetch(`${config.apiBaseUrl}/api/v1/literature/citation-graph?${params}`,
        { headers: authHeaders() });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setGraphNodes(data.nodes || []);
      setGraphEdges(data.edges || []);
    } catch (err: any) {
      setError(err.message || "引用图加载失败");
    } finally { setGraphLoading(false); }
  }, [graphDoi]);

  /* ── Search dispatch ────────────────────────────────── */
  const handleSearch = useCallback((e?: React.FormEvent) => {
    setShowGraph(false);
    if (useSemantic) {
      doSemanticSearch(e);
    } else if (useStream) {
      doStreamSearch(e);
    } else {
      doSearch(e);
    }
  }, [useSemantic, useStream, doStreamSearch, doSearch]);

  return (
    <div className="page page-literature">
      {/* ═══ Header ═══ */}
      <div className="lit-header">
        <h1>📚 文献检索</h1>
        <p className="lit-subtitle">
          跨库检索 OpenAlex（2.5亿+）、Semantic Scholar、知网 —
          自动标注研究方法论，识别学术空白
        </p>
      </div>

      {/* ═══ Search Bar ═══ */}
      <form className="lit-search-bar" onSubmit={handleSearch}>
        <div className="lit-search-row">
          <input
            type="text"
            className="lit-search-input"
            placeholder="输入研究主题、关键词或研究问题…（如：基层治理中的公民参与）"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <button
            type="submit"
            className="btn-primary lit-search-btn"
            disabled={loading || !query.trim()}
          >
            {loading ? "搜索中…" : "🔍 检索"}
          </button>
        </div>

        {/* Filters */}
        <div className="lit-filters">
          <select
            className="lit-filter-select"
            value={langPref}
            onChange={(e) => setLangPref(e.target.value)}
          >
            {LANG_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>

          <select
            className="lit-filter-select"
            value={methodFilter}
            onChange={(e) => setMethodFilter(e.target.value)}
          >
            <option value="">全部方法</option>
            {Object.entries(METHOD_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>

          <input
            type="number"
            className="lit-filter-year"
            placeholder="起始年"
            value={yearFrom}
            onChange={(e) => setYearFrom(e.target.value)}
            min={1900}
            max={2030}
          />
          <span className="lit-filter-sep">—</span>
          <input
            type="number"
            className="lit-filter-year"
            placeholder="截止年"
            value={yearTo}
            onChange={(e) => setYearTo(e.target.value)}
            min={1900}
            max={2030}
          />

          <button
            type="button"
            className="btn-secondary lit-gap-btn"
            onClick={doGapAnalysis}
            disabled={gapLoading || !query.trim()}
          >
            {gapLoading ? "分析中…" : "🔬 研究空白分析"}
          </button>

          {/* Search mode toggles */}
          <button
            type="button"
            className="btn-secondary lit-gap-btn"
            onClick={doExpandQuery}
            disabled={expandingQuery || !query.trim()}
            title="AI将用户查询扩展为多个学术检索词"
          >
            {expandingQuery ? "扩展中…" : "🧠 查询扩展"}
          </button>

          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--text-muted)", cursor: "pointer", whiteSpace: "nowrap" }}>
            <input type="checkbox" checked={useExpand} onChange={(e) => setUseExpand(e.target.checked)} />
            AI扩展
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--text-muted)", cursor: "pointer", whiteSpace: "nowrap" }}>
            <input type="checkbox" checked={useStream} onChange={(e) => setUseStream(e.target.checked)} />
            流式
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--primary)", cursor: "pointer", whiteSpace: "nowrap", fontWeight: 600 }}>
            <input type="checkbox" checked={useSemantic} onChange={(e) => setUseSemantic(e.target.checked)} />
            🧬 语义
          </label>
        </div>

        {/* Citation Graph controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--border)" }}>
          <span style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>📊 引用图:</span>
          <input
            type="text"
            className="lit-filter-year"
            placeholder="输入种子论文 DOI…"
            value={graphDoi}
            onChange={(e) => setGraphDoi(e.target.value)}
            style={{ flex: 1, maxWidth: 280 }}
          />
          <button
            type="button"
            className="btn-secondary lit-gap-btn"
            onClick={() => doCitationGraph()}
            disabled={graphLoading || !graphDoi.trim()}
          >
            {graphLoading ? "加载中…" : "生成"}
          </button>
          {graphNodes.length > 0 && (
            <button
              type="button"
              className="btn-secondary lit-gap-btn"
              onClick={() => setShowGraph(!showGraph)}
            >
              {showGraph ? "📋 列表" : "📊 图视图"}
            </button>
          )}
        </div>

        {/* Expanded queries chips */}
        {expandedQueries.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: "28px" }}>扩展查询:</span>
            {expandedQueries.map((eq, i) => (
              <button
                key={i}
                type="button"
                className="lit-example-chip"
                onClick={() => { setQuery(eq); setTimeout(() => handleSearch(), 50); }}
                style={{ fontSize: 11, padding: "3px 10px" }}
              >
                {eq}
              </button>
            ))}
          </div>
        )}
      </form>

      {/* ═══ Results ═══ */}
      <section className="lit-results">
        {loading && (
          <div className="lit-loading">
            <Skeleton variant="text" width="40%" />
            <Skeleton variant="text" width="60%" />
            <Skeleton variant="card" count={4} />
          </div>
        )}

        {error && (
          <ErrorState
            message={error}
            variant="error"
            onRetry={() => doSearch()}
          />
        )}

        {!loading && !error && searchedQuery && papers.length === 0 && (
          <ErrorState
            message={`未找到与「${searchedQuery}」相关的文献`}
            details="尝试使用更宽泛的关键词，或切换到「全部语言」"
            variant="empty"
          />
        )}

        {!loading && !error && papers.length > 0 && (
          <>
            <div className="lit-results-header">
              <span>
                找到 <strong>{totalCount}</strong> 篇文献
                {searchedQuery && (
                  <>
                    {" "}
                    关于「<strong>{searchedQuery}</strong>」
                  </>
                )}
              </span>
            </div>

            <div className="lit-paper-list">
              {papers.map((paper, i) => (
                <article
                  key={paper.doi || `${paper.title}-${i}`}
                  className={`lit-paper-card ${
                    expandedAbstract === i ? "expanded" : ""
                  }`}
                >
                  <div className="lit-paper-main">
                    <h3 className="lit-paper-title">
                      {paper.url ? (
                        <a
                          href={paper.doi ? `https://doi.org/${paper.doi}` : paper.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {paper.title}
                        </a>
                      ) : (
                        paper.title
                      )}
                    </h3>

                    <div className="lit-paper-meta">
                      {paper.authors.length > 0 && (
                        <span className="lit-meta-authors">
                          {paper.authors.slice(0, 3).join(", ")}
                          {paper.authors.length > 3 &&
                            ` 等${paper.authors.length}人`}
                        </span>
                      )}
                      {paper.year && (
                        <span className="lit-meta-year">{paper.year}</span>
                      )}
                      {paper.journal && (
                        <span className="lit-meta-journal">
                          {paper.journal}
                        </span>
                      )}
                      <span className="lit-meta-source">
                        {SOURCE_LABELS[paper.source] || paper.source}
                      </span>
                      {paper.citation_count > 0 && (
                        <span className="lit-meta-citations">
                          📊 被引 {paper.citation_count} 次
                        </span>
                      )}
                      {paper.language === "zh" && (
                        <span className="lit-badge lit-badge-lang">中文</span>
                      )}
                    </div>

                    {paper.abstract && (
                      <div
                        className={`lit-paper-abstract ${
                          expandedAbstract === i ? "expanded" : "collapsed"
                        }`}
                        onClick={() =>
                          setExpandedAbstract(
                            expandedAbstract === i ? null : i
                          )
                        }
                      >
                        <p>{paper.abstract}</p>
                        {paper.abstract.length > 200 && (
                          <span className="lit-abstract-toggle">
                            {expandedAbstract === i ? "收起 ▲" : "展开阅读 ▼"}
                          </span>
                        )}
                      </div>
                    )}

                    {paper.methodology_tags.length > 0 && (
                      <div className="lit-method-tags">
                        {paper.methodology_tags.map((tag) => (
                          <span key={tag} className="lit-tag lit-tag-method">
                            {METHOD_LABELS[tag] || tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </section>

      {/* ═══ Citation Graph View ═══ */}
      {showGraph && (
        <section className="lit-gap-panel dash-card" style={{ marginTop: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h3 style={{ margin: 0 }}>📊 引用网络图</h3>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              种子: {graphSeedDoi} · {graphNodes.length} 节点 / {graphEdges.length} 边
            </span>
          </div>
          {graphLoading ? (
            <Skeleton variant="card" count={2} />
          ) : graphNodes.length === 0 ? (
            <p className="lit-subtitle" style={{ textAlign: "center", padding: 32 }}>
              未找到引用数据 — 请确认 DOI 是否正确
            </p>
          ) : (
            <CitationGraph
              nodes={graphNodes}
              edges={graphEdges}
              seedDoi={graphSeedDoi}
              onNodeClick={(doi) => { setGraphDoi(doi); doCitationGraph(doi); }}
            />
          )}
        </section>
      )}

      {/* ═══ Gap Analysis Panel ═══ */}
      {gapResult && (
        <section className="lit-gap-panel dash-card">
          <h3>🔬 研究空白分析：{gapResult.topic}</h3>
          <p className="dash-card-subtitle">
            基于 {gapResult.papers_found} 篇文献覆盖度分析
          </p>

          <div className="lit-gap-grid">
            {gapResult.methodology_gaps.length > 0 && (
              <div className="lit-gap-col">
                <h4>🔧 方法论空白</h4>
                <ul>
                  {gapResult.methodology_gaps.map((g, i) => (
                    <li key={i}>{g}</li>
                  ))}
                </ul>
              </div>
            )}
            {gapResult.region_gaps.length > 0 && (
              <div className="lit-gap-col">
                <h4>🌍 区域覆盖空白</h4>
                <ul>
                  {gapResult.region_gaps.map((g, i) => (
                    <li key={i}>{g}</li>
                  ))}
                </ul>
              </div>
            )}
            {gapResult.population_gaps.length > 0 && (
              <div className="lit-gap-col">
                <h4>👥 人群覆盖空白</h4>
                <ul>
                  {gapResult.population_gaps.map((g, i) => (
                    <li key={i}>{g}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {gapResult.recommendations.length > 0 && (
            <div className="lit-gap-recs">
              <h4>💡 建议</h4>
              <ol>
                {gapResult.recommendations.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ol>
            </div>
          )}
        </section>
      )}

      {/* ═══ Empty pre-search state ═══ */}
      {!loading && !error && !searchedQuery && (
        <div className="lit-onboarding">
          <div className="lit-onboarding-icon">📚</div>
          <h3>开始你的文献探索</h3>
          <div className="lit-onboarding-tips">
            <p>💡 <strong>搜索提示：</strong></p>
            <ul>
              <li>使用研究领域关键词，如「社区治理」「乡村振兴」</li>
              <li>添加方法论词汇，如「民族志」「扎根理论」</li>
              <li>中英双语搜索可获得更全面的结果</li>
              <li>使用「研究空白分析」发现可贡献的学术空间</li>
            </ul>
          </div>
          <div className="lit-example-queries">
            <span>试试：</span>
            {[
              "基层治理 公民参与",
              "rural China social capital",
              "社区 老年人 社会支持",
              "mixed methods education equity",
            ].map((eq) => (
              <button
                key={eq}
                className="lit-example-chip"
                onClick={() => {
                  setQuery(eq);
                  setTimeout(() => {
                    const form = document.querySelector(
                      ".lit-search-bar"
                    ) as HTMLFormElement;
                    if (form) form.requestSubmit();
                  }, 100);
                }}
              >
                {eq}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
