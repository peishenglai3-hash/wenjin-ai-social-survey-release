"""Questionnaire design skill — generates structured survey instruments with academic rigor.

v0.3.0 — Enhanced with ISSP/SocioBench scale knowledge, multi-step generation,
structured JSON output for card-based UI, and Chinese sociological context.
"""

import json
import logging
import re

from app.skills.base import BaseSkill, SkillResult

logger = logging.getLogger(__name__)

# ── HTML tag patterns for output cleaning ───────────────────────────────
# LLMs (especially DeepSeek) sometimes emit raw HTML tags mixed with Markdown.
# These patterns strip all HTML/XML tags while preserving Markdown syntax.

_HTML_TAG_RE = re.compile(r"<[^>]*>")  # strip all <tag> forms
_HTML_ENTITY_RE = re.compile(r"&[a-z]+;")  # strip &nbsp; &lt; &amp; etc.
_BR_VARIANTS_RE = re.compile(r"</?\s*(br|p|div|span|html|body|head|meta|link|script|style)\s*/?>", re.IGNORECASE)
_SELF_CLOSING_RE = re.compile(r"<\s*(img|input|hr|meta|link|br)\s+[^>]*/?>", re.IGNORECASE)


def strip_html_tags(text: str) -> str:
    """Aggressively strip HTML/XML tags from AI-generated text.

    Three-pass strategy:
    1. Strip known structural/variable tags (br, p, div, span, etc.)
    2. Strip all remaining <...> patterns (self-closing & attributes)
    3. Decode common HTML entities to plain text
    """
    # Pass 1: known noisy structural tags (case-insensitive, with or without attrs)
    text = _BR_VARIANTS_RE.sub("", text)
    # Pass 2: self-closing tags with attributes (e.g. <img src="..." />)
    text = _SELF_CLOSING_RE.sub("", text)
    # Pass 3: any remaining <...> tag-like patterns
    text = _HTML_TAG_RE.sub("", text)
    # Pass 4: common entities → plain text
    text = text.replace("&nbsp;", " ")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&amp;", "&")
    text = text.replace("&quot;", '"')
    text = text.replace("&apos;", "'")
    # Clean up double spaces and orphan newlines from tag removal
    text = re.sub(r"  +", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

# ── ISSP & Major Social Survey Scale Reference ──────────────────────────
# Curated from SocioBench ISSP modules + Chinese survey instruments
# (CGSS=中国综合社会调查, CFPS=中国家庭追踪调查, WVS=世界价值观调查)

ISSP_SCALE_KNOWLEDGE = """
## 常用社会科学量表知识库 (基于ISSP/SocioBench及中国社会调查实践)

### 社会不平等 (Social Inequality)
| 量表 | 题数 | 信度(α) | 来源 |
|------|------|---------|------|
| 公平世界信念量表 (Belief in a Just World) | 6-8 | 0.80-0.87 | Dalbert 1999; ISSP Inequality |
| 阶层认同量表 (Subjective Social Status) | 3-5 | 0.72-0.78 | ISSP Inequality; CGSS |
| 分配公平感量表 (Distributive Justice) | 6-10 | 0.78-0.84 | ISSP Inequality IV (2009/2019) |
| 社会流动性感知量表 (Perceived Mobility) | 4-6 | 0.70-0.76 | ISSP; CGSS |

### 家庭与性别角色 (Family & Gender Roles)
| 量表 | 题数 | 信度(α) | 来源 |
|------|------|---------|------|
| 性别角色态度量表 (Gender Role Attitudes) | 8-12 | 0.82-0.89 | ISSP Family; CGSS |
| 工作-家庭冲突量表 (Work-Family Conflict) | 5-10 | 0.85-0.90 | Carlson 2000; ISSP Family |
| 婚姻满意度量表 (Marital Satisfaction) | 6-10 | 0.88-0.93 | ENRICH; ISSP |

### 环境态度 (Environmental Attitudes)
| 量表 | 题数 | 信度(α) | 来源 |
|------|------|---------|------|
| 新生态范式量表 (NEP Scale) | 15 | 0.82-0.87 | Dunlap 2000; ISSP Environment |
| 环境行为意向量表 (Pro-Environmental Behavior) | 8-12 | 0.78-0.85 | ISSP Environment 2020 |
| 环境风险感知量表 (Environmental Risk Perception) | 5-8 | 0.75-0.82 | ISSP; CGSS |

### 健康与幸福感 (Health & Well-being)
| 量表 | 题数 | 信度(α) | 来源 |
|------|------|---------|------|
| 自评健康 (Self-Rated Health, SRH) | 1-3 | — | ISSP Health; CGSS; CFPS |
| 主观幸福感量表 (生活满意度SWLS) | 5 | 0.82-0.87 | Diener 1985; ISSP |
| 心理困扰量表 (K6/K10) | 6-10 | 0.85-0.92 | Kessler 2002; ISSP Health |
| 社会支持量表 (Social Support) | 6-12 | 0.80-0.88 | ISSP Social Networks |

### 公民权利与政治参与
| 量表 | 题数 | 信度(α) | 来源 |
|------|------|---------|------|
| 政治效能感量表 (Political Efficacy) | 6-8 | 0.78-0.85 | ISSP Citizenship 2014; CGSS |
| 政治信任量表 (Political Trust) | 5-7 | 0.82-0.88 | ISSP Role of Government; WVS |
| 社会参与度量表 (Civic Engagement) | 8-12 | 0.75-0.82 | ISSP Social Networks; CGSS |

### 宗教与价值观
| 量表 | 题数 | 信度(α) | 来源 |
|------|------|---------|------|
| 宗教虔诚度量表 (Religiosity) | 5-8 | 0.85-0.90 | ISSP Religion; WVS |
| 后物质主义价值观 (Post-Materialism) | 4-12 | 0.65-0.75 | Inglehart; WVS; ISSP |
| 传统-现代价值观 | 8-15 | 0.78-0.85 | WVS; CGSS |

### 工作导向
| 量表 | 题数 | 信度(α) | 来源 |
|------|------|---------|------|
| 工作价值观量表 (Work Values) | 10-16 | 0.78-0.85 | ISSP Work Orientation; WVS |
| 工作满意度 (Job Satisfaction) | 3-6 | 0.80-0.86 | ISSP; CGSS |
| 职业倦怠 (MBI-GS) | 9-16 | 0.85-0.91 | Maslach; ISSP Work |

### 社交网络
| 量表 | 题数 | 信度(α) | 来源 |
|------|------|---------|------|
| 社会资本量表 (Social Capital) | 8-15 | 0.78-0.85 | ISSP Social Networks; CGSS |
| 孤独感量表 (UCLA Loneliness) | 3-8 | 0.82-0.89 | UCLA; ISSP |
| 社会信任量表 (Social Trust) | 3-5 | 0.72-0.78 | ISSP; WVS; CGSS |

### 政府角色与福利态度
| 量表 | 题数 | 信度(α) | 来源 |
|------|------|---------|------|
| 政府责任认知 (Gov't Responsibility) | 6-10 | 0.78-0.84 | ISSP Role of Government |
| 福利态度量表 (Welfare Attitudes) | 5-8 | 0.75-0.82 | ISSP; CGSS |

### 国家认同
| 量表 | 题数 | 信度(α) | 来源 |
|------|------|---------|------|
| 国家认同量表 (National Identity) | 6-10 | 0.80-0.86 | ISSP National Identity; WVS |
| 移民态度量表 (Attitudes toward Immigrants) | 5-8 | 0.78-0.84 | ISSP National Identity |

---
**使用说明**: α>0.80为高信度量表优先推荐。跨文化使用需语境调适。
"""


class QuestionnaireSkill(BaseSkill):
    name = "questionnaire"
    description = "设计结构化问卷：量表推荐、题项生成、信效度保障，支持ISSP/SocioBench学术标准"
    version = "0.3.0"

    def system_prompt(self, context: dict | None = None, experience_level: str = "beginner") -> str:
        ctx_str = str(context) if context else ""

        tier_guide = {
            "beginner": (
                "用户是新手调查者。请提供完整的、可直接使用的问卷方案。"
                "每个题项后附加简短的「设计意图」说明。"
                "在关键方法论决策处，用「💡 小贴士」格式解释原因。"
                "语气温暖、鼓励，多用类比帮助理解。"
                "推荐成熟量表而非自定义题项，降低设计风险。"
            ),
            "intermediate": (
                "用户有一定调查经验。请提供结构化框架和2-3个备选量表/题项。"
                "标注每个推荐的适用条件和优劣。"
                "引导用户在关键决策点做出选择。"
                "提供信效度对比数据。"
            ),
            "advanced": (
                "用户是经验丰富的研究者。请以「同行评议」风格提供方法论审阅。"
                "重点放在：量表选择的对比论证（含效应量）、信效度风险提示、最新文献引用。"
                "提供跨文化调适建议和中国语境常模数据。"
                "简洁直接，减少基础性解释。"
            ),
        }
        tier_text = tier_guide.get(experience_level, tier_guide["beginner"])

        return (
            "你是一位资深的社会调查方法论专家，精通问卷设计与心理测量学。\n"
            "你的任务是根据用户的研究主题，生成一套结构化的问卷方案。\n"
            "你必须严谨、学术，同时根据用户的经验水平调整输出的详细程度。\n\n"
            f"## 用户水平适配\n{tier_text}\n\n"
            + ISSP_SCALE_KNOWLEDGE +
            "\n\n## 输出格式要求（用 Markdown）\n\n"
            "### 1. 核心构念与概念框架\n"
            "列出需要测量的关键变量/构念，使用表格呈现：\n"
            "| 构念 | 理论定义 | 操作化维度 | 预期方向 |\n"
            "|------|----------|-----------|----------|\n\n"
            "### 2. 推荐量表\n"
            "优先从上方的「常用量表知识库」中选择经过验证的量表。每个构念推荐1-3个候选，表格呈现：\n"
            "| 构念 | 推荐量表 | 题数 | 信度(α) | 来源 | 选择理由 |\n"
            "|------|----------|------|---------|------|----------|\n\n"
            "### 3. 完整问卷题项\n"
            "将所有题项整合为一套可直接使用的完整问卷。每道题标注：\n"
            "- **题号**（如 Q1, Q2...）\n"
            "- **题干**（完整表述）\n"
            "- **选项**（标注量表类型，如 5点Likert / 语义差异）\n"
            "- **所属构念**\n"
            "- **反向题标记**（如为反向题，标注 ⚠️R）\n"
            "- **设计意图**（简短说明此题测量什么）\n"
            "使用以下格式：\n"
            "```\n"
            "**Q1** [构念：XX] 题干内容...\n"
            "- 选项 (1) 非常不同意 (2) 不同意 (3) 中立 (4) 同意 (5) 非常同意\n"
            "> 💡 设计意图：此题测量XX维度...\n"
            "```\n\n"
            "### 4. 量表格式总览\n"
            "说明各部分的计分方式、是否需要反向计分、总分/维度分计算方式。\n\n"
            "### 5. 信效度保障策略\n"
            "- 内容效度：专家评审要点\n"
            "- 结构效度：CFA模型和拟合指标阈值 (CFI>0.90, RMSEA<0.08, SRMR<0.08)\n"
            "- 内部一致性：Cronbach's α 各维度目标值 (≥0.70)\n"
            "- 预测试方案：样本量和项目分析标准\n\n"
            "### 6. 实施注意事项\n"
            "- 社会称许性控制（建议加入MCSDS简版2-3题）\n"
            "- 顺序效应（建议的题项随机化策略）\n"
            "- 疲劳效应（合理长度和休息点）\n"
            "- 文化调适（中国语境下的特殊考虑）\n"
            "- 数据质量检查项（注意力检测题、反向题配对验证）\n\n"
            "### 7. 结构化JSON (供系统解析)\n"
            "在报告末尾，输出一个```questionnaire_json 代码块：\n"
            "```questionnaire_json\n"
            "{\n"
            '  "title": "问卷标题",\n'
            '  "constructs": [{"name":"...","definition":"...","dimensions":["..."]}],\n'
            '  "scales": [{"name":"...","source":"...","alpha":0.85,"items_count":6}],\n'
            '  "questions": [\n'
            '    {"id":"Q1","construct":"...","text":"...","options":["...",..."],\n'
            '     "scale_type":"5-point Likert","reversed":false,"intent":"..."}\n'
            '  ],\n'
            '  "total_items": 25,\n'
            '  "estimated_time_minutes": 8,\n'
            '  "attention_checks": 2\n'
            "}\n"
            "```\n\n"
            "---\n"
            "重要提醒：\n"
            "- 问卷总题数控制在20-40题（新手）、15-25题（进阶）、10-20题（专家）\n"
            "- 必须包含至少1道注意力检测题和2道反向题\n"
            "- 优先使用知识库中的成熟量表；量表名称、题项、信效度和版权必须逐项核验，不能把候选提示当作已验证事实\n"
            "- 区分原量表题项、研究者自拟题项和翻译/文化适配题项，并记录版本、来源和许可边界\n\n"
            "## ⚠️ 格式强制规范（必须遵守）\n"
            "- 禁止使用任何HTML标签：不允许出现 `<br>` `<p>` `<div>` `<span>` `<li>` `<ul>` `<ol>` `<table>` 等\n"
            "- 换行请用空行分隔段落，列表请用 Markdown 的 `-` 或 `1.` 语法\n"
            "- 表格请用 Markdown 原生表格语法 `| 列 | 列 |`\n"
            "- 粗体用 `**文字**`，斜体用 `*文字*`\n"
            "- 严禁输出任何 HTML/XML 格式的内容\n"
            f"额外上下文：{ctx_str}"
        )

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "research_topic": {"type": "string", "description": "研究主题"},
                "target_population": {"type": "string", "description": "目标人群"},
                "research_paradigm": {
                    "type": "string",
                    "enum": ["quantitative", "qualitative", "mixed"],
                    "description": "研究范式",
                },
                "experience_level": {
                    "type": "string",
                    "enum": ["beginner", "intermediate", "advanced"],
                    "description": "用户经验水平",
                },
                "existing_scales": {"type": "string", "description": "已知的相关量表（可选）"},
                "step": {
                    "type": "string",
                    "enum": ["full", "concepts", "scales", "questions", "review"],
                    "description": "生成步骤",
                },
            },
            "required": ["research_topic"],
        }

    def match(self, user_intent: str) -> float:
        keywords = [
            "问卷", "量表", "题项", "信效度", "survey", "questionnaire",
            "likert", "测量", "量化", "定量", "scale", "item",
        ]
        intent_lower = user_intent.lower()
        hits = sum(1 for kw in keywords if kw in intent_lower)
        return min(hits / max(len(keywords) * 0.3, 1), 1.0)

    async def execute(self, ai_service, user_input: dict, context: dict | None = None) -> SkillResult:
        topic = user_input.get("research_topic", "")
        population = user_input.get("target_population", "")
        experience = user_input.get("experience_level", "beginner")
        paradigm = user_input.get("research_paradigm", "quantitative")
        existing_scales = user_input.get("existing_scales", "")
        step = user_input.get("step", "full")

        step_instructions = {
            "full": "请按照系统提示的完整框架，输出包含所有7个部分的问卷设计方案。",
            "concepts": "请仅输出「核心构念与概念框架」部分，深入分析每个构念的理论来源和操作化路径。",
            "scales": "请仅输出「推荐量表」部分，为每个构念提供2-3个候选量表，对比信效度和文化适用性。",
            "questions": "请仅输出「完整问卷题项」和「结构化JSON」部分，生成立即可用的完整问卷。",
            "review": "请以方法论审阅模式，仅输出「信效度保障策略」和「实施注意事项」部分。",
        }

        instruction = step_instructions.get(step, step_instructions["full"])

        prompt = (
            f"研究主题：{topic}\n"
            f"目标人群：{population or '未指定'}\n"
            f"研究范式：{paradigm}\n"
            + (f"已知相关量表：{existing_scales}\n" if existing_scales else "")
            + f"\n{instruction}"
        )

        messages = [
            {"role": "system", "content": self.system_prompt(context, experience)},
            {"role": "user", "content": prompt},
        ]

        max_tok = 8192 if step == "full" else 4096
        response = await ai_service.chat(messages, temperature=0.7, max_tokens=max_tok)

        # Strip any HTML artifacts that the LLM may have emitted
        response = strip_html_tags(response)

        # Extract structured JSON if present
        parsed_questions = None
        try:
            json_match = response.split("```questionnaire_json\n")
            if len(json_match) > 1:
                json_str = json_match[1].split("\n```")[0]
                parsed_questions = json.loads(json_str)
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"Failed to parse questionnaire JSON: {e}")

        return SkillResult(
            content=response,
            metadata={"parsed": parsed_questions, "step": step},
        )
