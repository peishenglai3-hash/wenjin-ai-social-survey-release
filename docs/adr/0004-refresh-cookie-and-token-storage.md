# ADR-0004：刷新令牌 Cookie 与前端内存令牌

- 状态：Accepted / Implemented in evolution branch
- 日期：2026-10-16
- 范围：认证会话、Web 客户端、原生 fetch/SSE

## 背景

旧版 Web 客户端把 access token 和 refresh token 一起写入 `localStorage`，并由多个 fetch/SSE 路径自行读取。后端也把 refresh token 原文写入用户表。这样会扩大 XSS、浏览器扩展、备份和数据库泄露后的影响面。

## 决策

1. 后端只把 refresh token 的 HMAC-SHA256 摘要写入数据库；旧的明文值只在一次成功轮换时兼容并升级为摘要。
2. refresh token 通过 `HttpOnly` Cookie 传递，Cookie 路径限制为 `/api/v1/auth`，并使用配置化的 `SameSite`、`Secure` 和过期时间。生产环境必须设置 `REFRESH_COOKIE_SECURE=true`，本地明文 HTTP 开发环境才允许保持 false。
3. 前端 access token 只驻留模块内存，不再持久化到 `localStorage`；Axios、原生 fetch 和 SSE 统一使用内存令牌，并在需要时携带 Cookie。
4. 旧版 `wenjin_auth` 仅用于一次迁移：启动时尝试交换其中的 refresh token，随后无论成功与否都删除该键。响应中保留的 refresh 字段仅作为当前过渡期 API 兼容字段，前端不得读取或持久化；后续公开 API 契约将评估移除原文响应。
5. 登录、刷新、ORCID 交换都会轮换 refresh token；刷新 token 增加随机 `jti`，避免同秒生成相同 token。退出会撤销服务端记录并清理 Cookie。

## 后果

- 页面刷新仍可依靠 HttpOnly Cookie 恢复会话，但 JavaScript 不能读取 refresh token。
- 任何依赖直接从 `localStorage` 取 token 的第三方集成需要迁移到 Cookie/内存令牌或服务端会话。
- Bearer access token 仍用于 API 与 SSE；它的生命周期和内存暴露面仍需由 CSP、XSS 防护和短过期时间共同控制。
- 数据库备份不再直接包含可重放的 refresh token，但历史明文值若曾在外部备份或日志中出现，仍必须在供应商/存储侧撤销、轮换和复核。

## 验证

- `backend/tests/test_refresh_token_storage.py` 覆盖摘要存储、Cookie 刷新和明文兼容升级。
- 前端 `npx tsc --noEmit` 和 `npx vitest run` 已通过；前端测试中的 API client 使用无网络 mock。
- 生产部署门禁必须验证 `REFRESH_COOKIE_SECURE=true`、HTTPS、CORS/凭据白名单和退出后的 Cookie 清理。
