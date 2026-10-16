# Wenjin 知识候选登记册

状态：`needs_review`。本文件只登记候选材料的主题、来源线索和审核边界，不包含书籍全文、论文全文、OCR、训练切片、日志或私人知识卡片。

## 使用规则

- 候选材料不会自动进入 Wenjin runtime、prompt 或训练集。
- 进入 runtime 前必须完成来源版本、许可、事实、译文、隐私、偏差、场域适配和提示注入审计，并由研究者明确批准。
- 原项目的训练书籍、切片、知识卡片和日志保留在私有备份中；它们不会因本登记册公开而恢复到公开仓库。
- 仅允许部署者将自有或已获授权的结构化卡片放入私有 `KNOWLEDGE_DIR`，并通过 [`KNOWLEDGE_INGESTION.md`](KNOWLEDGE_INGESTION.md) 的 manifest 闸门。

## 优先审核候选

| ID | 语言 | 主题 | 来源线索 | 当前状态 |
| --- | --- | --- | --- | --- |
| E01 | en | 调查职业伦理与最佳实践 | AAPOR Best Practices | needs_review |
| E03 | en | 调查标准定义与质量控制 | AAPOR Standard Definitions | needs_review |
| E08 | en | 定性研究报告规范 | COREQ | needs_review |
| E09 | en | 主题分析方法 | Braun & Clarke | needs_review |
| E11 | en | 混合研究方法 | NIH Mixed Methods | needs_review |
| E12 | en | 跨文化调查与翻译 | Cross-cultural survey guidelines | needs_review |
| E15 | en | 人体研究伦理 | Belmont Report | needs_review |
| E17 | en | 隐私工程与去标识化 | NIST Privacy Framework | needs_review |
| E20 | en | 生成式 AI 与教育/研究治理 | UNESCO GenAI guidance | needs_review |
| E21 | en | 可信与负责任 AI | EU responsible AI guidance | needs_review |
| C01 | zh | 个人信息保护与最小化 | 中国个人信息保护法 | needs_review |
| C03 | zh | 科研伦理审查 | 中国科研伦理审查相关规范 | needs_review |
| C09 | zh | 统计调查质量与管理 | 中国统计调查相关规范 | needs_review |
| C13 | zh | 混合研究与调查设计 | 中文方法学资料候选 | needs_review |

## 审核记录要求

每个候选进入 approved 前，至少要登记：原始 URL/版本日期、版权与再分发结论、语言和翻译责任、适用场域、方法标签、隐私风险、偏差与限制、审计人、批准人、内容哈希和撤销方式。若只能确认主题而不能确认可再分发权利，保持 `needs_review`。

本登记册不构成法律意见、伦理批准或材料授权证明。
