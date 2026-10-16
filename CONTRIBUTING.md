# Contributing to Wenjin

感谢参与问津。请先阅读 [`AGENTS.md`](AGENTS.md)、[`SECURITY.md`](SECURITY.md)、[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) 和 [`docs/KNOWLEDGE_INGESTION.md`](docs/KNOWLEDGE_INGESTION.md)。

## 基本边界

- 不提交 API key、密码、JWT/OAuth secret、真实受访者资料、生产日志、数据库、音频、照片或未获再许可的书籍/论文全文、OCR、切片和知识卡片。
- 新知识先登记和审计，不能把候选材料直接放进公开 runtime；只有明确批准的结构化包才能由部署者私有挂载。
- AI 输出是候选建议，不得自动确认研究结论、权限、长期记忆或公开材料。
- 协作 V1 不实现实时共同编辑；第三方技能保持 prompt-only 声明式边界，不执行仓库外代码。

## 提交前检查

```text
cd backend
python -m pytest tests/ -v --tb=short
python -m compileall -q app
python -m alembic upgrade head
python -m alembic check

cd ../frontend
npx tsc --noEmit
npm test
npm run build
```

同时运行 `git diff --check`，检查当前树和 Git 历史中的高置信度凭据模式，并确认新增文档的相对链接可用。不要用真实 provider key 运行提交前测试。

## Pull request 要求

说明改动范围、未改动的稳定路径、权限/隐私边界、迁移与回滚方式、实际命令和结果。涉及数据库、公开 API、知识材料、认证、上传或发布流程时，先补规格/ADR 和拒绝路径测试。公开发布需要维护者完成发布报告并单独批准，不能由自动化代理自行推送。
