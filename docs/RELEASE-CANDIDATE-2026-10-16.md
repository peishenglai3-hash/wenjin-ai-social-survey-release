# Wenjin 发布候选报告（2026-10-16）

状态：`release candidate`，等待最终前端质量门禁、部署环境证据和发布者复核，不等同于已经公开发布。

当前分支：`codex/wenjin-evolution-v2`  
本次候选审计基于 `6e6a6ad` 之后的本地工作树；最终审计提交哈希以本地 `git log` 为准。
公开仓库 `main`：未修改、未推送。原 `ai-social-survey` master 基线：`c759f6f415a55c3f66efde17627b57c5415b1791`。

## 1. 结论摘要

当前候选已经完成一轮可运行的安全、知识准入、WISE、协作研究和 Open API 演进，稳定核心代码路径没有因新架构被删除。与私有备份中原 master 的路径和功能边界对照显示：原有 `frontend/src` 文件全部保留，并新增协作 API/页面；原有 `backend/app` 中被移出的 7 个文件全部是历史知识卡片/manifest 数据，而不是业务代码；其余后端新增内容主要是权限、安全、迁移、协作、WISE 和 provider contract。当前候选仓库不含原 master 对象，不能把本地 Git diff 误报为对该 SHA 的直接对象级比较。

因此可以给出：

- 功能路径保留程度：高。认证、选题/问卷、田野工具、AI 助手、文献发现、知识/记忆、导出、社区和管理等现有路径仍在源码与回归测试中。
- 实用性判断：具备继续部署和复用的候选基础；协作研究 V1 和 Open API V1 已有最小闭环。
- 不能宣称：与原 master 在所有真实 provider、历史数据、PostgreSQL/Redis、Docker 和浏览器环境中已经完成严格等价验收；这些还需要 CI/部署环境和人工验收证据。

## 2. 原 master 对照证据

对照使用私有备份中的原 master ZIP 和当前 Git 跟踪树，只比较路径、类别和可执行代码边界，不把私有材料复制到公开树：

| 范围 | 原 master | 当前候选 | 判断 |
| --- | ---: | ---: | --- |
| 总文件 | 386 | 320 | 减少部分主要是内部文档、部署脚本、日志、原始材料和知识数据 |
| `backend/app` | 104 | 129 | 仅 7 个移出项为历史知识卡片数据；新增安全/协作/API/WISE 代码 |
| `frontend/src` | 73 | 76 | 原有 73 个保留，新增协作 API、协作页面和离线队列测试相关内容 |
| `backend/tests` | 11 | 41 | 新增归属、认证、上传、知识、协作、WISE、provider 和安全拒绝测试 |
| `frontend/src/__tests__` | 3 | 4 | 保留原测试并新增离线队列覆盖 |

原 master 中的书籍、PDF/OCR/切片、内部汇报、日志、部署脚本和知识卡片不进入公开树；它们继续作为私有备份，不能因为 Apache-2.0 代码许可证而获得再许可。

## 3. 已完成切片

### 平台与安全

- request ID、通用错误边界、provider fail-closed、CORS/代理边界和多组对象归属校验。
- refresh token 改为 HttpOnly Cookie + 服务端摘要，浏览器 access token 仅内存保存，响应不返回 refresh token 原文。
- 上传大小/签名/归属/保留元数据、URL/SSRF 和实时 WebSocket bearer 子协议边界。
- ORCID redirect 仅接受同源相对路径；provider 响应体、Redis URL、字段笔记和文献响应不会进入日志；CORS 方法/请求头已收窄，反向代理模板增加 HSTS/CSP。
- 修复实时情绪/时间线的跨用户模块级状态泄漏；实时 pipeline、情绪 tracker 和时间线存储均按连接/用户隔离，并增加帧大小、消息速率和文本上限。
- SMS 未配置或 provider 不可用时 fail-closed，不再生成、接受或记录可复用验证码；Open API 输入、分析属性、音频/转录和批量边界均有上限。
- CI 已包含 `pip check`、compile、Alembic upgrade/check、diff whitespace 和高置信度凭据扫描。
- 在线 npm audit 首轮发现 17 个前端依赖漏洞；已通过非强制修复更新 lockfile，并移除未被源码使用的 `sharp` 依赖，当前在线审计为 0 vulnerabilities。

### 知识、prompt 与 WISE

- 内置 skill 自动附加证据/推断区分、隐私最小化、知情同意、AI 建议性、场域/语言限制和失败条件。
- 私有知识包只接受 `approved` manifest、哈希匹配、未撤销条目；逐卡校验未知字段、长度、相对路径、语言、场域、方法标签、材料类型和明显提示注入/凭据标记。
- 中英文候选材料只公开元数据登记，全部保持 `needs_review`；独立审计报告仍在私有审计区，未进入 runtime。
- WISE 候选记忆进入 pending，经过批准/撤销路径才能影响长期记忆。

### 协作研究 V1

- 项目成员、角色、邀请、审计事件、研究产物、版本、批注、审核任务、分页和一次性可撤销脱敏分享。
- 前端最小协作工作台默认关闭；启用后只显示成员元数据和研究产物入口，不实现实时共同编辑，不上传原始访谈资料。

### Open API V1

- OpenAI-compatible、DashScope 和 local fake provider contract；provider key 只在部署者后端环境配置。
- scope/项目归属、滚动配额、有限 retry、metadata-only usage records、OpenAPI snapshot、标准库示例和 prompt-only 扩展边界。
- Open API 配额在 profile 行级锁/事务内预留请求和 token，成功/失败回写同一条记录；异常中断的预留十分钟后释放 token，保留请求计数。
- 普通受保护 HTTP 路由生成 request-scoped AI service，成本熔断器默认绑定当前 profile；技能执行 payload 具有大小、深度、复杂度、凭据字段和控制字段边界。

## 4. 实测验证

本机验证环境：Python 3.11.15、Node v24.15.0、npm 11.12.1；后端测试清除了代理环境变量和所有真实 provider key，使用仅测试 JWT secret。

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 后端全量 | 284 passed | 53.82s，2 个既有 Pydantic deprecation warnings |
| 知识准入专项 | 12 passed | 包含未知字段、越界、路径、注入标记、双语 metadata 和 runtime 只读 manifest |
| 后端 compile | passed | `python -m compileall -q app` |
| 依赖图 | passed | `pip check` 无 broken requirements |
| 启动 smoke | passed | Uvicorn 返回 `status=ok`、`version=0.5.0` |
| SQLite migration | passed | `alembic upgrade head` + `alembic check` + `alembic upgrade head --sql`，含知识 metadata migration |
| 前端类型/单测 | passed | `tsc --noEmit`，Vitest 4 files / 17 tests |
| 前端 build | passed with warning | Vite build 成功；最大压缩 vendor chunk 约 1.29 MB |
| 新协作文件 lint | passed | 协作页面/API/config 定向 ESLint 通过 |
| 全前端 lint | passed | 0 errors、0 warnings；未关闭规则，未删除稳定功能 |
| npm 依赖审计 | passed | 在线 `npm audit --audit-level=high`：0 vulnerabilities；已移除未使用的 `sharp` |
| 前端窄屏审计 | passed with boundary | 320px/768px 视口截图通过；后端未联机，API 404 不能当作集成通过 |
| 当前树凭据扫描 | passed | 当前树及候选分支可达提交的高置信度模式未命中；不替代历史扫描和供应商侧轮换 |
| Markdown 链接 | passed | 公开文档 inventory 覆盖 30 个 Markdown/README 文件，当前相对链接无缺失目标 |
| Docker/Compose | not run | 当前验证环境未安装 Docker |
| Playwright 浏览器 smoke | not run | npm 包存在，但本机未安装 Chromium executable |
| pip-audit/SBOM/Trivy | not run | 当前环境没有可用的在线依赖审计、SBOM 或镜像扫描工具；不能据此宣称供应链清零 |

## 5. 仍需项目创建者审阅的阻塞项

1. 知识候选的版权/再分发权、翻译质量、场域适配和伦理边界仍需人工批准；在此之前不能生成 `approved` manifest，也不能把原训练书籍/切片恢复到公开树。
2. PostgreSQL + Redis、Docker Compose、真实浏览器/PWA、生产 HTTPS/CORS/CSP/HSTS 和上传保留清理还没有本机成功证据。
3. Open API 配额代码已具备事务预留和 profile 锁，但仍需 PostgreSQL 多实例压测证据；后台直接创建 AI service 的异步任务仍需补充用户归属；完整数据导出/删除保留策略、DNS rebinding/SSRF 防护、Python 依赖 lock、SBOM 仍需部署级复核。
5. 服务端 BYOK 已实现，但它仍是部署者后端环境配置，不是让浏览器把 provider key 直接交给公共 API；ORCID/技能市场的外部审查和完整 typed SDK、webhook、公共 streaming 仍不属于本候选完成范围。

## 6. 发布建议与回滚

当前建议：保留候选分支和私有备份，先由项目创建者审阅本报告、知识审计报告和 `docs/MARKDOWN_INVENTORY.md`，完成剩余环境/版权/依赖闸门后，再单独确认是否将候选普通推送到公开仓库 `main`。本轮没有执行任何公开推送、强推、可见性变更或私有备份删除。

回滚路径是回到候选前的已提交 commit；协作前端可通过 `VITE_COLLABORATION_V1_ENABLED=false` 保持关闭，知识 runtime 可不设置 `KNOWLEDGE_DIR`，Open API provider 可保持未配置或关闭。
