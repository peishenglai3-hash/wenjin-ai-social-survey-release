# ADR-0006：Open API V1 先固定窄 contract

- 状态：Accepted
- 日期：2026-10-16
- 范围：Open API、provider adapter、第三方客户端

## 决策

第一版只公开受认证的 provider capability discovery 和 chat completion envelope。provider 选择必须来自服务端 allow-list；请求不得携带 key、base URL 或任意上游 URL。OpenAI-compatible 和 DashScope 使用同一内部 contract，local fake provider 只用于离线开发和契约测试。

## 为什么不一次开放全部生态

配额账本、API token 生命周期、webhook、公开流式协议、embedding/多模态统一能力和可执行第三方扩展都需要独立的权限、审计、重试、网络白名单和隔离模型。先固定窄 contract 可以保留旧单人路径，并避免把未审计的扩展代码加载进服务进程。

## 验证

`backend/tests/test_provider_contract.py` 覆盖 fake provider、manifest 不泄密、认证 Open API 不接收 `api_key`、项目 owner 归属和上游错误归一化；无 provider 的旧 AIService 边界由 `test_provider_boundary.py` 覆盖。
