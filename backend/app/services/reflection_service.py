"""Reflection Service — sociological reflexivity engine for iterative profiling.

Based on:
  - French Pragmatism (Boltanski, Thévenot): actors reflexively adjust justifications in situ
  - Ethnomethodology (Garfinkel): social order is an ongoing accomplishment of members' practical actions
  - Sociological Reflexivity (Bourdieu): researchers must reflect on how their social position shapes understanding

This service powers the transition from "一键画像" (one-click profiling) → "反思性迭代画像"
(reflective iterative profiling) by orchestrating structured reflection dialogues after each
survey fieldwork session, extracting insights, and feeding them back into the Hermes memory
system to continuously refine the user profile.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.ai import AIService
from app.services.wise_service import WISEService

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Reflection Prompt Templates — structured by sociological tradition
# ═══════════════════════════════════════════════════════════════════════════════

REFLECTION_SYSTEM_PROMPT = """你是一个社会学反思教练，运行在「问津」AI社会调查工作台中。
你的任务不是评判用户的调查做得"好"或"坏"，而是引导用户进行**社会学反思**——
帮助他们审视自己的研究实践，发现隐含的预设，识别社会位置对研究的影响。

## 理论基础
你借助以下社会学传统来设计反思问题：

1. **法国实用主义（Boltanski & Thévenot）**
   - 行动者在不同情境中使用不同的"正当化秩序"（cité）来辩护自己的行动
   - 反思要点：你在调查中使用了什么样的论证逻辑？市场效率？公民权利？学术真理？情感联结？

2. **常人方法学（Garfinkel）**
   - 社会秩序并非天然存在，而是成员在日常实践中持续"成就"的
   - 反思要点：你和受访者是如何共同"制造"访谈秩序的？你的哪些默认预设被当作"理所当然"？

3. **反思社会学（Bourdieu）**
   - 研究者自身的社会位置（阶级、教育、性别等）会影响研究
   - 反思要点：你的身份如何影响了你对受访者世界的理解？你是否将自己的分类范畴强加于受访者的经验？

## 对话风格
- 使用开放式问题，引导用户自己发现，而非直接给答案
- 每次反思聚焦 2-3 个核心问题，不过载
- 使用学术语言但有温度，避免空洞说教
- 如果用户表现出不确定性或困惑，给予肯定——反思本身就是困难的

## 输出结构（用于后续记忆提取）
在反思对话结束后，附一个简短的 JSON 洞察块（不展示给用户，但会在返回中保留）：

```json
{"reflection_insights": [
  {"dimension": "theory_driven", "direction": -1, "confidence": 0.7,
   "rationale": "用户发现过度依赖理论框架导致忽略了受访者原生活语"},
  ...
]}
```

dimension 可选值: theory_driven, methodological_rigidity, analysis_depth,
  structure_preference, participation_level, tech_dependency, writing_style, learning_preference
direction: -2到+2，表示该维度应向哪个方向偏移
confidence: 0.0-1.0，AI 对该洞察的置信度
"""

REFLECTION_TRIGGERS = {
    "fieldwork_completed": {
        "title": "田野调查完成反思",
        "intro": "你刚完成了一次田野调查会话。让我们花几分钟反思一下这个过程。",
        "questions": [
            {
                "id": "surprising_moment",
                "prompt": "## 第一问：意外时刻\n\n在这次调查中，最让你感到**意外**的瞬间是什么？——受访者说了什么让你没想到的话？现场发生了什么与你预期不符的事？",
                "tradition": "ethnomethodology",
                "spectrum_touch": "structure_preference",
            },
            {
                "id": "presupposition_challenge",
                "prompt": "## 第二问：预设被挑战\n\n在进入田野之前，你对这个议题或这群人有什么**预设**？经过这次调查，哪些预设被**动摇**或**修正**了？",
                "tradition": "pragmatism",
                "spectrum_touch": "theory_driven",
            },
            {
                "id": "positionality",
                "prompt": "## 第三问：你的位置\n\n你的身份（学生/研究者/实务工作者）和你的社会背景，**如何影响**了你与受访者的互动？你是否注意到受访者因为你的身份而说了或没说什么？",
                "tradition": "bourdieu",
                "spectrum_touch": "participation_level",
            },
            {
                "id": "method_adaptation",
                "prompt": "## 第四问：方法的弹性\n\n你是否在访谈过程中**临时调整**了原来的访谈提纲或方法？如果有，为什么？调整后的效果如何？如果没有——是什么让你坚持原计划？",
                "tradition": "pragmatism",
                "spectrum_touch": "methodological_rigidity",
            },
        ],
    },
    "analysis_completed": {
        "title": "数据分析完成反思",
        "intro": "你刚完成了一轮数据分析。让我们从方法论角度反思一下。",
        "questions": [
            {
                "id": "coding_choice",
                "prompt": "## 第一问：编码选择\n\n在分析数据时，你是如何决定什么**值得编码**、什么**可以忽略**的？这个选择过程反映了你什么样的理论预设？",
                "tradition": "ethnomethodology",
                "spectrum_touch": "analysis_depth",
            },
            {
                "id": "alternative_reading",
                "prompt": "## 第二问：替代解读\n\n如果你换一个理论视角（比如从结构功能主义换成冲突论），同样的数据会呈现出**怎样不同的故事**？",
                "tradition": "pragmatism",
                "spectrum_touch": "theory_driven",
            },
            {
                "id": "voice_representation",
                "prompt": "## 第三问：声音的代表性\n\n在你的分析中，受访者的声音是**被忠实呈现**了，还是**被你的分析框架重新组织**了？你如何处理受访者表达中的矛盾和不一致？",
                "tradition": "bourdieu",
                "spectrum_touch": "writing_style",
            },
        ],
    },
    "project_completed": {
        "title": "项目完成综合反思",
        "intro": "恭喜你完成了一个调查项目！让我们对整个研究过程进行一次系统性反思。",
        "questions": [
            {
                "id": "learning_trajectory",
                "prompt": "## 第一问：学习轨迹\n\n回顾整个项目 —— 从选题到现在的最终成果 —— 你在**方法论理解和实际操作能力**上有什么变化？你现在的你和项目开始时的你，会做出哪些不同的选择？",
                "tradition": "pragmatism",
                "spectrum_touch": "learning_preference",
            },
            {
                "id": "knowledge_claim",
                "prompt": "## 第二问：知识主张的边界\n\n你现在对你研究问题的**回答**是什么？这个回答的**边界**在哪里——它适用于什么情境、什么人群、什么时间？你的研究发现中有多少是**情境特定的**，有多少可能具有**更广泛的适用性**？",
                "tradition": "bourdieu",
                "spectrum_touch": "analysis_depth",
            },
            {
                "id": "ethical_retrospective",
                "prompt": "## 第三问：伦理回顾\n\n回顾整个研究过程，有没有什么时刻让你在**伦理上感到不舒服**？受访者的隐私是否得到了充分保护？你的研究对受访者/社区产生了什么影响（正面或负面）？如果重新做，你会怎样改进？",
                "tradition": "bourdieu",
                "spectrum_touch": "participation_level",
            },
            {
                "id": "future_direction",
                "prompt": "## 第四问：下一步\n\n基于这次的发现和反思，你的**下一个研究问题**会是什么？这次经历如何**重塑了你的研究兴趣**？",
                "tradition": "pragmatism",
                "spectrum_touch": "theory_driven",
            },
        ],
    },
}

# Quick reflection — lightweight version for frequent use
QUICK_REFLECTION_PROMPT = """你刚完成了一次调查会话。请用 2-3 句话反思：

1. **一个意外**：什么与你预期不同？
2. **一个调整**：你临时改变了什么做法？
3. **一个洞察**：关于你自己作为研究者，你学到了什么？

请用中文回答，自然语言即可。"""

ITERATION_INSIGHT_SYSTEM = """你是一个用户画像演化分析师，运行在「问津」AI社会调查工作台中。
你的任务是分析用户的反思对话，提取关于用户**方法论光谱位置变化**的洞察。

## 光谱维度（1-5 Likert量表）
- theory_driven: 1=理论驱动 ←→ 5=经验驱动
- methodological_rigidity: 1=严谨规范 ←→ 5=灵活探索
- analysis_depth: 1=广度优先 ←→ 5=深度优先
- structure_preference: 1=结构化 ←→ 5=开放式
- participation_level: 1=旁观观察 ←→ 5=深度参与
- tech_dependency: 1=低技术 ←→ 5=高技术
- writing_style: 1=学术正式 ←→ 5=通俗亲和
- learning_preference: 1=示范引导 ←→ 5=自主探索

## 提取规则
1. 只提取用户在反思中**明确显现**的趋势，不推测
2. direction: -2（显著向左偏移）~ +2（显著向右偏移），0=无变化
3. 只有 confidence >= 0.6 的洞察才应被采纳
4. 如果反思中没有足够证据支持某个维度的变化，不要强行提取

## 输出格式（严格遵守JSON）
{"insights": [
  {"dimension": "learning_preference", "direction": +1, "confidence": 0.75,
   "rationale": "用户表示越来越喜欢自主探索而非依赖示范", "evidence": "用户说...（引用反思原文关键句）"}
]}"""


# ═══════════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ReflectionSession:
    """In-memory representation of a reflection dialogue."""
    session_id: str = ""
    trigger_type: str = ""  # fieldwork_completed | analysis_completed | project_completed
    user_id: int = 0
    project_id: int | None = None
    source_session_id: int | None = None  # the fieldwork/analysis session that triggered this
    questions: list[dict] = field(default_factory=list)
    answers: list[dict] = field(default_factory=list)  # [{question_id, user_response, ai_followup}]
    insights: list[dict] = field(default_factory=list)
    spectrum_shifts: list[dict] = field(default_factory=list)
    created_at: str = ""


@dataclass
class IterationInsight:
    """A single insight about profile evolution."""
    dimension: str = ""
    direction: int = 0  # -2 to +2
    confidence: float = 0.0
    rationale: str = ""
    evidence: str = ""
    source_reflection_id: int | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# Reflection Service
# ═══════════════════════════════════════════════════════════════════════════════

class ReflectionService:
    """Orchestrates sociological reflexivity dialogues for iterative profiling.

    Core flow:
      1. trigger() — start a reflection session after a fieldwork/analysis milestone
      2. ask_question() — pose a structured reflection question, get user response
      3. follow_up() — AI processes response and asks a probing follow-up
      4. conclude() — extract insights, compute spectrum shifts, store to memory
    """

    DEFAULT_QUESTIONS_PER_SESSION = 3  # Keep it focused, not overwhelming

    # ── Trigger ─────────────────────────────────────────────────────────────

    @staticmethod
    def get_trigger(trigger_type: str) -> dict | None:
        """Return the reflection trigger config for a given milestone."""
        return REFLECTION_TRIGGERS.get(trigger_type)

    @staticmethod
    def list_triggers() -> list[dict]:
        """List all available reflection triggers."""
        return [
            {"id": k, "title": v["title"], "question_count": len(v["questions"])}
            for k, v in REFLECTION_TRIGGERS.items()
        ]

    @staticmethod
    async def start_reflection(
        trigger_type: str,
        ai: AIService,
        profile_data: dict | None = None,
        project_data: dict | None = None,
        source_context: str = "",
    ) -> dict:
        """Initialize a reflection session.

        Returns the session state with the first question ready.
        """
        trigger = REFLECTION_TRIGGERS.get(trigger_type)
        if not trigger:
            return {"error": f"Unknown trigger type: {trigger_type}", "available": list(REFLECTION_TRIGGERS.keys())}

        # Select a subset of questions (2-3, not all 4)
        questions = trigger["questions"][:ReflectionService.DEFAULT_QUESTIONS_PER_SESSION]

        # Build context-rich intro
        context_block = ""
        if project_data:
            context_block += f"\n当前项目：{project_data.get('title', '未命名')}"
            if project_data.get("research_direction"):
                context_block += f"\n研究方向：{project_data['research_direction']}"
        if source_context:
            context_block += f"\n\n## 触发反思的背景信息\n{source_context[:1500]}"

        # Generate a personalized intro using AI
        intro_messages = [
            {"role": "system", "content": "你是一个温暖而专业的社会学反思引导者。根据用户当前的调查情况，生成一段2-3句的个性化反思引导语。不要过于正式，要让人感到这是一个有意义的停顿和回顾时刻。"},
            {"role": "user", "content": f"触发类型：{trigger['title']}\n{context_block}\n\n请为该用户生成一段反思引导语。"},
        ]
        try:
            personalized_intro = await ai.chat(
                intro_messages, temperature=0.7, max_tokens=256, task="summarize",
            )
        except Exception:
            logger.warning("Failed to generate personalized intro, using default", exc_info=True)
            personalized_intro = trigger["intro"]

        session_state = {
            "trigger_type": trigger_type,
            "title": trigger["title"],
            "intro": personalized_intro,
            "questions": questions,
            "current_question_index": 0,
            "answers": [],
            "context_block": context_block,
        }

        return session_state

    # ── Dialogue ────────────────────────────────────────────────────────────

    @staticmethod
    async def process_answer(
        session_state: dict,
        user_answer: str,
        ai: AIService,
        profile_data: dict | None = None,
    ) -> dict:
        """Process a user's reflection answer and generate follow-up.

        Returns updated session state with the next question (if any).
        """
        questions = session_state.get("questions", [])
        current_idx = session_state.get("current_question_index", 0)

        if current_idx >= len(questions):
            return {**session_state, "completed": True}

        current_q = questions[current_idx]

        # Generate AI follow-up to the user's answer
        followup_messages = [
            {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"""用户正在反思：{current_q['prompt']}

用户的回答：
{user_answer}

请基于用户的回答提供一个简短的**反思性反馈**（2-4句话）：
1. 肯定用户愿意反思的态度
2. 如果用户提到了某个具体经验，帮ta将其与更广泛的社会学概念关联
3. 如果需要更深挖，提出一个温和的追问
4. 不要评判对错，不要给建议，保持引导姿态"""},
        ]

        try:
            ai_followup = await ai.chat(
                followup_messages, temperature=0.5, max_tokens=512, task="hints",
            )
        except Exception as e:
            logger.warning("Reflection follow-up generation failed: %s", e)
            ai_followup = "谢谢你的分享。反思本身就是一种重要的学术实践。"

        # Record the answer
        answer_record = {
            "question_id": current_q["id"],
            "question_prompt": current_q["prompt"],
            "user_answer": user_answer,
            "ai_followup": ai_followup,
            "tradition": current_q.get("tradition", ""),
            "spectrum_touch": current_q.get("spectrum_touch", ""),
        }

        answers = list(session_state.get("answers", []))
        answers.append(answer_record)

        next_idx = current_idx + 1
        completed = next_idx >= len(questions)

        return {
            **session_state,
            "current_question_index": next_idx,
            "answers": answers,
            "completed": completed,
            "ai_followup": ai_followup if not completed else None,
            "next_question": questions[next_idx] if not completed else None,
        }

    # ── Conclusion & Insight Extraction ─────────────────────────────────────

    @staticmethod
    async def conclude_reflection(
        session_state: dict,
        ai: AIService,
        profile_data: dict | None = None,
    ) -> dict:
        """Conclude a reflection session: generate summary, extract insights, compute shifts.

        Returns the final reflection summary + spectrum shift recommendations.
        """
        answers = session_state.get("answers", [])
        if not answers:
            return {"error": "No answers to conclude from", "session_state": session_state}

        # Build the reflection transcript for analysis
        transcript_parts = []
        for a in answers:
            transcript_parts.append(f"Q: {a['question_prompt']}")
            transcript_parts.append(f"A: {a['user_answer']}")
            transcript_parts.append(f"AI: {a['ai_followup']}")
            transcript_parts.append("---")

        transcript = "\n".join(transcript_parts)

        # Extract spectrum iteration insights
        profile_summary = "暂无画像信息"
        if profile_data:
            dims = []
            dim_labels = {
                "theory_driven": ("理论驱动", "经验驱动"),
                "methodological_rigidity": ("严谨规范", "灵活探索"),
                "analysis_depth": ("广度优先", "深度优先"),
                "structure_preference": ("结构化", "开放式"),
                "participation_level": ("旁观观察", "深度参与"),
                "tech_dependency": ("低技术", "高技术"),
                "writing_style": ("学术正式", "通俗亲和"),
                "learning_preference": ("示范引导", "自主探索"),
            }
            for dim, (left, right) in dim_labels.items():
                val = profile_data.get(dim)
                if val is not None:
                    dims.append(f"  {dim}（{left}—{right}）: {val}/5")
            if dims:
                profile_summary = "当前光谱位置：\n" + "\n".join(dims)

        insight_messages = [
            {"role": "system", "content": ITERATION_INSIGHT_SYSTEM},
            {"role": "user", "content": f"""## 用户画像
{profile_summary}

## 反思对话记录
{transcript[:3000]}

请提取用户方法论光谱位置的演化洞察。只返回JSON，不要附加解释。"""},
        ]

        try:
            result = await ai.chat(
                insight_messages, temperature=0.2, max_tokens=1024, task="memory_extraction",
            )
            # Try to extract JSON from the response
            result = result.strip()
            # Handle potential markdown code block wrapping
            if result.startswith("```"):
                result = result.split("```")[1]
                if result.startswith("json"):
                    result = result[4:]
            data = json.loads(result)
            insights = data.get("insights", [])
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to parse reflection insights: %s", e)
            insights = []

        # Filter: only keep high-confidence insights
        validated_insights = [
            i for i in insights
            if i.get("confidence", 0) >= 0.6 and abs(i.get("direction", 0)) >= 1
        ]

        # Generate a human-readable summary
        summary_messages = [
            {"role": "system", "content": "你是一个社会学反思总结者。根据用户的反思对话，生成一段200字以内的总结，突出用户的自我发现和方法论成长。使用温暖而专业的语气。"},
            {"role": "user", "content": f"反思主题：{session_state.get('title', '反思')}\n\n{transcript[:2000]}\n\n请生成一段反思总结。"},
        ]
        try:
            summary = await ai.chat(
                summary_messages, temperature=0.5, max_tokens=512, task="summarize",
            )
        except Exception:
            logger.warning("Failed to generate reflection summary, using default", exc_info=True)
            summary = "感谢你的深度反思。每一次反思都是方法论成长的契机。"

        return {
            "summary": summary,
            "insights": validated_insights,
            "total_questions": len(answers),
            "trigger_type": session_state.get("trigger_type", ""),
            "spectrum_shifts": [
                {
                    "dimension": i["dimension"],
                    "current_value": profile_data.get(i["dimension"]) if profile_data else None,
                    "direction": i["direction"],
                    "confidence": i["confidence"],
                    "rationale": i.get("rationale", ""),
                    "evidence": i.get("evidence", ""),
                }
                for i in validated_insights
            ],
            "answers_count": len(answers),
        }

    # ── Memory Integration ───────────────────────────────────────────────────

    @staticmethod
    async def store_reflection_memories(
        conclusion: dict,
        ai: AIService,
        db,
        profile_id: int,
        trigger_type: str = "",
        project_id: int | None = None,
    ) -> int:
        """Turn reflection insights into pending WISE memory proposals.

        AI-derived insights are deliberately not written to long-term memory
        here.  The user must review and approve each proposal through WISE.
        """
        if not conclusion.get("insights"):
            return 0

        # Convert insights into memory format
        memories = []
        for insight in conclusion["insights"]:
            dim_labels = {
                "theory_driven": "理论驱动↔经验驱动",
                "methodological_rigidity": "严谨规范↔灵活探索",
                "analysis_depth": "广度优先↔深度优先",
                "structure_preference": "结构化↔开放式",
                "participation_level": "旁观观察↔深度参与",
                "tech_dependency": "低技术↔高技术",
                "writing_style": "学术正式↔通俗亲和",
                "learning_preference": "示范引导↔自主探索",
            }
            dim_label = dim_labels.get(insight["dimension"], insight["dimension"])
            direction_word = "←" if insight["direction"] < 0 else "→"

            memory = {
                "category": "reflection",
                "key": f"reflect_{insight['dimension']}_{trigger_type}",
                "value": (
                    f"[方法论反思] 用户在{dim_label}维度上出现偏移趋势({direction_word})："
                    f"{insight.get('rationale', '')}"
                ),
                "confidence": insight.get("confidence", 0.7),
                "importance": 4,  # Reflection insights are high importance
            }
            memories.append(memory)

        if memories:
            try:
                saved = await WISEService.create_memory_proposals(
                    db,
                    profile_id,
                    memories,
                    source="reflection",
                    project_id=project_id,
                )
                logger.info("Created %d reflection memory proposals for profile %d", saved, profile_id)
                return saved
            except Exception as e:
                logger.error("Failed to store reflection memories: %s", e)
                return 0
        return 0

    # ── Quick Reflection (lightweight, non-dialogue) ─────────────────────────

    @staticmethod
    async def quick_reflection(
        ai: AIService,
        user_notes: str,
        session_context: str = "",
    ) -> str:
        """Generate a quick 2-3 sentence reflection based on user's field notes.

        Lightweight mode — no full dialogue, just AI-generated reflection text.
        Suitable for mobile or when the user wants a fast reflection.
        """
        messages = [
            {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"""## 调查背景
{session_context[:1000]}

## 用户笔记
{user_notes}

{QUICK_REFLECTION_PROMPT}"""},
        ]
        try:
            result = await ai.chat(messages, temperature=0.5, max_tokens=512, task="hints")
            return result
        except Exception as e:
            logger.error("Quick reflection failed: %s", e)
            return "反思生成失败，请稍后重试。"

    # ── Profile Iteration Application ────────────────────────────────────────

    @staticmethod
    def compute_profile_adjustments(
        insights: list[dict],
        current_spectrum: dict[str, int],
        stability: float = 0.7,
    ) -> dict:
        """Compute profile spectrum adjustments from reflection insights.

        Args:
            insights: list of validated reflection insights
            current_spectrum: dict of dimension → current value (1-5)
            stability: how resistant the profile is to change (0-1, higher = more stable)

        Returns:
            dict with recommended new values and adjustment metadata
        """
        adjustments = {}
        for insight in insights:
            dim = insight.get("dimension", "")
            if dim not in current_spectrum:
                continue

            direction = insight.get("direction", 0)
            confidence = insight.get("confidence", 0.0)
            current = current_spectrum[dim]

            # Compute adjustment magnitude: direction * confidence * (1 - stability)
            # stability=0.7 means only 30% of the insight's force is applied per reflection
            magnitude = direction * confidence * (1.0 - stability)

            # Apply adjustment with clamping to 1-5
            new_value = round(current + magnitude)
            new_value = max(1, min(5, new_value))

            # Only record if there's a meaningful change
            if new_value != current:
                adjustments[dim] = {
                    "current": current,
                    "recommended": new_value,
                    "direction": direction,
                    "confidence": confidence,
                    "magnitude": round(magnitude, 2),
                    "rationale": insight.get("rationale", ""),
                }

        return adjustments
