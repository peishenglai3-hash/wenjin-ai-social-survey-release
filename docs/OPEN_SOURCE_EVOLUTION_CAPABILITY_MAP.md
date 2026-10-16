# Wenjin 开源演进能力地图

状态：已批准；能力地图本身不代表已实现或已进入公开 release

基线：`main@9a536905bc8e77c6366b596f7c15ac36a205034c`

## 能力边界

| 模块 ID | 责任 | 依赖 | 首个可验收产物 |
|---|---|---|---|
| `knowledge-pipeline` | 原有知识卡片/训练材料的权利分类、来源登记、双语资料导入、审计代理、版本化发布 | — | 可追溯、可撤销的知识包；未经审计不能导入运行时 |
| `platform-hardening` | 环境一致性、配置校验、依赖/迁移、数据归属、上传安全、错误契约和测试门 | 当前基线 | 干净环境可启动，核心回归通过，P0 安全项关闭 |
| `wise-memory` | WISE 微创新机制、记忆提案、证据边界、用户确认、撤销与反馈闭环 | `knowledge-pipeline`, `platform-hardening` | AI 只能提出可审阅提案，确认后才写入记忆/技能 |
| `collaboration-mode` | 项目、成员、邀请、角色权限、研究产物版本、批注、审核、审计和脱敏分享 | `platform-hardening` | 两个账户无法越权，研究产物可版本化、审核和撤销 |
| `open-api-ecosystem` | 服务端 BYOK、provider adapter、scope、配额、统一错误、OpenAPI、Webhook、SDK 和扩展隔离 | `platform-hardening`, `collaboration-mode` | 第三方客户端可用稳定 API 完成受限研究流程 |
| `release-gate` | 端到端、环境、网络安全、版权/隐私、文档、回滚和公开推送 | 全部模块 | 可复现 release，公开树无未审计材料，推送有证据链 |

## 实施顺序

`knowledge-pipeline` 与 `platform-hardening` 可并行只读审查；实现顺序为：

`platform-hardening` → `knowledge-pipeline` → `wise-memory` → `collaboration-mode` → `open-api-ecosystem` → `release-gate`

知识材料的审计是进入 Wenjin 的硬门槛，不因代码阶段完成而绕过。
