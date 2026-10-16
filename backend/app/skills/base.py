"""Skill abstract base class — each skill = system_prompt + tools + schema."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import wraps


RESEARCH_GUARDRAILS = (
    "\n\n## 社会调查专业与安全边界（所有技能必须遵守）\n"
    "1. 将观察/原始材料、已有证据、合理推断和行动建议分开标注；证据不足时明确说不足。\n"
    "2. 不编造文献、法规、统计数字、样本、受访者经历或量表信效度；无法核验的来源只能作为待核查候选。\n"
    "3. 以研究目的最小化收集身份信息，提醒知情同意、撤回、保留期限和场域风险；不要在输出中重复直接身份信息、凭据或原始敏感材料。\n"
    "4. AI 输出只是研究者可审阅的候选方案、编码、问题或解释，不自动替代伦理审查、代表性判断、最终编码、研究结论或发布决定。\n"
    "5. 明确适用场域、语言/文化限制、潜在偏差和失败条件；跨场域迁移必须由研究者重新核验。"
)


@dataclass
class SkillResult:
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    confidence: "ConfidenceMarker | None" = None


class BaseSkill(ABC):
    """A Skill is a specialized AI capability with its own system prompt,
    optional function-calling tools, and structured input/output schemas.

    The router LLM selects which skill to invoke based on the user's intent
    and the skill's `match` method.
    """

    name: str = ""
    description: str = ""
    version: str = "0.1.0"

    def __init_subclass__(cls, **kwargs):
        """Attach the same evidence/privacy guardrail to every built-in skill."""
        super().__init_subclass__(**kwargs)
        prompt_method = cls.__dict__.get("system_prompt")
        if prompt_method is None or getattr(prompt_method, "_wenjin_guardrailed", False):
            return

        @wraps(prompt_method)
        def guarded_prompt(self, *args, **kwargs):
            return self.with_research_guardrails(prompt_method(self, *args, **kwargs))

        guarded_prompt._wenjin_guardrailed = True
        cls.system_prompt = guarded_prompt

    @staticmethod
    def with_research_guardrails(prompt: str) -> str:
        """Return a prompt with non-optional evidence and privacy constraints."""
        return f"{prompt}{RESEARCH_GUARDRAILS}"

    @abstractmethod
    def system_prompt(self, context: dict | None = None) -> str:
        """Return the system prompt that primes the LLM for this skill."""
        ...

    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema describing the expected input fields."""
        ...

    def tools(self) -> list[dict]:
        """Optional function-calling tool definitions."""
        return []

    def match(self, user_intent: str) -> float:
        """Return a confidence score 0-1 for whether this skill matches the intent.
        Override in subclasses for keyword / semantic matching.
        """
        return 0.0

    async def execute(
        self, ai_service, user_input: dict, context: dict | None = None
    ) -> SkillResult:
        """Default execution: send system_prompt + user_input to the LLM."""
        messages = [
            {"role": "system", "content": self.system_prompt(context)},
            {"role": "user", "content": str(user_input)},
        ]
        response = await ai_service.chat(messages)
        return SkillResult(content=response)

    async def execute_streaming(
        self, ai_service, user_input: dict, context: dict | None = None
    ):
        """Override for streaming responses."""
        raise NotImplementedError
