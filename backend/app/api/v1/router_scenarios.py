"""Scene Design Workshop — preset templates + AI-powered scenario customisation.

The Scenario Workshop helps researchers plan their fieldwork by providing:
1. 12 preset scenario templates (community, rural, school, hospital, etc.)
2. AI-powered custom scenario design wizard (5-8 questions → full blueprint)
3. Save/load scenario designs
"""

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_db
from app.api.deps_auth import require_user, get_current_profile
from app.models.user import UserAccount
from app.services.ai import AIService
from app.models.survey import ScenarioDesign, UserProfile
from app.skills.mode_prompts import ACADEMIC_SYSTEM, GOVERNMENT_SYSTEM, YOUTH_SYSTEM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

# ── 12 preset scenario templates ─────────────────────────────────────

PRESET_SCENARIOS = [
    {
        "id": "community_interview", "name": "社区访谈", "icon": "🏘",
        "category": "community", "description": "在城市社区中进行入户或街头访谈",
        "features": ["面对面深度访谈", "半结构化问卷", "社区观察日志"],
        "suitable_methods": ["半结构化访谈", "参与观察", "焦点小组"],
        "common_pitfalls": [
            "受访者戒备心理强，需要社区干部引荐",
            "访谈时间难以控制（老人爱聊天，上班族时间紧）",
            "录音设备的使用需要提前说明并获得同意",
        ],
        "ethical_notes": "需获口头知情同意；敏感话题（收入、家庭矛盾）需特别注意措辞",
        "recommended_tools": "手机录音 + 笔记本 + 社区地图",
    },
    {
        "id": "rural_fieldwork", "name": "乡村田野", "icon": "🌾",
        "category": "rural", "description": "在农村地区进行驻点式田野调查",
        "features": ["长期驻点观察", "田间地头访谈", "村级档案查阅"],
        "suitable_methods": ["参与观察", "口述史", "焦点小组", "PRA参与式农村评估"],
        "common_pitfalls": [
            "语言/方言障碍，需要当地翻译协助",
            "村民对外来者持谨慎态度，需建立信任关系",
            "交通和住宿条件有限，需提前规划后勤",
        ],
        "ethical_notes": "注意保护村民隐私；避免'猎奇式'研究；研究成果应回馈社区",
        "recommended_tools": "田野笔记 + 录音笔 + 相机 + GPS定位",
    },
    {
        "id": "school_research", "name": "学校调研", "icon": "🏫",
        "category": "education", "description": "在大中小学进行教育相关调研",
        "features": ["课堂观察", "师生访谈", "问卷调查"],
        "suitable_methods": ["问卷调查", "焦点小组", "课堂观察量表"],
        "common_pitfalls": [
            "需获学校管理层和教育局批准",
            "未成年人研究需家长知情同意",
            "考试期间无法开展调研",
        ],
        "ethical_notes": "未成年人保护是首要考量；研究结果不对学生进行个体评价",
        "recommended_tools": "匿名问卷 + 课堂观察记录表 + 录音笔",
    },
    {
        "id": "hospital_research", "name": "医疗机构调研", "icon": "🏥",
        "category": "healthcare", "description": "在医院、社区卫生中心进行医疗健康相关调研",
        "features": ["医患访谈", "服务流程追踪", "病历数据分析"],
        "suitable_methods": ["深度访谈", "追踪调查", "二手数据分析"],
        "common_pitfalls": [
            "涉及患者隐私，需通过伦理审查",
            "医护人员工作繁忙，访谈时间难以安排",
            "医疗场景下的情绪敏感性",
        ],
        "ethical_notes": "必须通过机构伦理审查委员会（IRB）审批；严格遵守个人信息保护法规",
        "recommended_tools": "结构化访谈提纲 + 录音笔 + 观察日志",
    },
    {
        "id": "enterprise_research", "name": "企业调研", "icon": "🏢",
        "category": "enterprise", "description": "在企业/工厂进行组织社会学或劳动关系调研",
        "features": ["管理者访谈", "员工焦点小组", "制度文件分析"],
        "suitable_methods": ["半结构化访谈", "问卷调查", "文档分析"],
        "common_pitfalls": [
            "企业可能限制敏感信息的披露",
            "管理者和一线员工的视角差异需要分别处理",
            "商业机密保护",
        ],
        "ethical_notes": "注意保护商业秘密；确保员工匿名性（避免管理者追溯言论来源）",
        "recommended_tools": "访谈提纲 + 匿名问卷 + 企业档案分析表",
    },
    {
        "id": "government_research", "name": "政府机关调研", "icon": "🏛",
        "category": "government", "description": "在党政机关、事业单位进行政策执行或治理调研",
        "features": ["干部访谈", "政策文件分析", "工作流程追踪"],
        "suitable_methods": ["深度访谈", "政策文本分析", "案例研究"],
        "common_pitfalls": [
            "需要正式的调研函和单位介绍信",
            "受访者可能按'标准答案'回应敏感问题",
            "数据的保密级别要求",
        ],
        "ethical_notes": "严格遵守保密规定；不记录涉密信息；研究成果需经对方审核",
        "recommended_tools": "正式函件 + 结构化访谈提纲 + 政策文件清单",
    },
    {
        "id": "online_survey", "name": "在线调查", "icon": "💻",
        "category": "online", "description": "通过网络平台进行问卷调查或线上访谈",
        "features": ["在线问卷分发", "视频/语音远程访谈", "社交媒体数据采集"],
        "suitable_methods": ["在线问卷调查", "视频访谈", "网络民族志"],
        "common_pitfalls": [
            "样本代表性不足（数字鸿沟）",
            "受访者注意力不集中，问卷质量低",
            "网络环境不稳定影响视频访谈质量",
        ],
        "ethical_notes": "在线知情同意书的有效性；数据存储安全（云端服务器位置）",
        "recommended_tools": "问卷星/腾讯问卷 + Zoom/腾讯会议 + 云存储",
    },
    {
        "id": "street_interview", "name": "街头拦截访谈", "icon": "🚶",
        "category": "public", "description": "在公共场所进行随机拦截式短访谈",
        "features": ["随机抽样", "3-5分钟短访谈", "多地点覆盖"],
        "suitable_methods": ["结构化短问卷", "拦截访谈", "行为观察"],
        "common_pitfalls": [
            "拒访率高，需大量尝试",
            "时间和地点对样本有显著影响",
            "户外环境嘈杂影响录音质量",
        ],
        "ethical_notes": "公共场所摄影需注意肖像权；明确告知研究用途",
        "recommended_tools": "手持平板问卷 + 便携录音设备 + 小礼品",
    },
    {
        "id": "migrant_community", "name": "流动人口社区调研", "icon": "🧳",
        "category": "migrant", "description": "在城中村、工地、流动人口聚集地进行调研",
        "features": ["信任建立是关键", "灵活的时间安排", "非正式访谈为主"],
        "suitable_methods": ["非结构化访谈", "参与观察", "关键人物访谈"],
        "common_pitfalls": [
            "受访者流动性大，难以追踪",
            "身份证件/合法性问题可能使受访者回避",
            "居住条件差，需要在受访者方便的地方进行",
        ],
        "ethical_notes": "特别注意保护弱势群体隐私；不询问移民/户籍状态等敏感问题；适当提供报酬",
        "recommended_tools": "手机便签 + 小额感谢费 + 社区关键人物联系方式",
    },
    {
        "id": "elite_interview", "name": "精英/专家访谈", "icon": "👔",
        "category": "elite", "description": "对政府官员、企业高管、专家学者进行深度访谈",
        "features": ["正式邀约", "办公室/会议室访谈", "专业议题讨论"],
        "suitable_methods": ["精英访谈法", "半结构化深度访谈", "职业史访谈"],
        "common_pitfalls": [
            "预约困难，可能多次改期",
            "受访者有较强的印象管理意识",
            "时间严格限制（通常30-60分钟）",
        ],
        "ethical_notes": "明确引用规则（可署名/匿名/化名）；提前发送访谈提纲",
        "recommended_tools": "专业录音设备 + 正式访谈提纲 + 感谢函",
    },
    {
        "id": "focus_group", "name": "焦点小组", "icon": "👥",
        "category": "group", "description": "组织6-10人的小组讨论，收集集体层面的观点互动",
        "features": ["小组互动讨论", "主持人引导", "多角度碰撞"],
        "suitable_methods": ["焦点小组法", "名义小组技术", "德尔菲法"],
        "common_pitfalls": [
            "个别参与者主导讨论",
            "群体压力和从众效应",
            "录音转录工作量巨大",
        ],
        "ethical_notes": "确保每位参与者都有发言机会；组内保密协议的说明",
        "recommended_tools": "专业录音设备 + 白板/便利贴 + 讨论提纲 + 观察员记录表",
    },
    {
        "id": "archival_research", "name": "档案/文献研究", "icon": "📜",
        "category": "archive", "description": "在档案馆、图书馆进行历史文献和二手资料研究",
        "features": ["档案查阅", "历史文献分析", "二手数据整理"],
        "suitable_methods": ["历史文献法", "内容分析", "二手数据分析"],
        "common_pitfalls": [
            "档案获取权限限制",
            "文献完整性和真实性问题",
            "孤证不立——需要多方印证",
        ],
        "ethical_notes": "遵守档案馆使用规定；引用文献注明出处；不泄露未公开档案内容",
        "recommended_tools": "高清相机/扫描仪 + 文献管理软件 + 档案分析框架",
    },
]


# ── Public read-only endpoints (no auth required) ────────────────────
public_router = APIRouter(prefix="/scenarios", tags=["scenarios-public"])


@public_router.get("/templates")
async def get_scenario_templates():
    """Return all 12 preset scenario templates."""
    return {"scenarios": PRESET_SCENARIOS, "count": len(PRESET_SCENARIOS)}


@public_router.get("/templates/{scenario_id}")
async def get_scenario_template(scenario_id: str):
    for s in PRESET_SCENARIOS:
        if s["id"] == scenario_id:
            return s
    return {"error": "Scenario not found"}


@router.post("/design/stream")
async def design_scenario_stream(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    ai: AIService = Depends(get_ai_service),
):
    """AI-powered scenario design — streaming SSE response."""
    answers = payload.get("answers", {})
    theme = payload.get("theme", "academic")

    theme_systems = {"academic": ACADEMIC_SYSTEM, "government": GOVERNMENT_SYSTEM, "youth": YOUTH_SYSTEM}
    theme_system = theme_systems.get(theme, ACADEMIC_SYSTEM)
    user_context = "\n".join(f"- {k}: {v}" for k, v in answers.items())

    prompt = (
        f"{theme_system}\n\n"
        f"用户正在规划一次社会调查的场景方案。以下是用户的需求信息：\n\n"
        f"{user_context}\n\n"
        "请为这位用户生成一份完整的场景方案，包括：\n\n"
        "## 1. 场景概述\n（用200字概括这个调查场景的核心特征和关键挑战）\n\n"
        "## 2. 推荐方法组合\n（推荐2-3种最合适的方法，说明每种方法的理由和操作要点）\n\n"
        "## 3. 访谈提纲框架\n（提供5-8个核心访谈问题/主题，按逻辑顺序排列）\n\n"
        "## 4. 常见陷阱与应对\n（列出3-5个该场景下最常见的错误和预防策略）\n\n"
        "## 5. 伦理注意事项\n（针对该场景的特殊伦理考量）\n\n"
        "## 6. 推荐工具清单\n（硬件、软件、文档模板等）\n\n"
        "## 7. 时间与资源估算\n（预估所需时间、人员、经费范围）\n\n"
        "用中文输出，Markdown格式。语气专业但可读性强。"
    )

    messages = [
        {"role": "system", "content": "你是一位资深社会调查方法学家，擅长为不同场景设计调查方案。"},
        {"role": "user", "content": prompt},
    ]

    async def event_stream():
        full = []
        try:
            async for token in ai.chat_stream(messages, temperature=0.7, max_tokens=8192, task="guidance"):
                full.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("Scenario design stream error")
            yield f"data: {json.dumps({'error': 'Scenario design failed'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/design")
async def design_scenario(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    ai: AIService = Depends(get_ai_service),
):
    """Non-streaming scenario design."""
    answers = payload.get("answers", {})
    theme = payload.get("theme", "academic")
    theme_systems = {"academic": ACADEMIC_SYSTEM, "government": GOVERNMENT_SYSTEM, "youth": YOUTH_SYSTEM}
    user_context = "\n".join(f"- {k}: {v}" for k, v in answers.items())
    prompt = (
        f"{theme_systems.get(theme, ACADEMIC_SYSTEM)}\n\n"
        f"用户正在规划一次社会调查的场景方案。用户需求：\n\n{user_context}\n\n"
        "请生成完整的场景方案（场景概述、推荐方法、访谈提纲、常见陷阱、"
        "伦理注意、工具清单、时间资源估算）。中文Markdown格式。"
    )
    messages = [
        {"role": "system", "content": "你是一位资深社会调查方法学家。"},
        {"role": "user", "content": prompt},
    ]
    result = await ai.chat(messages, temperature=0.7, max_tokens=8192, task="guidance")
    return {"design": result}


@router.post("/save")
async def save_scenario_design(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    design = ScenarioDesign(
        profile_id=profile.id,
        name=payload.get("name", "未命名场景"),
        scenario_type=payload.get("scenario_type", "custom"),
        description=payload.get("description", ""),
        location_context=payload.get("location_context", ""),
        method_recommendations=payload.get("method_recommendations", ""),
        pitfalls=payload.get("pitfalls", ""),
        ethical_notes=payload.get("ethical_notes", ""),
        tool_recommendations=payload.get("tool_recommendations", ""),
        interview_guide=payload.get("interview_guide", ""),
        full_output=payload.get("full_output", ""),
    )
    db.add(design)
    await db.commit()
    await db.refresh(design)
    return {"id": design.id, "name": design.name}


@router.get("/saved")
async def list_saved_scenarios(
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(ScenarioDesign).where(ScenarioDesign.profile_id == profile.id)
        .order_by(ScenarioDesign.id.desc()).limit(20)
    )
    return {
        "scenarios": [
            {"id": d.id, "name": d.name, "scenario_type": d.scenario_type,
             "description": d.description[:200] if d.description else ""}
            for d in rows.scalars().all()
        ]
    }


@router.get("/saved/{design_id}")
async def get_saved_scenario(
    design_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    row = await db.execute(
        select(ScenarioDesign).where(
            ScenarioDesign.id == design_id,
            ScenarioDesign.profile_id == profile.id,
        )
    )
    d = row.scalar_one_or_none()
    if not d:
        return {"error": "Scenario design not found"}
    return {
        "id": d.id, "name": d.name, "scenario_type": d.scenario_type,
        "description": d.description, "location_context": d.location_context,
        "method_recommendations": d.method_recommendations, "pitfalls": d.pitfalls,
        "ethical_notes": d.ethical_notes, "tool_recommendations": d.tool_recommendations,
        "interview_guide": d.interview_guide, "full_output": d.full_output,
    }
