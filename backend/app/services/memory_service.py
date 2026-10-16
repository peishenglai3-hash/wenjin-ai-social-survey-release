"""Memory Service — Hermes-style persistent user memory layer.

Core responsibilities:
  1. Extract structured memories from Copilot dialogue via LLM
  2. CRUD operations for UserMemory and UserSkill
  3. Retrieve relevant memories for context injection
  4. Build formatted memory blocks for system-prompt injection
  5. Generate reusable UserSkill from a dialogue round
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.survey import UserMemory, UserSkill
from app.services.ai import AIService

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Prompt templates
# ═══════════════════════════════════════════════════════════════════════════════

MEMORY_EXTRACTION_SYSTEM = """你是一个用户记忆提取器，运行在「问津」AI社会调查工作台中。
分析以下用户与AI助手的对话，提取关于该用户的**持久性信息**，用于未来更好地个性化服务。

## 可提取的记忆类别 (category)
- **preference** — 用户的偏好（研究方法、工具、写作风格、交互方式）
- **interest** — 用户的研究兴趣、关注的社会议题
- **expertise** — 用户擅长的领域、熟悉的工具
- **habit** — 用户的工作习惯、经常遇到的问题类型
- **goal** — 用户的学习目标、研究目标、职业目标
- **constraint** — 用户面临的约束（时间、资源、数据获取）
- **methodology** — 用户对方法论的看法和立场
- **tool** — 用户使用或询问过的工具
- **pitfall** — 用户常犯的错误或遇到的困难
- **note** — 其他值得记住的信息

## 提取规则（非常重要）
1. 只提取**面向未来有帮助**的、**相对稳定**的信息
2. 每条 memory.value 应是一句简洁、独立、自包含的中文陈述（20-80字）
3. memory.key 是一个短标签（英文snake_case，如 favoured_paradigm、struggles_with_sampling）
4. **confidence** (0.0-1.0)：你对这条记忆的确定程度。用户明确说的话 → 0.9+；推断的 → 0.5-0.7；不确定的不提取
5. **importance** (1-5)：这条信息对未来服务用户有多重要。核心研究偏好 → 5；边缘细节 → 1-2
6. **不要提取**：临时性信息（如"今天天气热"）、已经在user_profiles表中存在的静态属性（如role="undergraduate"是硬编码的）
7. 如果对话中没有新的持久信息，返回 {"memories": []}
8. 每轮对话最多提取 5 条记忆

## 输出格式（严格遵守JSON）
{"memories": [{"category": "...", "key": "...", "value": "...", "confidence": 0.8, "importance": 3}]}"""

MEMORY_EXTRACTION_USER = """## 用户消息
{user_message}

## AI 回复
{assistant_reply}

## 用户当前画像（供参考，不要重复提取画像中已有的信息）
{profile_summary}

请提取此轮对话中可获得的用户持久记忆。只返回JSON，不要附加解释。"""

SKILL_GENERATION_SYSTEM = """你是一个技能生成器，运行在「问津」AI社会调查工作台中。
观察用户与AI助手的对话，当用户的提问方式或AI的回答模式具有**复用价值**时，
将其提炼为一个可保存、可复用的"技能"（即一个提示词模板）。

## 什么样的对话值得生成为技能？
- 用户系统地提出了某类调研问题（如"帮我设计一份关于XX的访谈提纲"）
- AI的回答形成了一个可复用的模板/框架
- 用户明确表示"这个很好，以后也这样回答"
- 某类任务反复出现

## 技能生成规则
- name: 简洁的中文技能名（10字以内）
- description: 一句话描述这个技能的用途
- prompt_template: 将用户的原始问题中**具体的变量**替换为 {变量名} 占位符后形成模板
- category: questionnaire | interview | analysis | writing | methodology | general

## 输出格式（严格遵守JSON）
{"skill": {"name": "...", "description": "...", "prompt_template": "...", "category": "..."}} | null
如果当前对话不值得生成为技能，返回 null。"""

SKILL_GENERATION_USER = """## 用户消息
{user_message}

## AI 回复
{assistant_reply}

请判断是否值得生成技能。只返回JSON，不要附加解释。"""


# ═══════════════════════════════════════════════════════════════════════════════
# Memory Service
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryService:
    """Hermes-style memory: extract → store → retrieve → inject."""

    # ── Extraction ──────────────────────────────────────────────────────────

    @staticmethod
    async def extract_from_dialogue(
        ai: AIService,
        user_message: str,
        assistant_reply: str,
        profile_data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Call LLM to extract structured memories from one dialogue round.

        Returns a list of memory dicts ready for save_memories().
        """
        if not user_message or not assistant_reply:
            return []

        # Build a short profile summary to avoid re-extracting static attributes
        profile_summary = "暂无画像信息"
        if profile_data:
            parts = []
            role_map = {"undergraduate": "本科生", "graduate": "硕士", "phd_candidate": "博士",
                        "researcher": "研究人员", "faculty": "教师", "practitioner": "实务工作者"}
            exp_map = {"beginner": "新手", "intermediate": "有经验", "advanced": "经验丰富"}
            para_map = {"qualitative": "质性", "quantitative": "量化", "mixed": "混合"}
            if profile_data.get("role"):
                parts.append(f"身份: {role_map.get(profile_data['role'], profile_data['role'])}")
            if profile_data.get("experience_level"):
                parts.append(f"经验: {exp_map.get(profile_data['experience_level'], profile_data['experience_level'])}")
            if profile_data.get("paradigm_preference"):
                parts.append(f"范式偏好: {para_map.get(profile_data['paradigm_preference'], profile_data['paradigm_preference'])}")
            if parts:
                profile_summary = "；".join(parts)

        messages = [
            {"role": "system", "content": MEMORY_EXTRACTION_SYSTEM},
            {"role": "user", "content": MEMORY_EXTRACTION_USER.format(
                user_message=user_message[:2000],
                assistant_reply=assistant_reply[:2000],
                profile_summary=profile_summary,
            )},
        ]

        try:
            result = await ai.chat(
                messages, temperature=0.3, max_tokens=2048, task="memory_extraction",
            )
            data = json.loads(result.strip())
            memories = data.get("memories", [])
            # Validate each memory has required fields
            valid = []
            for m in memories:
                if all(k in m for k in ("category", "key", "value")):
                    m.setdefault("confidence", 0.5)
                    m.setdefault("importance", 3)
                    valid.append(m)
            logger.info("Extracted %d memories from dialogue", len(valid))
            return valid
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Memory extraction parse error: %s", e)
            return []
        except Exception as e:
            logger.error("Memory extraction failed: %s", e)
            return []

    # ── Persistence ─────────────────────────────────────────────────────────

    @staticmethod
    async def save_memories(
        db: AsyncSession,
        profile_id: int,
        memories: list[dict[str, Any]],
        source: str = "dialogue",
        commit: bool = True,
    ) -> int:
        """Upsert explicitly approved memories.  Returns count of changed rows.

        Upsert key: (profile_id, category, key) — same key for same profile
        updates the existing row rather than creating a duplicate.

        ``commit=False`` is reserved for the WISE approval transaction so the
        proposal status and memory promotion commit atomically.
        """
        saved = 0
        for m in memories:
            # Check for existing memory with same (profile_id, category, key)
            existing = await db.execute(
                select(UserMemory).where(
                    and_(
                        UserMemory.profile_id == profile_id,
                        UserMemory.category == m["category"],
                        UserMemory.key == m["key"],
                    )
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                # Skip suppressed memories — user explicitly asked to forget
                if (row.confidence or 0) < 0.15:
                    continue
                # Update existing — bump confidence if new observation agrees
                row.value = m["value"]
                row.confidence = min(1.0, m.get("confidence", 0.5) + 0.1)
                row.importance = max(row.importance, m.get("importance", 3))
                row.source = source
            else:
                row = UserMemory(
                    profile_id=profile_id,
                    category=m["category"],
                    key=m["key"],
                    value=m["value"],
                    confidence=m.get("confidence", 0.5),
                    importance=m.get("importance", 3),
                    source=source,
                )
                db.add(row)
            saved += 1

        if commit and saved:
            await db.commit()
            logger.info("Saved %d memories for profile %d", saved, profile_id)
        elif not commit:
            await db.flush()
            if saved:
                logger.info("Prepared %d memories for profile %d", saved, profile_id)
        return saved

    # ── Retrieval ───────────────────────────────────────────────────────────

    @staticmethod
    async def get_relevant_memories(
        db: AsyncSession,
        profile_id: int,
        query_hint: str = "",
        limit: int = 5,
    ) -> list[UserMemory]:
        """Retrieve memories relevant to the current conversation context.

        Current implementation: returns top-N by importance weighted by confidence.
        Future v0.5: vector similarity search over value text.
        """
        stmt = (
            select(UserMemory)
            .where(UserMemory.profile_id == profile_id)
            .order_by((UserMemory.importance * UserMemory.confidence).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        memories = list(result.scalars().all())

        # If query_hint provided, do naive keyword boost (v0.5 → vector search)
        if query_hint and memories:
            keywords = query_hint.lower().split()
            scored = []
            for m in memories:
                score = m.importance * m.confidence
                text = f"{m.category} {m.key} {m.value}".lower()
                hits = sum(1 for kw in keywords if kw in text)
                scored.append((score + hits * 2, m))
            scored.sort(key=lambda x: x[0], reverse=True)
            memories = [m for _, m in scored[:limit]]

        # Mark hit
        now = datetime.now(timezone.utc)
        for m in memories:
            m.hit_count = (m.hit_count or 0) + 1
            m.last_hit_at = now
        if memories:
            await db.commit()

        return memories

    @staticmethod
    async def list_memories(
        db: AsyncSession,
        profile_id: int,
        limit: int = 50,
    ) -> list[UserMemory]:
        """Read-only list of memories for display — does NOT increment hit_count.

        Unlike get_relevant_memories(), this is a pure read for the management UI.
        """
        stmt = (
            select(UserMemory)
            .where(UserMemory.profile_id == profile_id)
            .order_by(UserMemory.confidence.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── Injection ───────────────────────────────────────────────────────────

    @staticmethod
    def build_memory_context(memories: list[UserMemory]) -> str:
        """Format retrieved memories as a system-prompt block.

        Returns empty string if no memories to inject.
        """
        if not memories:
            return ""

        category_labels: dict[str, str] = {
            "preference": "偏好", "interest": "兴趣", "expertise": "擅长",
            "habit": "习惯", "goal": "目标", "constraint": "限制",
            "methodology": "方法论立场", "tool": "工具", "pitfall": "常见问题",
            "note": "备注",
        }

        lines = ["## 用户长期记忆（AI 从历史对话中提取）"]
        for m in memories:
            cat_label = category_labels.get(m.category, m.category)
            stars = "★" * m.importance
            lines.append(f"- [{cat_label}] {m.value} {stars}")

        return "\n".join(lines) + "\n"

    # ── Skill Generation ────────────────────────────────────────────────────

    @staticmethod
    async def generate_skill_from_dialogue(
        ai: AIService,
        user_message: str,
        assistant_reply: str,
    ) -> dict[str, Any] | None:
        """Attempt to generate a reusable UserSkill from a dialogue round.

        Returns a skill dict (name, description, prompt_template, category)
        or None if the dialogue isn't suitable for skill generation.
        """
        if not user_message or not assistant_reply:
            return None

        messages = [
            {"role": "system", "content": SKILL_GENERATION_SYSTEM},
            {"role": "user", "content": SKILL_GENERATION_USER.format(
                user_message=user_message[:2000],
                assistant_reply=assistant_reply[:2000],
            )},
        ]

        try:
            result = await ai.chat(
                messages, temperature=0.3, max_tokens=2048, task="memory_skill_gen",
            )
            data = json.loads(result.strip())
            skill_data = data.get("skill")
            if skill_data and all(k in skill_data for k in ("name", "description", "prompt_template")):
                skill_data.setdefault("category", "general")
                logger.info("Generated skill: %s", skill_data["name"])
                return skill_data
            return None
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Skill generation parse error: %s", e)
            return None
        except Exception as e:
            logger.error("Skill generation failed: %s", e)
            return None

    @staticmethod
    async def save_skill(
        db: AsyncSession,
        profile_id: int,
        skill_data: dict[str, Any],
        source_dialogue_snippet: str = "",
    ) -> UserSkill | None:
        """Persist a generated skill."""
        try:
            skill = UserSkill(
                profile_id=profile_id,
                name=skill_data.get("name", "未命名技能"),
                description=skill_data.get("description", ""),
                prompt_template=skill_data.get("prompt_template", ""),
                category=skill_data.get("category", "general"),
                tags=json.dumps(skill_data.get("tags", []), ensure_ascii=False),
                source_dialogue_snippet=source_dialogue_snippet[:500] if source_dialogue_snippet else None,
            )
            db.add(skill)
            await db.commit()
            await db.refresh(skill)
            logger.info("Saved skill %d: %s", skill.id, skill.name)
            return skill
        except Exception as e:
            logger.error("Save skill failed: %s", e)
            await db.rollback()
            return None

    @staticmethod
    async def list_user_skills(
        db: AsyncSession,
        profile_id: int,
        category: str | None = None,
    ) -> list[UserSkill]:
        """List skills for a user, optionally filtered by category."""
        stmt = select(UserSkill).where(UserSkill.profile_id == profile_id)
        if category:
            stmt = stmt.where(UserSkill.category == category)
        stmt = stmt.order_by(UserSkill.usage_count.desc(), UserSkill.id.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def delete_memory(db: AsyncSession, memory_id: int, profile_id: int) -> bool:
        """Delete a single memory. Returns True if deleted, False if not found/unauthorised."""
        result = await db.execute(
            select(UserMemory).where(
                and_(UserMemory.id == memory_id, UserMemory.profile_id == profile_id)
            )
        )
        memory = result.scalar_one_or_none()
        if not memory:
            return False
        await db.delete(memory)
        await db.commit()
        return True

    @staticmethod
    async def confirm_memory(db: AsyncSession, memory_id: int, profile_id: int) -> bool:
        """User manually confirms a memory — boost confidence by +0.3, capped at 1.0."""
        result = await db.execute(
            select(UserMemory).where(
                and_(UserMemory.id == memory_id, UserMemory.profile_id == profile_id)
            )
        )
        memory = result.scalar_one_or_none()
        if not memory:
            return False
        memory.confidence = min(1.0, (memory.confidence or 0.5) + 0.3)
        await db.commit()
        return True

    @staticmethod
    async def edit_memory(
        db: AsyncSession,
        memory_id: int,
        profile_id: int,
        value: str | None = None,
        key: str | None = None,
        category: str | None = None,
    ) -> bool:
        """Edit memory fields. Only non-None fields are updated."""
        result = await db.execute(
            select(UserMemory).where(
                and_(UserMemory.id == memory_id, UserMemory.profile_id == profile_id)
            )
        )
        memory = result.scalar_one_or_none()
        if not memory:
            return False
        if value is not None:
            memory.value = value
        if key is not None:
            memory.key = key
        if category is not None:
            memory.category = category
        await db.commit()
        return True

    @staticmethod
    async def suppress_memory(db: AsyncSession, memory_id: int, profile_id: int) -> bool:
        """Suppress a memory — sets confidence to 0.1, retaining the key to prevent re-extraction."""
        result = await db.execute(
            select(UserMemory).where(
                and_(UserMemory.id == memory_id, UserMemory.profile_id == profile_id)
            )
        )
        memory = result.scalar_one_or_none()
        if not memory:
            return False
        memory.confidence = 0.1
        await db.commit()
        return True

    @staticmethod
    async def delete_skill(db: AsyncSession, skill_id: int, profile_id: int) -> bool:
        """Delete a single skill."""
        result = await db.execute(
            select(UserSkill).where(
                and_(UserSkill.id == skill_id, UserSkill.profile_id == profile_id)
            )
        )
        skill = result.scalar_one_or_none()
        if not skill:
            return False
        await db.delete(skill)
        await db.commit()
        return True
