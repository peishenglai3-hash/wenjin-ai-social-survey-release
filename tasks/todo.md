# Wenjin 开源演进 V2 任务清单

状态：实施中；阶段 0 基线与阶段 1 平台硬化进行中。

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
- [ ] P2 认证、CORS、JWT/token 存储、对象归属、上传和 SSRF 边界（认证 Cookie/摘要、离线队列隐私与多组对象归属已完成第一轮，响应兼容字段、CORS、真实 PWA 验收和全局上传生命周期仍待完成）。
- [ ] P3 数据库迁移、SQLite/PostgreSQL、Redis 和 Compose 环境。
- [ ] P4 CI lint/type/test/build/security/license/secret gates。

## 知识流水线

- [ ] K1 知识包 schema、validator、manifest 和私有审计目录。
- [ ] K2 原有知识/训练材料分类、脱敏、授权和版本登记。
- [x] K3 使用联网研究整理中英文社会调查资料候选集（私有审计暂存）。
- [x] 委派独立知识审计子代理，禁止其写入公开 runtime。
- [ ] K4 人工批准前的事实、译文、许可、隐私、偏差和 prompt/skill 审计。
- [ ] K5 只导入 `approved` 且未撤销知识，并验证撤销传播。

## WISE、协作与 API

- [ ] W1/W2 WISE 提案、审批、撤销、证据和记忆写入门。
- [ ] W3 WISE/fake provider/提示注入/失败重试测试。
- [ ] C1 协作项目、成员、角色、邀请和归属模型。
- [ ] C2 版本、批注、审核任务、审计事件、脱敏分享和删除策略。
- [ ] C3 后端协作 API、权限矩阵、分页、幂等和错误契约。
- [ ] C4 前端协作最小闭环和安全默认 feature flag。
- [ ] C5 接口与浏览器 smoke，不实现实时共同编辑。
- [ ] A1 provider contract、fake provider、capability manifest 和契约测试。
- [ ] A2 OpenAI-compatible/DashScope server-side BYOK adapters。
- [ ] A3 gateway scope、项目归属、限流、配额、重试、审计和 redaction。
- [ ] A4 OpenAPI snapshot、最小 SDK、示例和兼容性文档。
- [ ] A5 扩展执行隔离拒绝测试和安全边界说明。

## 文档与发布

- [ ] D1-D4 全量 README/`.md` inventory、校准、链接和示例验证。
- [ ] 更新 ADR、CHANGELOG、贡献指南、知识准入指南、API/安全文档。
- [ ] 完成原有功能回归与新增功能全量测试。
- [ ] 完成三环境矩阵、依赖/license/secret/隐私/版权审计。
- [ ] 生成发布候选、干净 clone 验证和回滚演练记录。
- [ ] 输出发布报告并等待项目创建者审阅。
- [ ] [阻塞，待 G7 及单独确认] 推送公开仓库 main 和版本 tag。
