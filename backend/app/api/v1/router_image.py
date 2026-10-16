"""Image analysis endpoints — vision AI for fieldwork photos."""

import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_ai_service, get_vision_service
from app.services.ai import AIService, VisionNotSupportedError
from app.skills.registry import skill_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/image", tags=["image"])


@router.post("/analyze")
async def analyze_image(
    payload: dict,
    ai: AIService = Depends(get_ai_service),
    vision_ai: AIService = Depends(get_vision_service),
):
    """Analyze a fieldwork image using multimodal vision AI.

    Accepts:
    - image_base64: base64-encoded JPEG/PNG image
    - image_description: text description (fallback if no base64)
    - research_topic: optional research context
    - field_location: optional location info
    - analysis_focus: general | social_interaction | built_environment | text_ocr | objects | auto

    Falls back to text-only analysis when the AI provider doesn't support vision
    (DeepSeek V4 is text-only — configure a vision model provider for direct image analysis).
    """
    image_b64 = payload.get("image_base64", "")
    image_desc = payload.get("image_description", "")
    research_topic = payload.get("research_topic", "")
    field_location = payload.get("field_location", "")
    analysis_focus = payload.get("analysis_focus", "auto")

    if not image_b64 and not image_desc:
        return {"error": "image_base64 or image_description is required"}

    skill = skill_registry.get("image_analysis")
    if not skill:
        return {"error": "Image analysis skill not registered"}

    user_input = {
        "image_description": image_desc or "[图片已上传，请基于格式和大小元数据进行分析]",
        "research_topic": research_topic,
        "field_location": field_location,
        "analysis_focus": analysis_focus,
    }

    ctx = None
    if image_b64:
        # Pass DeepSeek (ai) as text_ai for fallback if Qwen Vision fails.
        # Qwen text API (qwen-max) has a 30K token limit; DeepSeek has much
        # larger context and won't fail on the full analysis framework prompt.
        ctx = {"image_base64": image_b64, "text_ai": ai}

    # Route to vision provider (Qwen-VL) for images, DeepSeek for text-only fallback
    active_ai = vision_ai if image_b64 else ai
    try:
        result = await skill.execute(active_ai, user_input, context=ctx)
    except Exception:
        logger.exception("Image analysis failed")
        return {"error": "Image analysis failed; please retry later"}

    meta = result.metadata or {}
    return {
        "analysis": result.content,
        "focus": analysis_focus,
        "has_image": bool(image_b64),
        "vision_used": meta.get("vision_used", False),
        "fallback_reason": meta.get("fallback_reason"),
        "image_meta": meta.get("image_meta"),
    }
