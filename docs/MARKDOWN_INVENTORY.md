# Markdown 与 README 审核登记

审核日期：2026-10-16。范围是公开 Git 树中全部 Markdown、README 和 `backend/alembic/README`。本登记确认文档已按“专业知识 / 调查赋能 / 隐私安全 / 可复现边界”复核；它不是版权或伦理批准。

| 文件 | 责任主题 | 审核结论 |
| --- | --- | --- |
| `AGENTS.md` | 代理、代码、隐私和发布规则 | 保留；明确稳定核心、密钥、知识和发布闸门 |
| `backend/alembic/README` | 迁移目录说明 | 保留；无部署秘密 |
| `README.md` | 项目入口、BYOK、运行和路线图 | 已更新；明确 Apache-2.0、候选知识、协作 flag 和未完成项 |
| `CHANGELOG.md` | 发布候选变更 | 新增；记录已实现能力与限制 |
| `CONTRIBUTING.md` | 贡献、测试和发布要求 | 新增；禁止秘密、原始研究资料和未审计知识 |
| `SECURITY.md` | 密钥、数据和泄露处置 | 保留并核验；要求供应商侧撤销/轮换 |
| `THIRD_PARTY_NOTICES.md` | 第三方材料和许可证边界 | 保留并核验；排除书籍全文、OCR、切片和内部资料 |
| `SPEC-WENJIN-OPEN-SOURCE-EVOLUTION-V2.md` | 总体规格与验收条件 | 已校准；不把历史测试占位数当作当前证据 |
| `tasks/plan.md` | 分阶段实施计划 | 已脱敏；不暴露本机路径，保留停止条件和回滚规则 |
| `tasks/todo.md` | 逐项实施状态 | 已更新；保留 Docker、lint、版权和人工知识批准等未完成闸门 |
| `docs/README.md` | 文档索引和公开知识边界 | 已更新；链接 prompt/skill 与候选材料登记 |
| `docs/BASELINE-2026-10-16.md` | 历史基线证据 | 保留为冻结基线；不等同于发布批准 |
| `docs/OPEN_SOURCE_EVOLUTION_CAPABILITY_MAP.md` | 能力地图 | 保留；明确能力地图不等于已发布 |
| `docs/OPEN_API.md` | Open API V1、BYOK 和客户端边界 | 已更新；明确部署者配置自己的 key，客户端不接收 provider key |
| `docs/COLLABORATION_V1.md` | 协作权限、产物和实时边界 | 已更新；说明前端最小闭环、默认关闭和非实时限制 |
| `docs/WISE.md` | 提案、审批、撤销和记忆门 | 保留；AI 输出不能自动写长期记忆 |
| `docs/EXTENSION_SECURITY.md` | 社区技能和扩展执行边界 | 保留；当前只允许 prompt-only 声明式技能 |
| `docs/KNOWLEDGE_INGESTION.md` | 私有知识包 manifest 和准入 | 已更新；加入逐卡 bounded shape、语言/场域/方法和注入标记闸门 |
| `docs/KNOWLEDGE_CANDIDATE_REGISTER.md` | 中英文候选材料元数据 | 新增；全部 `needs_review`，不含全文或私人材料 |
| `docs/PROMPT_SKILL_REVIEW.md` | prompt/skill 专业与调查赋能校准 | 新增；统一证据、隐私、场域和 AI 建议性守则 |
| `docs/adr/README.md` | ADR 目录规则 | 保留；要求记录决策、证据、风险和回滚 |
| `docs/adr/0001-server-side-byok.md` | 服务端 BYOK | 保留；key 不进客户端 |
| `docs/adr/0002-collaboration-v1-no-realtime-editing.md` | 协作 V1 非实时 | 保留；不引入共同编辑冲突复杂度 |
| `docs/adr/0003-knowledge-audit-gate.md` | 知识审计闸门 | 保留；独立审计后仍需人工批准 |
| `docs/adr/0004-refresh-cookie-and-token-storage.md` | refresh Cookie 和 token 存储 | 已同步现状；响应不再返回 refresh token 原文 |
| `docs/adr/0005-offline-transcript-privacy-boundary.md` | 离线访谈隐私 | 保留；作用域、TTL 和 API 缓存边界明确 |
| `docs/adr/0006-open-api-v1-contract.md` | Open API 兼容合同 | 保留；快照和向后兼容规则明确 |
| `frontend/README.md` | 前端运行与环境变量 | 已更新；`VITE_*` 不得放秘密，协作 flag 默认关闭 |

## 机械检查

- 相对 Markdown 链接：已扫描，当前公开树无缺失目标。
- 高置信度凭据模式：已扫描当前树，未发现命中；这不替代历史扫描或供应商侧撤销/轮换。
- 本机路径、日志、原始材料和第三方全文：公开清理树不包含；私有备份继续单独保管。
- 发布状态：文档审阅切片完成，但最终发布仍需依赖、许可证、历史 secret、环境矩阵和项目创建者审阅闸门。
