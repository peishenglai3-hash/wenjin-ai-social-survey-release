"""API v1 router — aggregates all sub-routers for the 5-phase social survey workflow.

Authentication model:
  - api_router (public):     auth endpoints only (login, register, CAPTCHA, refresh)
  - protected_api_router:    ALL other endpoints require a valid JWT Bearer token
"""

from fastapi import APIRouter, Depends

from app.api.deps_auth import require_user
from app.api.v1.router_analysis import router as analysis_router
from app.api.v1.router_analytics import router as analytics_router
from app.api.v1.router_auth import router as auth_router
from app.api.v1.router_export import router as export_router
from app.api.v1.router_fieldwork import router as fieldwork_router
from app.api.v1.router_image import router as image_router
from app.api.v1.router_library import router as library_router
from app.api.v1.router_profile import router as profile_router
from app.api.v1.router_settings import router as settings_router
from app.api.v1.router_coding import router as coding_router
from app.api.v1.router_community import router as community_router
from app.api.v1.router_copilot import router as copilot_router
from app.api.v1.router_dashboard import router as dashboard_router
from app.api.v1.router_knowledge import router as knowledge_router
from app.api.v1.router_memory import router as memory_router, router_skills as memory_skills_router
from app.api.v1.router_monitor import router as monitor_router
from app.api.v1.router_reflection import router as reflection_router
from app.api.v1.router_admin import router as admin_router
from app.api.v1.router_literature import router as literature_router
from app.api.v1.router_methodology import router as methodology_router
from app.api.v1.router_reminders import router as reminders_router
from app.api.v1.router_scenarios import router as scenarios_router, public_router as scenarios_public_router
from app.api.v1.router_skills import router as skills_router
from app.api.v1.router_topic import router as topic_router
from app.api.v1.router_questionnaire import router as questionnaire_router
from app.api.v1.router_open_api import router as open_api_router
from app.api.v1.router_collaboration import router as collaboration_router
from app.api.v1.router_wise import router as wise_router
from app.skills.fieldwork_coach import FieldworkCoachSkill
from app.skills.image_analysis import ImageAnalysisSkill
from app.skills.literature_review import LiteratureReviewSkill
from app.skills.quantitative_analysis import QuantitativeAnalysisSkill
from app.skills.qualitative_coding import QualitativeCodingSkill
from app.skills.questionnaire import QuestionnaireSkill
from app.skills.registry import skill_registry
from app.skills.report_generator import ReportGeneratorSkill
from app.skills.sampling_design import SamplingDesignSkill
from app.skills.topic_argumentation import TopicArgumentationSkill
from app.skills.transcript_analysis import TranscriptAnalysisSkill
from app.skills.reference_membrane import ReferenceMembraneSkill

# Register all skills on startup
skill_registry.register(QuestionnaireSkill())
skill_registry.register(TopicArgumentationSkill())
skill_registry.register(FieldworkCoachSkill())
skill_registry.register(TranscriptAnalysisSkill())
skill_registry.register(QuantitativeAnalysisSkill())
skill_registry.register(ReportGeneratorSkill())
skill_registry.register(LiteratureReviewSkill())
skill_registry.register(SamplingDesignSkill())
skill_registry.register(ImageAnalysisSkill())
skill_registry.register(ReferenceMembraneSkill())
skill_registry.register(QualitativeCodingSkill())

# ── Public router: auth-only (no dependency) ─────────────────────────
api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(scenarios_public_router)
api_router.include_router(analytics_router)  # POST /events is public; GET /stats has require_admin
api_router.include_router(admin_router)      # self-protected with require_admin per-endpoint

# ── Protected router: ALL other endpoints require JWT authentication ─
protected_api_router = APIRouter(dependencies=[Depends(require_user)])
protected_api_router.include_router(community_router)
protected_api_router.include_router(coding_router)
protected_api_router.include_router(copilot_router)
protected_api_router.include_router(dashboard_router)
protected_api_router.include_router(knowledge_router)
protected_api_router.include_router(profile_router)
protected_api_router.include_router(topic_router)
protected_api_router.include_router(questionnaire_router)
protected_api_router.include_router(open_api_router)
protected_api_router.include_router(collaboration_router)
protected_api_router.include_router(wise_router)
protected_api_router.include_router(fieldwork_router)
protected_api_router.include_router(image_router)
protected_api_router.include_router(analysis_router)
protected_api_router.include_router(export_router)
protected_api_router.include_router(library_router)
protected_api_router.include_router(literature_router)
protected_api_router.include_router(methodology_router)
protected_api_router.include_router(scenarios_router)
protected_api_router.include_router(settings_router)
protected_api_router.include_router(skills_router)
protected_api_router.include_router(memory_router)
protected_api_router.include_router(memory_skills_router)
protected_api_router.include_router(monitor_router)
protected_api_router.include_router(reflection_router)
protected_api_router.include_router(reminders_router)
