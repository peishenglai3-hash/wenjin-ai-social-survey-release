# Wenjin 项目代理与贡献规则

## 项目边界

问津（Wenjin）是 React/Vite 前端与 FastAPI 后端组成的 AI 辅助社会调查工作台。当前公开仓库是从早期项目清理后建立的可复现基线，不代表已完成生产安全、伦理或多租户审计。

稳定核心功能默认必须保留：认证、选题/问卷、田野工具、AI 研究助手、文献发现、知识/记忆、导出和现有测试。发现疑似冗余或问题时，先写证据和回归测试，再做最小修复；不得顺手重构无关模块。

## 技术栈与命令

- Backend: Python 3.12（CI）、FastAPI、Pydantic Settings、SQLAlchemy、SQLite/PostgreSQL、Redis。
- Frontend: Node 22（CI）、React、TypeScript、Vite、Vitest、Playwright。
- 后端安装：`cd backend` → `python -m pip install -r requirements.txt`。
- 后端测试：`python -m pytest tests/ -v --tb=short`。
- 前端安装：`cd frontend` → `npm ci`。
- 前端检查：`npx tsc --noEmit`、`npx vitest run`、`npm run build`、`npm run lint`。
- Compose smoke：`docker compose config` 后，在测试环境使用随机 `JWT_SECRET` 启动；不使用真实 provider key。

本机 Python/Node 版本可能与 CI 不同；任何“通过”都要注明实际版本。缺少 `JWT_SECRET` 时后端应失败启动，测试必须显式注入临时值，不能添加生产默认 secret。

## 工作流

1. 先读相关规格、计划、实际源文件和同类测试；优先依据 `SPEC-WENJIN-OPEN-SOURCE-EVOLUTION-V2.md` 与 `tasks/plan.md`。
2. 采用薄的垂直切片：先失败测试或契约，再最小实现，再测试、审查和原子提交。
3. 使用 `codex/` 前缀的短期分支；每个提交只做一个逻辑变化，消息使用 `feat/fix/refactor/test/docs/chore`。
4. 修改后运行受影响的最小命令、阶段基线、`git diff --check` 和 staged secret scan；不以删测试、放宽鉴权或真实凭据解决失败。
5. 每个切片报告：改了什么、刻意没改什么、验证结果、未解决风险和回滚方法。

## 安全、隐私与知识边界

- 真实 API key、密码、JWT、OAuth secret、个人身份信息、真实受访者数据和内部部署日志不得写入 Git、前端、URL、响应或日志。
- provider key 只允许存在于后端部署环境或受控 secret manager；前端不能持久化供应商 key。
- 研究资料、访谈、音频、图像、导出文件和数据库默认是敏感数据；上传必须有大小、MIME、路径和内容边界。
- 受保护对象必须同时检查用户身份、项目成员关系、角色和对象归属；不能只依赖前端隐藏按钮。
- LLM 输出是不可信输入，只能给出建议或提案；不能自动改变研究事实、权限、长期记忆、公开材料或 skill。
- 新知识先进入私有审计区。公开仓库只放元数据、短摘要、明确授权内容和结构化模板；不得复制第三方书籍/论文全文、OCR、切片、真实日志或原始研究材料。
- 独立审计代理不能批准自己生成的知识；人工批准和版本哈希完成前，运行时不得加载。

## 代码与文档约定

- 遵循现有 FastAPI router/service/model/schema 结构，避免为了抽象而抽象。
- API 采用稳定错误 envelope、request ID、明确 scope、项目归属、超时和有限重试；第三方响应视为不可信。
- 大型架构决定写入 `docs/decisions/` ADR；公开 API、README、prompt 和 skill 必须说明输入/输出、来源、适用场域、隐私边界和失败条件。
- 不在同一提交混合格式化、无关重构和业务功能；不删除不理解的注释或稳定路径。

## 发布边界

公开推送只有在 G7 发布闸门通过、发布报告完成且项目创建者单独审阅后才能执行。禁止强推覆盖历史、删除私有备份或改变原仓库可见性。未审计知识、密钥、隐私信息、原始材料和部署凭据一律阻塞发布。
