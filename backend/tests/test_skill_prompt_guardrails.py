"""Every built-in skill prompt carries the evidence and privacy contract."""

from app.skills.fieldwork_coach import FieldworkCoachSkill
from app.skills.image_analysis import ImageAnalysisSkill
from app.skills.literature_review import LiteratureReviewSkill
from app.skills.qualitative_coding import QualitativeCodingSkill
from app.skills.quantitative_analysis import QuantitativeAnalysisSkill
from app.skills.questionnaire import QuestionnaireSkill
from app.skills.reference_membrane import ReferenceMembraneSkill
from app.skills.report_generator import ReportGeneratorSkill
from app.skills.sampling_design import SamplingDesignSkill
from app.skills.topic_argumentation import TopicArgumentationSkill
from app.skills.transcript_analysis import TranscriptAnalysisSkill


def test_builtin_prompts_share_research_evidence_and_privacy_guardrails():
    skills = (
        FieldworkCoachSkill(),
        ImageAnalysisSkill(),
        LiteratureReviewSkill(),
        QualitativeCodingSkill(),
        QuantitativeAnalysisSkill(),
        QuestionnaireSkill(),
        ReferenceMembraneSkill(),
        ReportGeneratorSkill(),
        SamplingDesignSkill(),
        TopicArgumentationSkill(),
        TranscriptAnalysisSkill(),
    )
    for skill in skills:
        prompt = skill.system_prompt()
        assert "不编造文献、法规、统计数字" in prompt
        assert "知情同意" in prompt
        assert "不自动替代伦理审查" in prompt
