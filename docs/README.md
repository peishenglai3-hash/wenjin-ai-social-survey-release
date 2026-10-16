# Public documentation

公开文档只记录可复用的架构、接口和运行说明。内部申报、组会汇报、阶段性报告、原始研究记录、第三方全文和个人部署资料不放入本仓库。

发布变更见 [`CHANGELOG.md`](../CHANGELOG.md)，贡献与安全边界见 [`CONTRIBUTING.md`](../CONTRIBUTING.md) 和 [`SECURITY.md`](../SECURITY.md)。完整 README/Markdown 审核登记见 [`MARKDOWN_INVENTORY.md`](MARKDOWN_INVENTORY.md)。

如果要添加样例数据，请使用人工构造或明确获得授权的数据，并在文件头说明来源、许可、脱敏方法和删除方式。

## 可选知识卡片

公开树不包含任何书籍、论文全文、OCR、切片或知识卡片。`backend/app/services/knowledge_ingestion.py` 只接受部署者私有挂载的、经过 `manifest.json` 审计和人工批准的结构化 JSON；没有 manifest、状态不是 `approved`、条目被撤销或哈希不匹配时不会进入 runtime。部署者应先确认 `source_file`、来源、许可和删除策略，不要把第三方全文或其衍生切片直接复制回仓库。详见 [`KNOWLEDGE_INGESTION.md`](KNOWLEDGE_INGESTION.md)。

内置 prompt/skill 的专业边界、调查赋能目标和逐模块校准记录见 [`PROMPT_SKILL_REVIEW.md`](PROMPT_SKILL_REVIEW.md)。

联网整理的中英文候选材料只以元数据登记在 [`KNOWLEDGE_CANDIDATE_REGISTER.md`](KNOWLEDGE_CANDIDATE_REGISTER.md)；所有候选仍为 `needs_review`，不会自动进入 runtime。

## WISE 记忆准入

Copilot/反思产生的候选记忆先进入 `pending` 提案，必须由研究者批准后才会进入长期记忆。生命周期、接口和撤销语义见 [`WISE.md`](WISE.md)。
