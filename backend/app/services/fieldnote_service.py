"""
Field Note Service — AI-assisted field note generation during/after interviews.

Generates four types of structured field notes:
  - quote:        key verbatim quotes (2-3 per session, with estimated timestamps)
  - observation:  environmental/situational observations inferred from dialogue
  - reflection:   methodological reflections on interview quality
  - memo:         analytic memos (preliminary theoretical connections, hypotheses)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.survey import FieldNote

if TYPE_CHECKING:
    from app.services.ai import AIService

logger = logging.getLogger(__name__)

FIELD_NOTE_PROMPT = """你是一位经验丰富的田野调查方法论专家。请根据以下访谈转录文本，
生成结构化田野笔记。输出JSON格式（不要markdown代码块，不要额外文字）。

要求：
1. "quotes": 2-3条关键引语，每条含 { "text": "...", "rationale": "为什么重要", "estimated_seconds": 数字 }
2. "observations": 1-2条情境观察，从对话内容推断田野环境/氛围，每条 { "content": "..." }
3. "reflections": 1-2条方法论反思，关于访谈技巧/追问效果/节奏，每条 { "content": "..." }
4. "memos": 1-2条分析备忘录，初步理论联想/待验证假设/值得追问的方向，每条 { "content": "..." }

访谈情境: {scenario}
访谈主题: {theme}

访谈转录:
{transcript}

输出JSON:
{{
  "quotes": [...],
  "observations": [...],
  "reflections": [...],
  "memos": [...]
}}"""


async def generate_field_notes(
    db: AsyncSession,
    ai: "AIService",
    session_id: int,
    transcript: str,
    scenario: str = "community_interview",
    theme: str = "academic",
) -> list[FieldNote]:
    """Generate structured field notes from an interview transcript.

    Returns a list of persisted FieldNote rows (quote + observation + reflection + memo).
    """
    if not transcript or len(transcript.strip()) < 50:
        logger.info("Transcript too short for field note generation (session=%s)", session_id)
        return []

    scenario_map = {
        "community_interview": "社区访谈",
        "in_depth_interview": "深度访谈",
        "focus_group": "焦点小组",
        "participant_observation": "参与观察",
        "household_survey": "入户调查",
    }
    theme_map = {
        "academic": "学术研究",
        "government": "政务调研",
        "youth": "青年实践",
    }

    scenario_cn = scenario_map.get(scenario, scenario)
    theme_cn = theme_map.get(theme, theme)

    prompt = FIELD_NOTE_PROMPT.format(
        scenario=scenario_cn,
        theme=theme_cn,
        transcript=transcript[:6000],
    )

    try:
        response = await ai.chat(
            messages=[
                {"role": "system", "content": "你是一个田野调查方法论专家。只输出JSON，不要markdown代码块。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=2048,
            task="field_notes",
        )

        data = _parse_json(response)
        notes: list[FieldNote] = []
        sort_order = 0

        for q in data.get("quotes", []):
            note = FieldNote(
                session_id=session_id,
                note_type="quote",
                content=q.get("text", q.get("content", "")),
                timestamp_in_recording=q.get("estimated_seconds"),
                tags=json.dumps(
                    [t.strip() for t in q.get("rationale", "").split("；") if t.strip()],
                    ensure_ascii=False,
                ),
                ai_generated=True,
                sort_order=sort_order,
            )
            db.add(note)
            notes.append(note)
            sort_order += 1

        for obs in data.get("observations", []):
            note = FieldNote(
                session_id=session_id,
                note_type="observation",
                content=obs.get("content", obs.get("text", "")),
                ai_generated=True,
                sort_order=sort_order,
            )
            db.add(note)
            notes.append(note)
            sort_order += 1

        for ref in data.get("reflections", []):
            note = FieldNote(
                session_id=session_id,
                note_type="reflection",
                content=ref.get("content", ref.get("text", "")),
                ai_generated=True,
                sort_order=sort_order,
            )
            db.add(note)
            notes.append(note)
            sort_order += 1

        for memo in data.get("memos", []):
            note = FieldNote(
                session_id=session_id,
                note_type="memo",
                content=memo.get("content", memo.get("text", "")),
                ai_generated=True,
                sort_order=sort_order,
            )
            db.add(note)
            notes.append(note)
            sort_order += 1

        await db.commit()
        logger.info(
            "Generated %d field notes for session %s (%d quotes, %d obs, %d refl, %d memos)",
            len(notes), session_id,
            len(data.get("quotes", [])),
            len(data.get("observations", [])),
            len(data.get("reflections", [])),
            len(data.get("memos", [])),
        )
        return notes

    except Exception as e:
        logger.warning("Field note generation failed for session %s: %s", session_id, e)
        return []


async def list_notes(
    db: AsyncSession,
    session_id: int,
    note_type: str | None = None,
) -> list[FieldNote]:
    """List field notes for a session, optionally filtered by type."""
    stmt = select(FieldNote).where(FieldNote.session_id == session_id)
    if note_type:
        stmt = stmt.where(FieldNote.note_type == note_type)
    stmt = stmt.order_by(FieldNote.sort_order)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_note(
    db: AsyncSession,
    note_id: int,
    content: str,
    editor_profile_id: int | None = None,
) -> FieldNote | None:
    """Update a field note's content (marks as human-edited)."""
    result = await db.execute(select(FieldNote).where(FieldNote.id == note_id))
    note = result.scalar_one_or_none()
    if note is None:
        return None
    note.content = content
    note.ai_edited = True
    if editor_profile_id:
        note.editor_profile_id = editor_profile_id
    await db.commit()
    await db.refresh(note)
    return note


async def delete_note(db: AsyncSession, note_id: int) -> bool:
    """Delete a field note."""
    result = await db.execute(select(FieldNote).where(FieldNote.id == note_id))
    note = result.scalar_one_or_none()
    if note is None:
        return False
    await db.delete(note)
    await db.commit()
    return True


async def export_notes(
    db: AsyncSession,
    session_id: int,
    fmt: str = "markdown",
) -> str:
    """Export all field notes for a session as markdown or JSON."""
    notes = await list_notes(db, session_id)

    if fmt == "json":
        return json.dumps(
            [
                {
                    "id": n.id,
                    "note_type": n.note_type,
                    "content": n.content,
                    "timestamp_in_recording": n.timestamp_in_recording,
                    "tags": _safe_json_list(n.tags),
                    "ai_generated": n.ai_generated,
                    "ai_edited": n.ai_edited,
                    "sort_order": n.sort_order,
                }
                for n in notes
            ],
            ensure_ascii=False,
            indent=2,
        )

    type_labels = {
        "quote": "💬 关键引语",
        "observation": "👁 情境观察",
        "reflection": "🔍 方法反思",
        "memo": "📝 分析备忘",
        "methodology": "📐 方法论",
    }
    lines = ["# 田野笔记", "", f"共 {len(notes)} 条笔记", ""]
    for n in notes:
        label = type_labels.get(n.note_type, n.note_type)
        lines.append(f"## {label}")
        lines.append("")
        lines.append(n.content)
        lines.append("")
        if n.timestamp_in_recording is not None:
            mins = int(n.timestamp_in_recording // 60)
            secs = int(n.timestamp_in_recording % 60)
            lines.append(f"⏱ {mins:02d}:{secs:02d}  ")
        tags = _safe_json_list(n.tags)
        if tags:
            lines.append(f"🏷 {' · '.join(tags)}  ")
        lines.append(f"{'🤖 AI生成' if n.ai_generated else '✍ 手动记录'}{' (已编辑)' if n.ai_edited else ''}  ")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _parse_json(content: str) -> dict:
    """Parse JSON from LLM response, handling markdown code fences."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse field note JSON, chars=%s", len(text))
        return {}


def _safe_json_list(raw: str) -> list:
    """Safely parse a JSON string into a list."""
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
