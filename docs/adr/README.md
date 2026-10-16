# Wenjin 架构决策记录

本目录记录会影响公开发布、安全边界和兼容性的稳定决策。每条 ADR 说明背景、决策、后果和验证方式；实现可以继续演进，但不得无记录地放宽安全边界。

当前决策：

- [ADR-0001：服务端 BYOK 与 provider fail-closed](0001-server-side-byok.md)
- [ADR-0002：协作研究模式 V1 不做实时共同编辑](0002-collaboration-v1-no-realtime-editing.md)
- [ADR-0003：知识材料先审计、后导入运行时](0003-knowledge-audit-gate.md)
- [ADR-0004：刷新令牌 Cookie 与前端内存令牌](0004-refresh-cookie-and-token-storage.md)
- [ADR-0005：离线访谈草稿的隐私边界](0005-offline-transcript-privacy-boundary.md)

