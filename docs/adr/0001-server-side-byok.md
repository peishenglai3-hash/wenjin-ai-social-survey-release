# ADR-0001：服务端 BYOK 与 provider fail-closed

- 状态：Accepted
- 日期：2026-10-16
- 范围：AI provider、开放 API、前端调用边界

## 背景

问津需要支持 OpenAI-compatible、DashScope 和本地 fake provider，但真实密钥不能进入浏览器、公开仓库、URL、响应、日志、审计事件或测试输出。没有可用 provider 时，继续向默认外部地址发送空 key 会制造误导性网络请求和泄露面。

## 决策

真实 provider 只由服务端部署配置或受控 secret manager 提供；前端只能调用问津自己的服务端 API。provider 路由在没有有效配置时必须 fail-closed：文本/流式/图像请求返回明确的 503，健康检查返回不可用，不创建外部 HTTP client。测试和本地开发使用 fake provider 或明确的测试密钥。

## 后果

- 部署者需要自行配置 provider key；公开仓库不提供可运行的真实 key。
- provider 适配器必须保留错误、超时、限流和能力声明，不将 key 传入日志或持久化对象。
- ASR、视觉和其他 provider 出口仍需逐项遵守同一边界。

## 验证

`backend/tests/test_provider_boundary.py` 验证无 provider 时不会构造外部 client；开放 API 阶段还需补 provider contract、fake provider 和 secret redaction 测试。

