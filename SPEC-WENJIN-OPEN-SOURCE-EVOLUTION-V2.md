# Spec: Wenjin 开源演进 V2

状态：已批准，实施中（2026-10-16）

日期：2026-10-16

基线：`main@9a536905bc8e77c6366b596f7c15ac36a205034c`

能力地图：[OPEN_SOURCE_EVOLUTION_CAPABILITY_MAP.md](docs/OPEN_SOURCE_EVOLUTION_CAPABILITY_MAP.md)

## Objective

在不删除已经稳定的问津核心代码、页面和测试基线的前提下，完成一次可回滚、可审计、轻量化的开源演进：

1. 将原有知识资产和新增中英文社会调查资料整理为有来源、有许可、有适用边界、可撤销的知识包；由独立审计代理核查后才允许进入运行时。
2. 纠正环境、配置、架构、数据归属、网络安全、记忆和迭代逻辑中的实际问题，减少重复逻辑和冗余路径。
3. 分阶段实现协作研究模式和开放 API 生态；AI 输出保持建议性，不能绕过人的审核直接改变研究事实、权限或公开材料。
4. 在此前已有功能通过回归、环境测试、前端构建和安全门后，才同步推送新的公开版本。

## Explicit assumptions

1. 当前 `main` 是继续演进的唯一公开基线；稳定功能默认保留，删除代码必须有重复性证据、替代路径和回归证明。
2. “重新整理知识库”指整理为来源记录、短摘要、可引用片段、结构化卡片和训练/提示模板，不把第三方书籍全文、OCR、切片或真实研究资料重新上传到公开仓库。
3. 新材料优先使用公开许可、官方开放文档、开放获取论文和明确允许再分发的资料；不确定的材料只进入私有审计区，不进入 Wenjin 运行时。
4. 协作研究模式第一版采用项目/成员/角色/版本/审核/审计模型，不在第一阶段引入高复杂度实时共同编辑。
5. 开放 API 第一版采用服务端 BYOK；供应商 key 只存在部署环境或受控 secret manager，不接受浏览器持久化或第三方插件明文传入。
6. “WISE”表示可解释、可撤销、证据绑定的微创新提案机制，不是自动改写核心代码、研究结论或用户记忆的代理权限。

## Scope

### In scope

- 知识来源登记、权利分类、双语卡片、训练样例、提示片段、审计状态、版本哈希和撤销。
- README、Markdown、提示模板、skill 文档逐份校准：来源、适用场域、输入输出、隐私边界、失败条件和安全约束必须清楚。
- 后端依赖、配置、迁移、日志、上传、认证、项目归属、错误响应和 CI 环境测试。
- WISE/记忆提案与人工确认、协作项目与成员权限、开放 API provider adapter 和最小 SDK/契约测试。
- 公开 release 的许可证、NOTICE、第三方声明、变更日志、回滚和审计证据。

### Out of scope for the first release

- 真实受访者数据托管、跨项目全文搜索、公共原始访谈分享。
- 在 API 进程内执行未经审查的第三方 Python/Node 插件。
- 以 AI 自动决定研究结论、自动发布材料或自动改变权限。
- 将未确认版权的书籍、论文、OCR、切片、知识卡片、日志或内部材料再次公开。

## Proposed data and control boundaries

### Knowledge pipeline

每个知识条目至少包含：`source_id`、标题、作者/机构、语言、年份、场域标签、方法标签、来源 URL/DOI、许可状态、摘要、短引用片段、脱敏状态、审计状态、版本哈希和撤销原因。运行时只读取 `approved` 且未过期/未撤销的条目。

知识流水线必须经过：候选收集 → 版权/隐私初筛 → 内容与事实核查 → 双语质量检查 → 提示/skill 影响评估 → 独立审计代理 → 人工批准 → 版本化导入。审计代理不能自己批准自己生成的材料。

### WISE and memory

WISE 输出只能是 `proposal`、`experiment` 或 `candidate_memory`。每项必须绑定触发事件、来源证据、适用范围、置信度、反例、预计副作用、撤销方式和人工批准者。未经批准不得写入长期记忆、公开 skill、项目事实或知识库。

### Collaboration

第一版实体：`research_projects`、`research_memberships`、`research_invites`、`research_artifacts`、`research_artifact_versions`、`research_annotations`、`research_review_tasks`、`research_activity_events`、`research_shares`。

每个敏感实体必须有 `project_id`，权限检查同时满足用户身份、项目成员关系、角色、对象归属和数据分类。分享默认只指向脱敏派生物，并支持过期、撤销、访问记录和删除。

### Open API

统一 provider adapter 至少提供 capability manifest、chat、stream、embedding、vision/transcribe（按供应商能力可选）和 healthcheck。网关统一处理 request ID、scope、项目归属、配额、超时、有限重试、错误 envelope、secret redaction 和审计 metadata。

第一版 API 只允许声明式 provider/skill manifest；可执行扩展必须等到独立 worker/WASM/容器隔离、签名、依赖和网络白名单完成后再开放。

## Commands and verification

### Backend

```text
cd backend
python -m pip install -r requirements.txt
python -m pytest tests/ -v --tb=short
```

### Frontend

```text
cd frontend
npm ci
npx tsc --noEmit
npm test -- --run
npm run build
```

### Release/security checks

```text
git diff --check
secret scan on current tree and history
dependency audit and license inventory
OpenAPI schema snapshot/contract test
clean-environment startup with random JWT_SECRET and no provider key
two-user ownership and role matrix tests
upload size/MIME/path/URL/SSRF tests
SSE/WebSocket timeout and disconnect tests
```

## Testing strategy

- 保持现有后端 138 项测试与前端类型检查、Vitest、构建为不可回退基线。
- 每个新实体先写权限/归属失败测试，再写成功路径；优先测试拒绝、撤销、过期和删除。
- 知识包测试来源字段、许可状态、审计状态、撤销传播和 prompt/skill 不越界。
- 使用 fake provider 做 API 契约、超时、限流、配额和错误归一化测试，不使用真实 key。
- 至少建立一个干净环境矩阵：SQLite/no provider、PostgreSQL+Redis/fake provider、Docker compose smoke。
- 任何测试失败不得通过删除测试、放宽生产鉴权或注入真实凭据解决。

## Boundaries

- Always：保留稳定核心代码；所有知识条目可追溯；AI 只提案；测试先行；密钥只在后端；普通 Git 推送；保留回滚点。
- Ask first：数据库迁移、公开 API 契约变化、旧仓库可见性变化、第三方材料再许可、删除稳定代码、公开 release 推送。
- Never：提交真实 key/PII；把第三方全文放入公开仓库；让插件执行宿主代码；让 AI 自动确认研究结论/权限/发布；用 `git reset --hard` 或强推覆盖用户历史。

## Success criteria

1. 能力地图和各模块规格得到审阅；实现任务按依赖顺序执行并可单独验收。
2. 新知识包 100% 有来源、语言、场域、许可、审计和版本信息；任何未批准条目不能被运行时加载。
3. 原有稳定功能回归通过，新增协作/API/WISE 功能有失败路径测试和环境测试。
4. 两个不同用户无法读取、编辑、分享或删除不属于其项目/角色范围的对象。
5. provider key 不出现在前端、浏览器存储、URL、响应、日志、审计事件或测试输出中。
6. `main` 可从干净环境安装、启动、测试和构建；发布包内容和许可证边界可复核。
7. 只有在上述条件全部满足、用户审阅发布报告后，才把版本推送到公开仓库。

## Approved decisions

以下决策已由项目创建者确认，作为后续计划、实现和验收的约束：

1. 批准能力地图中的六个模块及其实施顺序。
2. 协作研究模式 V1 采用项目/成员/角色/版本/审核/审计模型，暂不实现实时共同编辑。
3. 开放 API 首批 provider 为 OpenAI-compatible、DashScope 和 local fake provider。
4. 新知识材料默认进入私有审计区；完成来源、版权/许可、隐私、事实、双语质量和独立审计后，仍需人工批准才能导入 Wenjin 运行时。
5. 批准创建模块规格、任务清单并开始代码实现；每个增量必须单独测试、审查、提交，并在最终发布门禁通过后再推送公开仓库。

## Open questions

当前没有阻塞实施的开放问题。具体部署平台、生产配额、域名和观测服务在进入部署阶段前另行确认，不影响本地、CI 和公开代码仓库中的可复现实现。
