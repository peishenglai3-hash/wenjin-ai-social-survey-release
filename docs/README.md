# Public documentation

公开文档只记录可复用的架构、接口和运行说明。内部申报、组会汇报、阶段性报告、原始研究记录、第三方全文和个人部署资料不放入本仓库。

如果要添加样例数据，请使用人工构造或明确获得授权的数据，并在文件头说明来源、许可、脱敏方法和删除方式。

## 可选知识卡片

公开树不包含任何书籍、论文全文、OCR、切片或知识卡片。`backend/app/services/knowledge_ingestion.py` 只接受部署者私有挂载的、经过 `manifest.json` 审计和人工批准的结构化 JSON；没有 manifest、状态不是 `approved`、条目被撤销或哈希不匹配时不会进入 runtime。部署者应先确认 `source_file`、来源、许可和删除策略，不要把第三方全文或其衍生切片直接复制回仓库。详见 [`KNOWLEDGE_INGESTION.md`](KNOWLEDGE_INGESTION.md)。
