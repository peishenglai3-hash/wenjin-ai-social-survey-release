"""
P0 — Literature discovery API endpoints.

GET  /api/v1/literature/search           — Search academic papers
POST /api/v1/literature/search           — Search (JSON body variant)
POST /api/v1/literature/expand-query     — LLM query expansion (multi-lingual)
GET  /api/v1/literature/search/stream    — SSE streaming search
POST /api/v1/literature/gap-analysis     — Research gap analysis
GET  /api/v1/literature/citations        — Citation lookup by DOI
POST /api/v1/literature/recommend        — Seed-paper-based recommendations
POST /api/v1/literature/semantic-search  — Vector similarity search (ChromaDB)
POST /api/v1/literature/index-papers     — Index papers into vector store
GET  /api/v1/literature/citation-graph   — Citation graph data (nodes + edges)
"""
import json
import asyncio
import logging
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.literature_service import get_literature_service
from app.services.vector_store import get_vector_store

router = APIRouter(prefix="/literature", tags=["Literature Discovery"])
logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    language_pref: str = Field("all")
    methodology_filter: str | None = Field(None)
    year_from: int | None = Field(None, ge=1900, le=2030)
    year_to: int | None = Field(None, ge=1900, le=2030)
    top_n: int = Field(20, ge=1, le=50)


class GapAnalysisRequest(BaseModel):
    topic: str = Field(..., min_length=2)
    seed_dois: list[str] = Field(default_factory=list)


class ExpandQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    n_variants: int = Field(3, ge=1, le=6)


class RecommendRequest(BaseModel):
    seed_doi: str = Field(..., min_length=5)
    top_n: int = Field(20, ge=1, le=50)


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_n: int = Field(20, ge=1, le=50)
    language_filter: str | None = Field(None)
    semantic_weight: float = Field(0.6, ge=0.0, le=1.0)


class IndexPapersRequest(BaseModel):
    papers: list[dict] = Field(..., min_length=1)
    """List of paper dicts, each with title, abstract, doi, year, source, etc."""


class CitationGraphRequest(BaseModel):
    seed_doi: str = Field(..., min_length=5)
    depth: int = Field(2, ge=1, le=3)
    max_nodes: int = Field(50, ge=5, le=200)


@router.get("/search")
async def literature_search(
    query: str = Query(..., min_length=2),
    language_pref: str = Query("all"),
    methodology_filter: str | None = Query(None),
    year_from: int | None = Query(None, ge=1900),
    year_to: int | None = Query(None, le=2030),
    top_n: int = Query(20, ge=1, le=50),
):
    """Search academic literature via OpenAlex (free, CC0, no API key needed)."""
    service = get_literature_service()
    year_range = (year_from or 1900, year_to or 2030) if (year_from or year_to) else None
    papers = await service.search(
        query=query, language_pref=language_pref,
        methodology_filter=methodology_filter,
        year_range=year_range, top_n=top_n,
    )
    return {"query": query, "count": len(papers), "papers": [p.to_dict() for p in papers]}


@router.post("/search")
async def literature_search_post(payload: SearchRequest):
    """Search academic literature (POST variant with JSON body)."""
    service = get_literature_service()
    year_range = (
        (payload.year_from or 1900, payload.year_to or 2030)
        if (payload.year_from or payload.year_to) else None
    )
    papers = await service.search(
        query=payload.query, language_pref=payload.language_pref,
        methodology_filter=payload.methodology_filter,
        year_range=year_range, top_n=payload.top_n,
    )
    return {"query": payload.query, "count": len(papers), "papers": [p.to_dict() for p in papers]}


@router.post("/expand-query")
async def expand_query(payload: ExpandQueryRequest):
    """Use LLM to expand a user query into optimized academic search queries."""
    service = get_literature_service()
    result = await service.expand_query(payload.query, n_variants=payload.n_variants)
    return result


@router.get("/search/stream")
async def literature_search_stream(
    query: str = Query(..., min_length=2),
    language_pref: str = Query("all"),
    methodology_filter: str | None = Query(None),
    year_from: int | None = Query(None, ge=1900),
    year_to: int | None = Query(None, le=2030),
    top_n: int = Query(30, ge=1, le=50),
    expand: bool = Query(False),
):
    """SSE streaming literature search — progressive results as they arrive."""
    service = get_literature_service()
    year_range = (year_from or 1900, year_to or 2030) if (year_from or year_to) else None

    async def event_stream():
        try:
            queries = [query]
            if expand:
                try:
                    expanded = await service.expand_query(query, n_variants=2)
                    queries.extend((expanded.get("expanded_queries") or [])[:2])
                except Exception:
                    pass

            seen: set[str] = set()
            count = 0
            for q in queries:
                papers = await service.search(
                    query=q, language_pref=language_pref,
                    methodology_filter=methodology_filter,
                    year_range=year_range, top_n=max(10, top_n // len(queries)),
                )
                for paper in papers:
                    if paper.doi and paper.doi in seen:
                        continue
                    if paper.doi:
                        seen.add(paper.doi)
                    count += 1
                    if count > top_n:
                        break
                    yield f"data: {json.dumps({'type':'paper','paper':paper.to_dict(),'query_used':q,'count':count}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.05)
                if count >= top_n:
                    break
            yield f"data: {json.dumps({'type':'done','total':count,'queries':queries}, ensure_ascii=False)}\n\n"
        except Exception:
            logger.exception("Literature search stream failed")
            yield f"data: {json.dumps({'type':'error','message':'Literature search failed'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/gap-analysis")
async def gap_analysis(payload: GapAnalysisRequest):
    """Analyze research gaps: methodology, region, population coverage."""
    service = get_literature_service()
    result = await service.gap_analysis(
        topic=payload.topic,
        seed_papers=payload.seed_dois if payload.seed_dois else None,
    )
    return result.to_dict()


@router.get("/citations")
async def get_citations(doi: str = Query(..., min_length=5)):
    """Get paper info and cited-by list for a given DOI."""
    service = get_literature_service()
    return await service.get_citations(doi)


@router.post("/recommend")
async def recommend_papers(payload: RecommendRequest):
    """Find related papers from a seed DOI via OpenAlex citation graph."""
    service = get_literature_service()
    papers = await service.recommend_from_seed(payload.seed_doi, top_n=payload.top_n)
    return {"seed_doi": payload.seed_doi, "count": len(papers), "papers": [p.to_dict() for p in papers]}


# ── Tier 2: Vector Semantic Search (ChromaDB) ─────────────────────

@router.post("/semantic-search")
async def semantic_search(payload: SemanticSearchRequest):
    """Semantic vector search via ChromaDB with hybrid keyword re-ranking.

    Falls back to keyword search if the vector store is empty.
    """
    store = get_vector_store()
    if store.count() == 0:
        # Fallback: use traditional keyword search
        service = get_literature_service()
        papers = await service.search(query=payload.query, top_n=payload.top_n)
        return {
            "query": payload.query,
            "count": len(papers),
            "papers": [p.to_dict() for p in papers],
            "method": "keyword_fallback",
            "indexed_count": 0,
        }

    where_filter = None
    if payload.language_filter and payload.language_filter in ("zh", "en"):
        where_filter = {"language": payload.language_filter}

    semantic_results = store.hybrid_search(
        query=payload.query,
        top_n=payload.top_n,
        where=where_filter,
        semantic_weight=payload.semantic_weight,
    )
    return {
        "query": payload.query,
        "count": len(semantic_results),
        "papers": [r.to_dict() for r in semantic_results],
        "method": "semantic_hybrid",
        "indexed_count": store.count(),
    }


@router.post("/index-papers")
async def index_papers(payload: IndexPapersRequest):
    """Index a batch of paper metadata into the ChromaDB vector store.

    Accepts a list of paper dicts from any source (OpenAlex, Semantic Scholar, etc.).
    Each dict should have: title, abstract, doi, year, source, citation_count, language.
    """
    from app.services.literature_service import PaperResult

    papers = []
    for p_dict in payload.papers:
        papers.append(PaperResult(
            title=p_dict.get("title", ""),
            abstract=p_dict.get("abstract", ""),
            doi=p_dict.get("doi"),
            year=p_dict.get("year"),
            source=p_dict.get("source", "unknown"),
            citation_count=p_dict.get("citation_count", 0),
            language=p_dict.get("language", "en"),
            journal=p_dict.get("journal", ""),
            methodology_tags=p_dict.get("methodology_tags", []),
        ))

    store = get_vector_store()
    indexed = store.index_papers(papers)
    return {"indexed": indexed, "total_in_store": store.count()}


@router.get("/citation-graph")
async def citation_graph(
    seed_doi: str = Query(..., min_length=5),
    depth: int = Query(2, ge=1, le=3),
    max_nodes: int = Query(50, ge=5, le=200),
):
    """Build a citation graph (nodes + edges) from a seed paper DOI.

    Returns ECharts-compatible format: {nodes: [...], edges: [...]}
    """
    import aiohttp

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_dois: set[str] = set()

    async def add_node(doi: str, label_prefix: str = "") -> dict | None:
        """Fetch paper metadata from OpenAlex and add as a graph node."""
        clean_doi = doi.replace("https://doi.org/", "").strip()
        if clean_doi in seen_dois:
            return None
        seen_dois.add(clean_doi)

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "WenjinOpenSource/0.1 (+https://github.com/peishenglai3-hash/ai-social-survey)"},
            ) as session:
                url = f"https://api.openalex.org/works/doi:{clean_doi}"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
        except Exception:
            return None

        title = data.get("title", "Unknown")
        year = data.get("publication_year")
        citations = data.get("cited_by_count", 0)

        node = {
            "id": clean_doi,
            "name": title[:60] + ("..." if len(title) > 60 else ""),
            "year": year,
            "citations": citations,
            "symbolSize": max(15, min(60, citations ** 0.5 + 10)),
        }
        nodes.append(node)
        return data

    # Depth 1: Seed paper
    seed_data = await add_node(seed_doi, "seed")

    if seed_data and depth >= 2:
        # Depth 2: Papers cited by seed + papers citing seed
        seed_wid = seed_data.get("id", "")
        second_dois: list[str] = []

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "WenjinOpenSource/0.1 (+https://github.com/peishenglai3-hash/ai-social-survey)"},
        ) as session:
            # References (cited by seed)
            if seed_wid:
                refs_url = f"https://api.openalex.org/works?filter=cites:{seed_wid}&per_page=15&sort=cited_by_count:desc"
                try:
                    async with session.get(refs_url) as resp:
                        if resp.status == 200:
                            refs_data = await resp.json()
                            for w in refs_data.get("results", []):
                                doi = (w.get("doi") or "").replace("https://doi.org/", "")
                                if doi and doi not in seen_dois:
                                    second_dois.append(doi)
                except Exception:
                    pass

            # Citations (citing seed)
            citing_url = f"https://api.openalex.org/works?filter=cited_by:{seed_wid}&per_page=15&sort=cited_by_count:desc"
            try:
                async with session.get(citing_url) as resp:
                    if resp.status == 200:
                        citing_data = await resp.json()
                        for w in citing_data.get("results", []):
                            doi = (w.get("doi") or "").replace("https://doi.org/", "")
                            if doi and doi not in seen_dois:
                                second_dois.append(doi)
            except Exception:
                pass

        # Add second-level nodes
        for doi in second_dois[:max_nodes - 1]:
            node_data = await add_node(doi)
            if node_data:
                edges.append({"source": seed_doi, "target": doi})

    return {
        "seed_doi": seed_doi,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
