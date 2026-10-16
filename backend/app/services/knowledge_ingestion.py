
"""
 M.4 - Knowledge Card Ingestion Service.
Optionally reads deployment-owned JSON knowledge cards and inserts them into SQLite.
The public repository ships no corpus; operators must supply authorized data.
Seeds M.3 design clusters (P0-2/P0-3/P0-4). Idempotent for the built-in clusters.
"""
import json, logging
from pathlib import Path
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.knowledge_card import ReferenceCard, SkillsCluster, TriggerKeyword
from app.services.knowledge_manifest import KnowledgeManifestError, iter_approved_items

logger = logging.getLogger(__name__)
CLUSTERS = [
    {"cluster_id": "P0-2", "name": "Cultural Knowledge", "description": "Cultural sensitivity reminders during interviews", "priority": 0,
     "prompt_template": "Cultural reminder: {trigger_topic}\nRegion: {region_context}\nNote: {cultural_note}\nFramework: {core_concepts} (source: {source_slug})\nAction: {practical_guidelines}",
     "sub_modules": [
         {"id": "P0-2a", "name": "Political Sensitivity", "triggers": ["government", "cadre", "policy", "party", "system", "politics"]},
         {"id": "P0-2b", "name": "Grassroots Governance", "triggers": ["rural", "township", "county", "village"]},
         {"id": "P0-2c", "name": "Rural Social Structure", "triggers": ["peasant", "land", "class", "landlord"]},
         {"id": "P0-2d", "name": "Cross-cultural Boundaries", "triggers": ["cross-province", "ethnic", "dialect", "minority"]},
         {"id": "P0-2e", "name": "Power and Relationships", "triggers": ["power", "guanxi", "face", "hometown"]},
     ]},
    {"cluster_id": "P0-3", "name": "Interview Methods", "description": "Real-time interview strategy guidance", "priority": 1,
     "prompt_template": "Method reminder: {interview_mode}\nBest practice: {practical_guidelines} (source: {source_slug})\nRisk: {ethical_notes}\nFollow-up: based on {core_concepts}",
     "sub_modules": [
         {"id": "P0-3a", "name": "In-depth Interview", "triggers": ["in-depth interview", "phenomenology", "life history", "one-on-one"]},
         {"id": "P0-3b", "name": "Focus Group", "triggers": ["focus group", "group discussion", "multiple participants"]},
         {"id": "P0-3c", "name": "Interview Rapport", "triggers": ["rapport", "trust", "relationship building"]},
         {"id": "P0-3d", "name": "Ethics", "triggers": ["ethics", "informed consent", "IRB", "anonymity", "sensitive"]},
         {"id": "P0-3e", "name": "Survey Design", "triggers": ["questionnaire", "scale", "survey", "quantitative", "sampling"]},
     ]},
    {"cluster_id": "P0-4", "name": "Indigenous Coding", "description": "Concept coding framework for Chinese social research", "priority": 2,
     "prompt_template": "Coding suggestion: detected {concept_keywords}\nFramework: {coding_dimension}\nRelated: {core_concepts}\nAnchor: {practical_guidelines}\nCase: {case_studies}",
     "sub_modules": [
         {"id": "P0-4a", "name": "Differential Mode Coding", "triggers": ["differential mode", "guanxi distance", "face"]},
         {"id": "P0-4b", "name": "Political System Coding", "triggers": ["tiao-kuai", "pressure system", "party committee"]},
         {"id": "P0-4c", "name": "Economic Class Coding", "triggers": ["class analysis", "land relations", "commercial capital"]},
         {"id": "P0-4d", "name": "Cultural Identity Coding", "triggers": ["regional identity", "dialect boundary", "tradition"]},
     ]},
]

CLUSTER_RULES = [
    ("zhongxian", ["P0-2", "P0-4"]),
    ("xianxiang", ["P0-2", "P0-4"]),
    ("xunwu", ["P0-2", "P0-4"]),
    ("interviewing_as_qualitative_research", ["P0-3"]),
    ("research_design_qualitative", ["P0-3"]),
    ("the_practice_of_social_research", ["P0-3"]),
]


def _assign_clusters(source_slug):
    for prefix, clusters in CLUSTER_RULES:
        if source_slug.startswith(prefix):
            return ",".join(clusters)
    return ""


def _build_search_text(card):
    parts = []
    for field in ["keywords", "practical_guidelines", "ethical_notes", "cultural_knowledge"]:
        val = card.get(field, [])
        if isinstance(val, list):
            parts.extend(str(v) for v in val)
        elif isinstance(val, str):
            parts.append(val)
    cc = card.get("core_concepts", [])
    if isinstance(cc, list):
        for item in cc:
            if isinstance(item, dict):
                parts.append(item.get("term", ""))
                parts.append(item.get("definition", ""))
            elif isinstance(item, str):
                parts.append(item)
    return " ".join(parts)


async def seed_clusters(db: AsyncSession):
    for c in CLUSTERS:
        result = await db.execute(select(SkillsCluster).where(SkillsCluster.cluster_id == c["cluster_id"]))
        if result.scalar_one_or_none():
            continue
        db.add(SkillsCluster(**c))
    await db.flush()


async def seed_triggers(db: AsyncSession):
    for c in CLUSTERS:
        for sm in c.get("sub_modules", []):
            for kw in sm.get("triggers", []):
                result = await db.execute(
                    select(TriggerKeyword).where(TriggerKeyword.keyword == kw, TriggerKeyword.cluster_id == c["cluster_id"]))
                if result.scalar_one_or_none():
                    continue
                db.add(TriggerKeyword(keyword=kw, cluster_id=c["cluster_id"], sub_module_id=sm["id"], weight=1.0))
    await db.flush()


async def ingest_all(db: AsyncSession) -> dict:
    result = await db.execute(select(func.count(ReferenceCard.id)))
    existing = result.scalar() or 0
    await seed_clusters(db)
    await seed_triggers(db)

    if not settings.knowledge_dir:
        await db.commit()
        return {
            "cards_ingested": 0,
            "total_cards": existing,
            "clusters": len(CLUSTERS),
            "status": "manifest_required",
        }

    try:
        approved_items = iter_approved_items(settings.knowledge_dir)
    except KnowledgeManifestError as exc:
        logger.warning("Knowledge runtime gate rejected package: %s", exc)
        await db.commit()
        return {
            "cards_ingested": 0,
            "total_cards": existing,
            "clusters": len(CLUSTERS),
            "status": "manifest_invalid",
        }

    ingested = 0
    for item, cards_path in approved_items:
        already_loaded = await db.scalar(
            select(func.count(ReferenceCard.id)).where(ReferenceCard.source_slug == item.source_slug)
        )
        if already_loaded:
            continue
        data = json.loads(cards_path.read_text(encoding="utf-8"))
        if data.get("source") and data["source"] != item.source_slug:
            logger.warning("Skipping source mismatch for %s", item.source_slug)
            continue
        clusters = _assign_clusters(item.source_slug)
        for card in data.get("cards", []):
            db.add(ReferenceCard(
                source_slug=item.source_slug,
                source_file=card.get("source_file", ""),
                source_section=card.get("source_section", ""),
                keywords=card.get("keywords", []),
                core_concepts=card.get("core_concepts", []),
                practical_guidelines=card.get("practical_guidelines", []),
                case_studies=card.get("case_studies", []),
                ethical_notes=card.get("ethical_notes", []),
                cultural_knowledge=card.get("cultural_knowledge", []),
                applicable_scenarios=card.get("applicable_scenarios", []),
                confidence=card.get("confidence", 3),
                extracted_at=card.get("extracted_at", ""),
                clusters=clusters,
                search_text=_build_search_text(card),
            ))
            ingested += 1
    await db.commit()
    total = await db.execute(select(func.count(ReferenceCard.id)))
    return {
        "cards_ingested": ingested,
        "total_cards": total.scalar(),
        "clusters": len(CLUSTERS),
        "status": "ok" if ingested else "already_complete",
    }
