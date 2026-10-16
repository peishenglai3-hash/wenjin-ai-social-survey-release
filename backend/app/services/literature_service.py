"""
P0 — Literature Discovery Service.

三层级联文献检索:
  1. OpenAlex (primary, free, no API key) — 250M+ works
  2. Semantic Scholar (secondary, free API key) — 200M+ works, citation graph
  3. iData/CNKI (tertiary, pending API access) — Chinese social science papers

Supports: search, gap analysis, citation lookup, user-profile-weighted ranking.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import quote

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

# ── Data models ──────────────────────────────────────────────

@dataclass
class PaperResult:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    abstract: str = ""
    source: str = "openalex"
    citation_count: int = 0
    journal: str = ""
    methodology_tags: list[str] = field(default_factory=list)
    language: str = "en"
    url: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "doi": self.doi,
            "abstract": self.abstract[:500] if self.abstract else "",
            "source": self.source,
            "citation_count": self.citation_count,
            "journal": self.journal,
            "methodology_tags": self.methodology_tags,
            "language": self.language,
            "url": self.url,
        }


@dataclass
class GapAnalysisResult:
    topic: str
    papers_found: int
    methodology_gaps: list[str] = field(default_factory=list)
    region_gaps: list[str] = field(default_factory=list)
    population_gaps: list[str] = field(default_factory=list)
    temporal_gaps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "papers_found": self.papers_found,
            "methodology_gaps": self.methodology_gaps,
            "region_gaps": self.region_gaps,
            "population_gaps": self.population_gaps,
            "temporal_gaps": self.temporal_gaps,
            "recommendations": self.recommendations,
        }


# ── Methodology keyword patterns for tagging ──────────────────

METHODOLOGY_PATTERNS = {
    "qualitative_interview": [
        "in-depth interview", "semi-structured interview",
        "深度访谈", "半结构访谈", "qualitative interview"
    ],
    "ethnography": [
        "ethnography", "participant observation", "fieldwork",
        "民族志", "田野调查", "参与观察"
    ],
    "case_study": [
        "case study", "case analysis", "案例研究", "个案研究"
    ],
    "survey_quantitative": [
        "survey", "questionnaire", "regression", "structural equation",
        "问卷调查", "回归分析", "结构方程"
    ],
    "grounded_theory": [
        "grounded theory", "扎根理论", "open coding", "axial coding"
    ],
    "mixed_methods": [
        "mixed method", "triangulation", "混合方法", "三角验证"
    ],
    "content_analysis": [
        "content analysis", "thematic analysis", "discourse analysis",
        "内容分析", "话语分析"
    ],
    "experimental": [
        "experiment", "randomized control", "field experiment",
        "实验研究", "随机对照"
    ],
}

CN_SOCIAL_SCIENCE_KEYWORDS = [
    "社会学", "政治学", "公共管理", "人类学", "传播学", "社会工作",
    "基层治理", "乡村", "社区", "政策", "制度", "文化",
    "social", "political", "governance", "rural", "urban",
    "community", "policy", "institution", "culture", "China", "Chinese",
]


class LiteratureService:
    """Multi-source academic literature search with profile-weighted ranking."""

    OPENALEX_BASE = "https://api.openalex.org/works"
    SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, semantic_scholar_key: str | None = None, idata_app_id: str | None = None,
                 idata_access_token: str | None = None):
        self._ss_key = semantic_scholar_key
        self._idata_app_id = idata_app_id
        self._idata_access_token = idata_access_token
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "WenjinOpenSource/0.1"},
            )
        return self._session

    # ── Public API ────────────────────────────────────────────

    async def search(
        self,
        query: str,
        language_pref: str = "all",
        methodology_filter: str | None = None,
        year_range: tuple[int, int] | None = None,
        top_n: int = 20,
    ) -> list[PaperResult]:
        """Search across available sources, deduplicate, and rank."""
        if not query.strip():
            return []

        tasks = [self._search_openalex(query, top_n * 2)]
        if self._ss_key:
            tasks.append(self._search_semantic_scholar(query, top_n))
        if self._idata_app_id and self._idata_access_token:
            tasks.append(self._search_idata(query, top_n))

        all_results: list[PaperResult] = []
        for task in asyncio.as_completed(tasks):
            try:
                results = await task
                all_results.extend(results)
            except Exception as e:
                logger.warning("Literature source failed: %s", e)

        merged = self._deduplicate(all_results)

        if language_pref == "zh":
            merged = [p for p in merged if p.language == "zh"]
        elif language_pref == "en":
            merged = [p for p in merged if p.language != "zh"]

        if methodology_filter:
            merged = [p for p in merged if methodology_filter in p.methodology_tags]

        if year_range:
            merged = [p for p in merged if p.year and year_range[0] <= p.year <= year_range[1]]

        for paper in merged:
            paper.methodology_tags = self._tag_methodology(paper)

        return merged[:top_n]

    async def gap_analysis(
        self,
        topic: str,
        seed_papers: list[str] | None = None,
    ) -> GapAnalysisResult:
        """Analyze research gaps based on literature coverage."""
        papers = await self.search(topic, top_n=50)
        result = GapAnalysisResult(topic=topic, papers_found=len(papers))

        if not papers:
            result.recommendations.append(
                "No papers found — consider broadening the search or using Chinese keywords"
            )
            return result

        method_counts: dict[str, int] = {}
        for p in papers:
            for tag in p.methodology_tags:
                method_counts[tag] = method_counts.get(tag, 0) + 1

        all_methods = set(METHODOLOGY_PATTERNS.keys())
        for method in all_methods:
            if method_counts.get(method, 0) < max(3, len(papers) * 0.05):
                result.methodology_gaps.append(
                    f"Method '{method}' is underrepresented ({method_counts.get(method, 0)} papers)"
                )

        china_papers = [p for p in papers if any(
            kw.lower() in (p.title + p.abstract).lower()
            for kw in ["china", "chinese", "中国", "农村", "城市", "社区"]
        )]
        if len(china_papers) < len(papers) * 0.1:
            result.region_gaps.append(
                "Limited Chinese/regional context — consider CNKI/iData search"
            )

        pop_keywords = ["rural", "urban", "elderly", "youth", "migrant",
                        "农民", "老年", "青年", "流动"]
        pop_hits = sum(1 for p in papers if any(
            kw.lower() in (p.title + p.abstract).lower() for kw in pop_keywords
        ))
        if pop_hits < len(papers) * 0.15:
            result.population_gaps.append(
                "Specific population groups underrepresented — refine scope"
            )

        if result.methodology_gaps:
            first_gap = result.methodology_gaps[0].split(" is ")[0]
            result.recommendations.append(
                f"Consider {first_gap} approach — this methodological gap could be "
                "a legitimate research contribution"
            )
        if result.region_gaps:
            result.recommendations.append(
                "Apply existing frameworks to Chinese/local context — a common and "
                "legitimate strategy for Chinese social science research"
            )
        if not result.methodology_gaps and not result.region_gaps:
            result.recommendations.append(
                "Field appears well-covered; consider narrowing scope or finding "
                "an overlooked sub-population or sub-region"
            )

        return result

    async def get_citations(self, doi: str) -> dict:
        """Get citation info for a specific DOI."""
        session = await self._get_session()
        paper_info = None
        citations = []

        try:
            url = f"{self.OPENALEX_BASE}/doi:{quote(doi, safe='')}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    paper_info = self._parse_openalex_work(data)
                    cited_by_url = data.get("cited_by_api_url", "")
                    if cited_by_url:
                        async with session.get(f"{cited_by_url}?per_page=10") as cr:
                            if cr.status == 200:
                                cdata = await cr.json()
                                for cw in cdata.get("results", []):
                                    citations.append(self._parse_openalex_work(cw))
        except Exception as e:
            logger.warning("Citation lookup failed: %s", e)

        return {
            "paper": paper_info.to_dict() if paper_info else None,
            "cited_by": [c.to_dict() for c in citations],
            "cited_by_count": len(citations),
        }

    # ── Source-specific search ─────────────────────────────────

    async def _search_openalex(self, query: str, per_page: int = 40) -> list[PaperResult]:
        """Search OpenAlex REST API — free, no key, CC0 license."""
        session = await self._get_session()
        papers: list[PaperResult] = []

        enhanced_query = query
        if any(kw in query for kw in ["中国", "治理", "基层", "乡村", "农村", "社区", "社会学"]):
            enhanced_query = f"{query} China social science"

        params = {
            "search": enhanced_query,
            "per_page": min(per_page, 200),
            "sort": "cited_by_count:desc",
            "filter": "type:article|book-chapter",
        }

        try:
            async with session.get(self.OPENALEX_BASE, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for work in data.get("results", []):
                        paper = self._parse_openalex_work(work)
                        title = work.get("title", "")
                        if any('一' <= c <= '鿿' for c in title):
                            paper.language = "zh"
                        papers.append(paper)
                else:
                    await resp.read()
                    logger.warning("OpenAlex returned HTTP %d", resp.status)
        except Exception as e:
            logger.warning("OpenAlex search failed: %s", e)

        return self._rank_cn_social_science(papers, query)

    async def _search_semantic_scholar(self, query: str, limit: int = 20) -> list[PaperResult]:
        """Search Semantic Scholar API."""
        if not self._ss_key:
            return []

        session = await self._get_session()
        papers: list[PaperResult] = []

        params = {
            "query": query,
            "limit": limit,
            "fields": "title,authors,year,abstract,externalIds,citationCount,journal,url",
        }

        try:
            async with session.get(
                f"{self.SEMANTIC_SCHOLAR_BASE}/search",
                params=params,
                headers={"x-api-key": self._ss_key},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for pd_data in data.get("data", []):
                        paper = PaperResult(
                            title=pd_data.get("title", ""),
                            authors=[a.get("name", "") for a in pd_data.get("authors", [])],
                            year=pd_data.get("year"),
                            doi=(pd_data.get("externalIds") or {}).get("DOI"),
                            abstract=pd_data.get("abstract", ""),
                            source="semantic_scholar",
                            citation_count=pd_data.get("citationCount", 0),
                            journal=(pd_data.get("journal") or {}).get("name", ""),
                            url=pd_data.get("url", ""),
                        )
                        papers.append(paper)
        except Exception as e:
            logger.warning("Semantic Scholar search failed: %s", e)

        return papers

    async def _search_idata(self, query: str, per_page: int = 20) -> list[PaperResult]:
        """Search iData/CNKI API — Chinese academic literature (requires API key).

        API docs: https://www.kancloud.cn/idata/idata
        Apply through the provider's official process for app_id + access_token
        """
        if not self._idata_app_id or not self._idata_access_token:
            return []

        session = await self._get_session()
        papers: list[PaperResult] = []

        params = {
            "keyword": query,
            "app_id": self._idata_app_id,
            "access_token": self._idata_access_token,
            "db": "SCDB",        # SCDB=综合, CJFQ=期刊, CDMD=博硕
            "sort_type": "1",    # 1=综合排序, 2=时间降序
            "start": "0",
        }

        try:
            async with session.get(
                "https://api.cn-ki.net/openapi/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == 1:
                        for item in data.get("data", {}).get("items", [])[:per_page]:
                            papers.append(PaperResult(
                                title=item.get("title", ""),
                                authors=[item.get("author", "")] if item.get("author") else [],
                                year=self._parse_idata_year(item.get("publish_time", "")),
                                doi=None,  # iData doesn't provide DOI in search results
                                abstract=item.get("abstract", ""),
                                source="idata",
                                citation_count=0,
                                journal=item.get("source", ""),
                                language="zh",
                                url=item.get("url", ""),
                            ))
                    else:
                        logger.warning("iData API error: %s", data.get("message", "unknown"))
                else:
                    logger.warning("iData returned HTTP %d", resp.status)
        except Exception as e:
            logger.warning("iData search failed: %s", e)

        return papers

    @staticmethod
    def _parse_idata_year(publish_time: str) -> int | None:
        """Extract year from iData publish_time (e.g. '2015年03期' or '2015')."""
        import re
        match = re.search(r'(\d{4})', publish_time)
        return int(match.group(1)) if match else None

    # ── Helpers ────────────────────────────────────────────────

    def _parse_openalex_work(self, work: dict) -> PaperResult:
        """Parse OpenAlex work object into PaperResult."""
        authorship = work.get("authorships", [])
        primary_location = work.get("primary_location", {}) or {}
        source_info = primary_location.get("source", {}) or {}

        return PaperResult(
            title=work.get("title", ""),
            authors=[a.get("author", {}).get("display_name", "") for a in authorship],
            year=work.get("publication_year"),
            doi=work.get("doi", "").replace("https://doi.org/", "") if work.get("doi") else None,
            abstract=(
                self._flatten_inverted_index(work["abstract_inverted_index"])
                if work.get("abstract_inverted_index") else ""
            ),
            source="openalex",
            citation_count=work.get("cited_by_count", 0),
            journal=source_info.get("display_name", ""),
            url=work.get("doi", ""),
        )

    def _deduplicate(self, papers: list[PaperResult]) -> list[PaperResult]:
        """Deduplicate by DOI, falling back to normalized title."""
        seen_dois: set[str] = set()
        seen_titles: set[str] = set()
        unique: list[PaperResult] = []

        for p in papers:
            if p.doi:
                doi_clean = p.doi.lower().strip()
                if doi_clean in seen_dois:
                    continue
                seen_dois.add(doi_clean)

            title_key = p.title.lower().strip().rstrip(".")
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            unique.append(p)

        return unique

    def _tag_methodology(self, paper: PaperResult) -> list[str]:
        """Tag paper with methodology keywords from title + abstract."""
        text = (paper.title + " " + paper.abstract).lower()
        tags = []
        for tag, patterns in METHODOLOGY_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in text:
                    tags.append(tag)
                    break
        return tags

    def _rank_cn_social_science(
        self, papers: list[PaperResult], query: str
    ) -> list[PaperResult]:
        """Boost Chinese social science relevance for CN-relevant queries."""
        has_cn_keywords = any(kw in query for kw in CN_SOCIAL_SCIENCE_KEYWORDS)
        if not has_cn_keywords:
            return papers

        for p in papers:
            text = (p.title + " " + p.abstract).lower()
            for kw in CN_SOCIAL_SCIENCE_KEYWORDS:
                if kw.lower() in text:
                    p.citation_count += 10
                    break

        return sorted(papers, key=lambda x: x.citation_count, reverse=True)

    @staticmethod
    def _flatten_inverted_index(inverted_index: dict) -> str:
        """Reconstruct OpenAlex abstract from inverted index."""
        if not inverted_index:
            return ""
        word_positions: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort()
        return " ".join(w for _, w in word_positions)

    async def expand_query(self, query: str, n_variants: int = 3) -> dict:
        """Use DeepSeek LLM to expand a user query into optimized academic search queries."""
        from app.services.ai import AIService
        ai = AIService(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model="deepseek-v4-flash",
        )
        prompt = (
            f"用户的研究检索问题是：「{query}」\n\n"
            f"请生成{n_variants}个优化的学术检索查询，要求：\n"
            f"1. 包含英文和中文版本\n"
            f"2. 包含方法论同义词（如 interview→in-depth interview, qualitative interview）\n"
            f"3. 包含更宽泛和更具体的术语变体\n"
            f"4. 适合在OpenAlex/Semantic Scholar中检索\n\n"
            f"输出纯JSON: {{\"original\": \"{query}\", \"expanded_queries\": [\"查询1\", \"查询2\", ...]}}"
        )
        messages = [
            {"role": "system", "content": "你是学术文献检索专家，擅长将研究问题转化为精确的学术数据库查询。输出纯JSON，不带Markdown格式。"},
            {"role": "user", "content": prompt},
        ]
        try:
            result = await ai.chat(messages, temperature=0.3, max_tokens=512, task="literature_search")
            import json as _json
            parsed = _json.loads(result.strip())
            return {
                "original": query,
                "expanded_queries": parsed.get("expanded_queries", [query])[:n_variants],
            }
        except Exception as e:
            logger.warning("Query expansion failed: %s", e)
            return {"original": query, "expanded_queries": [query]}

    async def recommend_from_seed(self, seed_doi: str, top_n: int = 20) -> list[PaperResult]:
        """Find related papers using OpenAlex citation graph from a seed DOI."""
        session = await self._get_session()
        papers: list[PaperResult] = []

        seed_url = f"https://api.openalex.org/works/doi:{seed_doi}"
        async with session.get(seed_url) as resp:
            if resp.status != 200:
                logger.warning("OpenAlex seed lookup failed: %s", resp.status)
                return papers
            seed_data = await resp.json()

        wid = seed_data.get("id", "")

        # 1. Papers this work cites
        refs_url = f"https://api.openalex.org/works?filter=cites:{wid}&sort=cited_by_count:desc&per_page={top_n}"
        async with session.get(refs_url) as resp:
            if resp.status == 200:
                data = await resp.json()
                for w in data.get("results", []):
                    papers.append(self._parse_openalex_work(w))

        # 2. Papers citing this work
        if len(papers) < top_n:
            citing_url = f"https://api.openalex.org/works?filter=cited_by:{wid}&sort=cited_by_count:desc&per_page={top_n}"
            async with session.get(citing_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for w in data.get("results", []):
                        papers.append(self._parse_openalex_work(w))

        # 3. Shared concepts
        if len(papers) < top_n and seed_data.get("concepts"):
            concept_ids = [c["id"] for c in seed_data["concepts"][:3]]
            related_url = f"https://api.openalex.org/works?filter=concepts.id:{'|'.join(concept_ids)}&sort=cited_by_count:desc&per_page={top_n}"
            async with session.get(related_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for w in data.get("results", []):
                        papers.append(self._parse_openalex_work(w))

        return self._deduplicate(papers)[:top_n]

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# Singleton
_literature_service: LiteratureService | None = None


def get_literature_service(semantic_scholar_key: str | None = None,
                          idata_app_id: str | None = None,
                          idata_access_token: str | None = None) -> LiteratureService:
    global _literature_service
    if _literature_service is None:
        _literature_service = LiteratureService(
            semantic_scholar_key=semantic_scholar_key or settings.semantic_scholar_api_key,
            idata_app_id=idata_app_id,
            idata_access_token=idata_access_token,
        )
    elif idata_app_id and not _literature_service._idata_app_id:
        _literature_service._idata_app_id = idata_app_id
        _literature_service._idata_access_token = idata_access_token
    return _literature_service
