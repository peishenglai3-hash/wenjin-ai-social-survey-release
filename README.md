# 问津 · AI 社会调查工作台

> Wenjin — an AI-assisted workstation for social research.

问津是一个早期的社会调查研究工具原型，尝试把选题设计、问卷生成、田野记录、文献发现和研究反思放进同一套工作流。它由 React/Vite 前端和 FastAPI 后端组成，支持本地 SQLite，也可以接入 PostgreSQL、Redis 以及研究者自己配置的 AI 服务。

本仓库目前处于“历史项目整理后重新开放”的阶段。它适合阅读、复用和继续实验，不应被当作已经完成安全审计、伦理审查或生产运维验证的 SaaS 产品。

## 主要模块

- 选题与问卷：研究问题拆解、问卷草拟和迭代
- 田野工具：访谈记录、音频转写和现场资料整理
- AI 研究助手：方法建议、文本分析、反思和研究上下文管理
- 文献发现：学术搜索、引用和研究空白辅助
- 导出与面板：研究过程可视化以及 DOCX/XLSX/PDF 导出

功能边界和实际可用性仍以源码与测试为准；模型输出只能作为研究建议，不能替代研究者判断、伦理审查、数据保护和事实核验。

## 技术栈

- Frontend: React, TypeScript, Vite, Axios, ECharts
- Backend: FastAPI, Pydantic Settings, SQLAlchemy, SQLite/PostgreSQL, Redis
- Optional AI providers: DeepSeek, Qwen/DashScope, Volcano Engine, Hunyuan, Xunfei

## 快速开始

### 运行后端

```bash
cd backend
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env  # Windows 可手动复制文件
```

编辑 `backend/.env`：至少设置一个 AI 供应商 key、一个随机的 `JWT_SECRET`，并把 `CORS_ORIGINS` 限定为本地前端地址。供应商 key 只应存在于后端环境变量中，不能写进前端代码、浏览器存储、日志或提交记录。

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

共享或生产数据库必须在启动服务前显式执行 Alembic 迁移；应用默认不会在启动时隐式 `create_all` 或吞掉 `ALTER TABLE` 错误。仅用于一次性本地原型时，才可在 `.env` 中临时设置 `AUTO_CREATE_SCHEMA=true`。

### 运行前端

```bash
cd frontend
npm ci
npm run dev
```

默认前端地址是 `http://localhost:5173`，后端 API 文档是 `http://localhost:8000/docs`。如后端不在本机，请通过前端的本地环境配置指定 API 地址，不要把供应商 key 放到 `VITE_*` 变量中。协作研究 V1 默认关闭；在确认部署边界后设置 `VITE_COLLABORATION_V1_ENABLED=true` 才显示前端入口。

### Docker（本地实验）

```bash
cp backend/.env.example backend/.env
# 在当前 shell 设置仅用于本地 Compose 的 POSTGRES_PASSWORD
docker compose up --build
```

Compose 配置只用于本地实验，backend 容器会先执行 `alembic upgrade head`；生产部署仍需要自行完成密钥管理、TLS、数据库备份、访问控制、限流、日志脱敏和数据删除流程。

Compose 内部会把 Redis 地址改写为 `redis://redis:6379/0`，并等待 Redis/backend 健康检查通过后再启动依赖服务；Redis 和 PostgreSQL 端口默认只绑定到本机。若将 `DATABASE_URL` 改为 Compose 内的 PostgreSQL 地址，还应在自己的部署覆盖文件中让 backend 等待 `postgres` 健康检查，不要把本地实验配置直接当作生产编排。

## BYOK 与数据边界

本项目采用后端 BYOK（Bring Your Own Key）边界：

1. 研究者在自己的部署环境配置供应商 key。
2. 前端只调用问津后端，不接收或持久化供应商 key。
3. 后端只把请求发送到已配置的供应商，并应避免记录原始 prompt、音频、图像和个人身份信息。
4. 研究资料、访谈文本、音频、导出文件和数据库默认视为敏感数据；不要把真实田野数据提交到 Git。

当前版本已提供受认证保护的协作成员/角色/邀请/审计元数据 API、研究产物版本/批注/审核/可撤销脱敏分享（列表支持 bounded pagination）、窄范围的版本化 Open API provider contract，以及 WISE 提案/审批边界。Copilot 和反思产生的候选记忆先进入待审区，不能自动写入长期记忆。它仍不是完整的多租户协作系统：批量审核、删除/保留策略、开放 API token 生命周期、流式公开端点和第三方扩展隔离仍在后续阶段。知识卡片是可选的部署者数据，不随公开树提供；候选知识材料仅见于 [`docs/KNOWLEDGE_CANDIDATE_REGISTER.md`](docs/KNOWLEDGE_CANDIDATE_REGISTER.md)，保持 `needs_review`。田野工具的 WebSocket 入口要求通过 `bearer` 子协议发送内存 access token，不接受 URL 中的 token。

## 测试

```bash
cd backend
python -m pytest tests/ -v --tb=short

cd ../frontend
npm run build
npm test
```

测试可能需要根据本地 Python/Node 版本和可选模型依赖调整；不要为了让测试通过而提交真实凭据或真实研究资料。

## 公开范围说明

本清理分支不包含：第三方书籍及其 OCR/切片/知识卡片、内部申报和组会材料、个人部署日志、服务器配置、截图、APK、研究原始资料和本机路径。这些内容不随代码获得再许可，详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

## 路线图

- [x] 首版 provider adapter / BYOK contract、fake provider 和能力发现
- [x] 研究项目成员、角色、邀请和元数据审计模型
- [x] WISE 候选提案、人工审批、撤销和记忆写入门
- [x] 研究产物版本、批注、审核任务、分页和可撤销脱敏分享（删除/保留策略仍待完成）
- [x] provider 配额、有限重试和运营审计；webhook、最小 SDK 和第三方扩展隔离仍待设计
- [ ] 版本化 REST/OpenAPI、配额与 webhook
- [ ] 可审计的第三方扩展机制和 typed SDK
- [ ] 在合并前完成依赖、历史提交和发布包的独立复核

## 许可证

本项目原创代码和原创文档采用 Apache-2.0 许可证，许可证只覆盖确认拥有再许可权的内容。第三方资料、依赖、模型、字体、图标和媒体资源仍受各自许可证约束；Apache-2.0 不替代第三方材料的授权，也不授予未经确认的书籍、论文全文、OCR、切片或知识卡片的再许可权。

## 安全问题

请先阅读 [`SECURITY.md`](SECURITY.md)。如果曾经把真实 key、密码、令牌或个人数据提交到任何公开历史中，应立即在供应商侧撤销/轮换，并把历史清理作为单独的、经维护者确认的操作。

---

问津：让 AI 帮助研究者整理问题，但不替研究者承担研究责任。
