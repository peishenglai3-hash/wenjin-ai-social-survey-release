# Wenjin Open API V1（当前实现范围）

当前 Open API 是受认证保护的窄范围 gateway，不是匿名公共 SaaS。它的目标是先固定 provider contract 和安全边界，让部署者能够在自己的服务端配置供应商，再由第三方客户端调用问津后端。

## 安全边界

- provider key、base URL 和模型配置只读取后端环境变量或受控 secret manager。
- 请求体不接受 `api_key`、`base_url` 或任意上游 URL；未知字段会被拒绝。
- 前端、浏览器存储、URL、响应、日志和项目审计事件不应出现 provider key。
- 没有可用 provider 时，API 返回安全的 `503`，不会构造外部 HTTP client。
- 项目上下文当前只允许项目 owner；协作成员对旧研究产物的共享读取/写入要等版本化产物与权限矩阵阶段完成。

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

响应是稳定的问津 envelope，包含 `provider`、`model`、文本和归一化 token usage；上游错误不会原样转发。

## 本地 fake provider

在离线开发或契约测试中可设置 `OPEN_API_FAKE_ENABLED=true`。它不访问网络，也不代表真实模型质量。生产部署应保持 `false`，并为自己的后端配置至少一个真实 provider key。

## 尚未纳入 V1

配额账本、API token 生命周期、自动重试策略、webhook、SDK、流式公开端点、embedding/vision/transcribe 的统一 contract，以及第三方可执行扩展隔离仍需单独设计、测试和安全复核。
