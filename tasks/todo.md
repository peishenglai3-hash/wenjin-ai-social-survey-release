# Wenjin 开源演进 V2 任务清单

状态：实施中；阶段 0 基线已完成，平台硬化与能力切片按阶段推进。

## 计划与基线

- [x] P0.1 建立 `AGENTS.md` 项目规则文件。
- [x] P0.2 生成当前 main 与原 master 功能/环境基线报告（后端完整依赖与 Docker smoke 待补证据）。
- [x] P0.3 建立 ADR 目录和第一批架构决策草案。
- [x] P0.4 记录基线测试、构建、secret scan 和工作树状态；后续切片证据持续追加。

## 技术与环境评审

- [x] 委派只读技术/环境评审子代理。
- [x] 审阅子代理报告，按 P0/P1/P2 建立修复顺序。
- [ ] 记录未采纳意见及原因，避免隐性范围扩张。

## 平台硬化

- [ ] P1 配置、启动失败、错误 envelope、request ID 和日志脱敏。
- [ ] P2 认证、CORS、JWT/token 存储、对象归属、上传和 SSRF 边界（认证 Cookie/摘要、离线队列隐私、编码/反射/场景及多组对象归属已完成第一轮，响应兼容字段、CORS、真实 PWA 验收和全局上传生命周期仍待完成）。
- [ ] P3 数据库迁移、SQLite/PostgreSQL、Redis 和 Compose 环境（问卷与协作迁移、Alembic drift 和显式迁移启动链已完成，已有库/PostgreSQL/健康依赖仍待验收）。
- [ ] P4 CI lint/type/test/build/security/license/secret gates（已加入 compile、pip check、Alembic drift、diff whitespace 和高置信度 credential scan；lint、依赖漏洞、license、OpenAPI 与 Docker smoke 仍待完成）。

## 知识流水线

- [x] K1 知识包 schema、validator、manifest 和私有审计目录（运行时仅接受 approved 且 hash 校验通过的私有包）。
- [ ] K2 原有知识/训练材料分类、脱敏、授权和版本登记。
- [x] K3 使用联网研究整理中英文社会调查资料候选集（私有审计暂存）。
- [x] 委派独立知识审计子代理，禁止其写入公开 runtime。
- [ ] K4 人工批准前的事实、译文、许可、隐私、偏差和 prompt/skill 审计。
- [ ] K5 只导入 `approved` 且未撤销知识，并验证撤销传播。

## WISE、协作与 API

- [x] W1/W2 WISE 提案、审批、撤销、证据和记忆写入门（模型生成的候选记忆先进入 pending；批准事务才写入长期记忆）。
- [ ] W3 WISE/fake provider/提示注入/失败重试测试。
- [x] C1 协作项目、成员、角色、邀请和归属模型（双用户拒绝测试已覆盖）。
- [x] C2 版本、批注、审核任务、审计事件和可撤销脱敏分享（删除/保留策略与分页待补）。
- [ ] C3 后端协作 API、权限矩阵、分页、幂等和错误契约（成员/邀请/角色/审计/研究产物列表已支持 bounded offset pagination；统一 envelope、删除保留策略和竞态幂等仍待完成）。
- [ ] C4 前端协作最小闭环和安全默认 feature flag。
- [ ] C5 接口与浏览器 smoke，不实现实时共同编辑。
- [x] A1 provider contract、fake provider、capability manifest 和契约测试（无网络 fake 与错误边界已覆盖）。
- [x] A2 OpenAI-compatible/DashScope server-side BYOK adapters（服务端 key、无 key fail-closed 和上游错误归一化已覆盖）。
- [x] A3 gateway scope、项目归属、限流、配额、有限重试、运营审计和 redaction（API token 生命周期、webhook、SDK 与扩展隔离待补）。
- [x] A4 OpenAPI snapshot、最小标准库 SDK、示例和兼容性文档（流式公开端点仍未纳入 V1）。
- [ ] A5 扩展执行隔离拒绝测试和安全边界说明。

## 文档与发布

- [ ] D1-D4 全量 README/`.md` inventory、校准、链接和示例验证。
- [ ] 更新 ADR、CHANGELOG、贡献指南、知识准入指南、API/安全文档。
- [ ] 完成原有功能回归与新增功能全量测试。
- [ ] 完成三环境矩阵、依赖/license/secret/隐私/版权审计。
- [ ] 生成发布候选、干净 clone 验证和回滚演练记录。
- [ ] 输出发布报告并等待项目创建者审阅。
- [ ] [阻塞，待 G7 及单独确认] 推送公开仓库 main 和版本 tag。
