"""Tests for ReflectionService — sociological reflexivity engine.

Covers:
  - Trigger listing and validation
  - Session start (intro generation)
  - Answer processing and question progression
  - Session conclusion with insight extraction
  - Quick reflection mode
  - Spectrum adjustment computation
  - Memory integration
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from app.services.reflection_service import (
    ReflectionService, ReflectionSession, IterationInsight,
    REFLECTION_TRIGGERS, REFLECTION_SYSTEM_PROMPT,
    ITERATION_INSIGHT_SYSTEM, QUICK_REFLECTION_PROMPT,
)


class TestTriggerListing:
    """Validate available reflection triggers."""

    def test_list_triggers_returns_all_types(self):
        triggers = ReflectionService.list_triggers()
        assert len(triggers) >= 3
        trigger_ids = [t["id"] for t in triggers]
        assert "fieldwork_completed" in trigger_ids
        assert "analysis_completed" in trigger_ids
        assert "project_completed" in trigger_ids

    def test_get_trigger_returns_valid_config(self):
        trigger = ReflectionService.get_trigger("fieldwork_completed")
        assert trigger is not None
        assert trigger["title"] == "田野调查完成反思"
        assert len(trigger["questions"]) == 4

    def test_get_trigger_returns_none_for_unknown(self):
        assert ReflectionService.get_trigger("unknown_event") is None

    def test_every_trigger_has_required_fields(self):
        for tid, trigger in REFLECTION_TRIGGERS.items():
            assert "title" in trigger, f"{tid} missing title"
            assert "intro" in trigger, f"{tid} missing intro"
            assert "questions" in trigger, f"{tid} missing questions"
            assert len(trigger["questions"]) >= 2, f"{tid} has too few questions"
            for q in trigger["questions"]:
                assert "id" in q
                assert "prompt" in q
                assert "tradition" in q
                assert "spectrum_touch" in q


class TestSessionStart:
    """Start reflection sessions with AI-generated intro."""

    @pytest.mark.asyncio
    async def test_start_returns_session_state(self):
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value="欢迎你进行这次反思，让我们开始吧。")

        state = await ReflectionService.start_reflection(
            trigger_type="fieldwork_completed",
            ai=ai,
            profile_data={"role": "undergraduate"},
            project_data={"title": "测试项目", "research_direction": "社区治理"},
        )

        assert state["trigger_type"] == "fieldwork_completed"
        assert state["title"] == "田野调查完成反思"
        assert "欢迎" in state["intro"]
        assert len(state["questions"]) <= 3  # DEFAULT_QUESTIONS_PER_SESSION
        assert state["current_question_index"] == 0
        assert state["answers"] == []

    @pytest.mark.asyncio
    async def test_start_unknown_trigger_returns_error(self):
        ai = AsyncMock()
        state = await ReflectionService.start_reflection(
            trigger_type="nonexistent",
            ai=ai,
        )
        assert "error" in state
        assert "available" in state

    @pytest.mark.asyncio
    async def test_start_falls_back_to_default_intro_on_ai_error(self):
        ai = AsyncMock()
        ai.chat = AsyncMock(side_effect=Exception("API error"))

        state = await ReflectionService.start_reflection(
            trigger_type="fieldwork_completed",
            ai=ai,
        )
        assert state["intro"] == REFLECTION_TRIGGERS["fieldwork_completed"]["intro"]


class TestAnswerProcessing:
    """Process user answers and generate AI follow-ups."""

    @pytest.mark.asyncio
    async def test_process_answer_advances_question(self):
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value="谢谢你的反思。你的经验反映了常人方法学的核心见解。")

        state = {
            "trigger_type": "fieldwork_completed",
            "title": "测试反思",
            "intro": "让我们开始反思",
            "questions": [
                {"id": "q1", "prompt": "第一问", "tradition": "ethnomethodology", "spectrum_touch": "structure_preference"},
                {"id": "q2", "prompt": "第二问", "tradition": "pragmatism", "spectrum_touch": "theory_driven"},
                {"id": "q3", "prompt": "第三问", "tradition": "bourdieu", "spectrum_touch": "participation_level"},
            ],
            "current_question_index": 0,
            "answers": [],
        }

        updated = await ReflectionService.process_answer(
            session_state=state,
            user_answer="受访者提到了我完全没想到的话题",
            ai=ai,
        )

        assert updated["current_question_index"] == 1
        assert not updated["completed"]
        assert updated["next_question"] is not None
        assert updated["next_question"]["id"] == "q2"
        assert len(updated["answers"]) == 1
        assert updated["answers"][0]["question_id"] == "q1"
        assert updated["answers"][0]["user_answer"] == "受访者提到了我完全没想到的话题"
        assert updated["answers"][0]["tradition"] == "ethnomethodology"

    @pytest.mark.asyncio
    async def test_process_answer_completes_on_last_question(self):
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value="很棒的反思。你的方法论意识正在成长。")

        state = {
            "trigger_type": "fieldwork_completed",
            "title": "测试反思",
            "intro": "开始",
            "questions": [
                {"id": "q1", "prompt": "第一问", "tradition": "ethnomethodology", "spectrum_touch": "structure_preference"},
            ],
            "current_question_index": 0,
            "answers": [],
        }

        updated = await ReflectionService.process_answer(
            session_state=state,
            user_answer="我反思了很多",
            ai=ai,
        )

        assert updated["completed"]
        assert updated["next_question"] is None

    @pytest.mark.asyncio
    async def test_process_answer_handles_ai_error_gracefully(self):
        ai = AsyncMock()
        ai.chat = AsyncMock(side_effect=Exception("timeout"))

        state = {
            "trigger_type": "fieldwork_completed",
            "title": "测试反思",
            "intro": "开始",
            "questions": [
                {"id": "q1", "prompt": "第一问", "tradition": "ethnomethodology", "spectrum_touch": "structure_preference"},
                {"id": "q2", "prompt": "第二问", "tradition": "pragmatism", "spectrum_touch": "theory_driven"},
            ],
            "current_question_index": 0,
            "answers": [],
        }

        updated = await ReflectionService.process_answer(
            session_state=state,
            user_answer="测试回答",
            ai=ai,
        )
        # Should continue despite AI error
        assert updated["current_question_index"] >= 1
        assert len(updated["answers"]) == 1

    @pytest.mark.asyncio
    async def test_process_past_end_marks_completed(self):
        ai = AsyncMock()
        state = {
            "trigger_type": "fieldwork_completed", "title": "T", "intro": "I",
            "questions": [], "current_question_index": 0, "answers": [],
        }
        updated = await ReflectionService.process_answer(state, "answer", ai)
        assert updated.get("completed")


class TestSessionConclusion:
    """Conclude sessions and extract insights."""

    @pytest.mark.asyncio
    async def test_conclude_extracts_valid_json_insights(self):
        ai = AsyncMock()
        ai.chat = AsyncMock(side_effect=[
            # First call: insight extraction
            '{"insights": [{"dimension": "theory_driven", "direction": 1, "confidence": 0.8, "rationale": "用户发现经验观察更有价值", "evidence": "用户说...实践中发现理论不够用"}]}',
            # Second call: summary generation
            "这是一次非常有价值的反思。",
        ])

        state = {
            "trigger_type": "fieldwork_completed",
            "title": "田野反思",
            "answers": [
                {
                    "question_id": "q1",
                    "question_prompt": "第一问",
                    "user_answer": "我发现实践中的经验比理论更复杂",
                    "ai_followup": "你的发现很有意义",
                    "tradition": "ethnomethodology",
                    "spectrum_touch": "theory_driven",
                },
            ],
        }

        conclusion = await ReflectionService.conclude_reflection(
            session_state=state,
            ai=ai,
            profile_data={"theory_driven": 3},
        )

        assert "summary" in conclusion
        assert len(conclusion["insights"]) >= 1
        assert conclusion["insights"][0]["dimension"] == "theory_driven"
        assert conclusion["insights"][0]["direction"] == 1
        assert conclusion["insights"][0]["confidence"] >= 0.6

    @pytest.mark.asyncio
    async def test_conclude_filters_low_confidence_insights(self):
        ai = AsyncMock()
        ai.chat = AsyncMock(side_effect=[
            '{"insights": [{"dimension": "a", "direction": 1, "confidence": 0.4, "rationale": "x", "evidence": "y"}]}',
            "总结文本",
        ])

        state = {
            "trigger_type": "fieldwork_completed",
            "title": "测试",
            "answers": [{"question_id": "q1", "question_prompt": "Q", "user_answer": "A", "ai_followup": "F", "tradition": "e", "spectrum_touch": "t"}],
        }

        conclusion = await ReflectionService.conclude_reflection(state, ai)
        # Low confidence (<0.6) should be filtered out
        assert len(conclusion["insights"]) == 0

    @pytest.mark.asyncio
    async def test_conclude_no_answers_returns_error(self):
        ai = AsyncMock()
        state = {"trigger_type": "fieldwork_completed", "title": "测试", "answers": []}
        conclusion = await ReflectionService.conclude_reflection(state, ai)
        assert "error" in conclusion

    @pytest.mark.asyncio
    async def test_conclude_handles_malformed_json(self):
        ai = AsyncMock()
        ai.chat = AsyncMock(side_effect=[
            "not valid json!!!",  # Will cause JSON parse error
            "总结文本",
        ])

        state = {
            "trigger_type": "fieldwork_completed",
            "title": "测试",
            "answers": [{"question_id": "q1", "question_prompt": "Q", "user_answer": "A", "ai_followup": "F", "tradition": "e", "spectrum_touch": "t"}],
        }

        conclusion = await ReflectionService.conclude_reflection(state, ai)
        assert conclusion["insights"] == []  # Graceful fallback
        assert "summary" in conclusion  # Summary still generated


class TestQuickReflection:
    """Lightweight one-shot reflection mode."""

    @pytest.mark.asyncio
    async def test_quick_reflection_returns_text(self):
        ai = AsyncMock()
        ai.chat = AsyncMock(return_value="一个意外：受访者比我预期的更开放...")

        result = await ReflectionService.quick_reflection(
            ai=ai,
            user_notes="今天的访谈中，受访者提到了很多我没想到的话题",
            session_context="社区治理访谈，时长约45分钟",
        )

        assert isinstance(result, str)
        assert len(result) > 10

    @pytest.mark.asyncio
    async def test_quick_reflection_handles_error(self):
        ai = AsyncMock()
        ai.chat = AsyncMock(side_effect=Exception("API down"))

        result = await ReflectionService.quick_reflection(
            ai=ai,
            user_notes="今天的观察",
        )
        assert "失败" in result  # Error message fallback


class TestSpectrumComputation:
    """Profile spectrum adjustment computation."""

    def test_compute_adjustments_basic_shift(self):
        insights = [
            {"dimension": "theory_driven", "direction": 2, "confidence": 0.9, "rationale": "强证据显示偏向经验驱动"},
        ]
        current = {"theory_driven": 3, "methodological_rigidity": 3}

        adjustments = ReflectionService.compute_profile_adjustments(
            insights=insights,
            current_spectrum=current,
            stability=0.7,
        )

        assert "theory_driven" in adjustments
        # magnitude = 2 * 0.9 * 0.3 = 0.54, round(3.54) = 4
        assert adjustments["theory_driven"]["recommended"] == 4
        assert adjustments["theory_driven"]["current"] == 3

    def test_compute_adjustments_no_change_for_zero_direction(self):
        insights = [
            {"dimension": "structure_preference", "direction": 0, "confidence": 0.9, "rationale": ""},
        ]
        current = {"structure_preference": 3}

        adjustments = ReflectionService.compute_profile_adjustments(
            insights=insights,
            current_spectrum=current,
            stability=0.7,
        )

        assert len(adjustments) == 0  # No change

    def test_compute_adjustments_clamped_to_bounds(self):
        insights = [
            {"dimension": "learning_preference", "direction": 2, "confidence": 1.0, "rationale": "强"},
        ]
        # Already at max
        current = {"learning_preference": 5}

        adjustments = ReflectionService.compute_profile_adjustments(
            insights=insights,
            current_spectrum=current,
            stability=0.0,  # No stability = full force
        )

        # magnitude = 2 * 1.0 * 1.0 = 2, 5 + 2 = 7 → clamped to 5
        assert "learning_preference" not in adjustments  # No change because clamped back to same

    def test_compute_adjustments_high_stability_resists_change(self):
        insights = [
            {"dimension": "analysis_depth", "direction": 2, "confidence": 0.9, "rationale": ""},
        ]
        current = {"analysis_depth": 3}

        adjustments = ReflectionService.compute_profile_adjustments(
            insights=insights,
            current_spectrum=current,
            stability=0.95,  # Very stable
        )

        # magnitude = 2 * 0.9 * 0.05 = 0.09, round(3.09) = 3, no change
        assert len(adjustments) == 0

    def test_compute_multiple_insights_same_dimension(self):
        insights = [
            {"dimension": "participation_level", "direction": 1, "confidence": 0.8, "rationale": ""},
            {"dimension": "participation_level", "direction": 1, "confidence": 0.7, "rationale": ""},
            {"dimension": "writing_style", "direction": -1, "confidence": 0.9, "rationale": ""},
        ]
        current = {"participation_level": 3, "writing_style": 3, "learning_preference": 3}

        adjustments = ReflectionService.compute_profile_adjustments(
            insights=insights,
            current_spectrum=current,
            stability=0.0,  # Zero stability so adjustments are visible
        )

        assert len(adjustments) >= 1


class TestMemoryIntegration:
    """Memory storage from reflection insights."""

    @pytest.mark.asyncio
    async def test_store_reflection_memories_converts_insights(self):
        from unittest.mock import AsyncMock, patch

        conclusion = {
            "insights": [
                {"dimension": "theory_driven", "direction": 1, "confidence": 0.8,
                 "rationale": "用户逐渐偏向经验驱动", "evidence": "用户说..."},
            ],
            "summary": "总结",
        }

        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()

        # AI-derived insights now become pending WISE proposals first.
        with patch("app.services.reflection_service.WISEService.create_memory_proposals", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = 1
            ai = AsyncMock()
            count = await ReflectionService.store_reflection_memories(
                conclusion=conclusion,
                ai=ai,
                db=db,
                profile_id=1,
                trigger_type="fieldwork_completed",
            )

            assert count == 1
            assert mock_save.called
            # Verify proposal candidates preserve the reflection category.
            call_args = mock_save.call_args
            memories = call_args.args[2]  # Third positional arg: memories list
            assert memories[0]["category"] == "reflection"
            assert "方法论反思" in memories[0]["value"]

    @pytest.mark.asyncio
    async def test_store_reflection_memories_no_insights_returns_zero(self):
        conclusion = {"insights": []}
        ai = AsyncMock()
        db = AsyncMock()
        count = await ReflectionService.store_reflection_memories(
            conclusion=conclusion, ai=ai, db=db, profile_id=1,
        )
        assert count == 0
