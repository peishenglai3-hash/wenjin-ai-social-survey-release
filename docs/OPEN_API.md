# Wenjin Open API V1（当前实现范围）

当前 Open API 是受认证保护的窄范围 gateway，不是匿名公共 SaaS。它的目标是先固定 provider contract 和安全边界，让部署者能够在自己的服务端配置供应商，再由第三方客户端调用问津后端。

因此，后来使用者只需要在自己的 Wenjin 部署环境配置自己的 provider key；客户端只持有问津 access token，不需要也不应该把供应商 key 交给浏览器或第三方插件。

## 安全边界

- provider key、base URL 和模型配置只读取后端环境变量或受控 secret manager。
- 请求体不接受 `api_key`、`base_url` 或任意上游 URL；未知字段会被拒绝。
- 前端、浏览器存储、URL、响应、日志和项目审计事件不应出现 provider key。
- 没有可用 provider 时，API 返回安全的 `503`，不会构造外部 HTTP client。
- 项目上下文当前只允许项目 owner；协作成员对旧单人研究产物仍不能越权，版本化协作产物使用独立的协作 API。
- 每个 profile 有滚动 24 小时请求数和 token 配额；响应会给出 request ID 和剩余 token 估计值。配额记录只保存 provider/model/token/status 元数据，不保存 prompt 或模型输出。
- 对 provider 明确标记为临时失败的错误最多做有限次数重试；拒绝类错误不重试，重试次数和退避由后端配置限制。
- 配额检查是防御性滚动窗口检查，不是跨实例原子扣款；多副本部署仍应在网关或 Redis 层增加原子限额器。

## 已实现端点

### `GET /api/v1/open-api/providers`

返回不含密钥和私有 URL 的 capability manifest，例如：

```json
{
  "providers": [
    {
      "id": "openai-compatible",
      "label": "OpenAI-compatible provider",
      "configured": false,
      "capabilities": ["chat", "stream", "health"],
      "default_model": "deepseek-chat"
    },
    {
      "id": "dashscope",
      "label": "Alibaba DashScope compatible provider",
      "configured": false,
      "capabilities": ["chat", "stream", "health"],
      "default_model": "qwen-plus"
    }
  ]
}
```

### `POST /api/v1/open-api/chat/completions`

请求使用登录后的问津 access token；`provider` 可选，未指定时选择第一个已配置 provider：

```json
{
  "provider": "dashscope",
  "messages": [
    {"role": "user", "content": "请帮助我检查一个研究问题。"}
  ],
  "temperature": 0.7,
  "max_tokens": 1024
}
```

响应是稳定的问津 envelope，包含 `request_id`、`provider`、`model`、文本、归一化 token usage 和配额剩余估计；上游错误不会原样转发。

## 本地 fake provider

在离线开发或契约测试中可设置 `OPEN_API_FAKE_ENABLED=true`。它不访问网络，也不代表真实模型质量。生产部署应保持 `false`，并为自己的后端配置至少一个真实 provider key。

## 已补充的运营边界

- `OPEN_API_DAILY_REQUEST_QUOTA` 和 `OPEN_API_DAILY_TOKEN_QUOTA` 控制 profile 级滚动 24 小时预算。
- `OPEN_API_RETRY_ATTEMPTS` 被硬限制在最多 3 次，退避时间也有上限；这不是无限重试或故障转移承诺。
- `/api/v1/open-api/` 仍受 IP 滑动窗口限流；生产部署应使用 Redis，单进程内存 fallback 只适合开发/故障降级。

## 尚未纳入 V1

API token 生命周期、webhook、SDK、流式公开端点、embedding/vision/transcribe 的统一 contract，以及第三方可执行扩展隔离仍需单独设计、测试和安全复核。

第三方技能市场的当前边界见 [`docs/EXTENSION_SECURITY.md`](EXTENSION_SECURITY.md)：开放 API 与社区技能都不接受客户端 provider key，也不把社区文本升级为服务端可执行代码。

## 客户端与 WebSocket 边界

HTTP 客户端只需要登录后的问津 access token。田野实时 ASR、pipeline 和 facial WebSocket 入口使用浏览器可发送的 `Sec-WebSocket-Protocol: bearer, <access-token>` 协商方式；服务端只返回 `bearer` 子协议，拒绝缺失、过期或非 access token。不要把 token 拼到 WebSocket URL、日志或示例链接中。

## 最小客户端与兼容性

仓库提供一个不依赖第三方 SDK 的示例客户端 [`examples/open_api_client.py`](../examples/open_api_client.py)。它只接收问津后端地址和登录 access token，不接受 provider key；生产调用方应自行处理 token 生命周期、重试提示和本地日志脱敏。

可审阅的 V1 合同快照位于 [`docs/open-api-v1.snapshot.json`](open-api-v1.snapshot.json)，并由后端测试检查路径、schema 和禁止的客户端凭据字段。V1 的兼容规则是：在 `/api/v1` 内只做向后兼容的新增字段/能力；移除字段、改变语义或改变认证方式必须进入新的版本路径，并同步更新快照、示例和变更说明。
