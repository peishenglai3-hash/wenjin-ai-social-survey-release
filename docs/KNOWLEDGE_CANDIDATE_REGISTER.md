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

## 新一批公开方法与数据候选（2026-10-16）

以下条目来自官方组织的公开入口或公开服务条款。它们目前只进入登记册，仍是
needs_review；“公开可访问”不等于“允许复制、再分发、训练或跨场域使用”。
高引用量、期刊影响力或平台规模也不自动构成版权、隐私、代表性或伦理批准。

| ID | 语言 | 候选用途 | 官方入口 | 建议材料类型 | 权利/隐私初筛 | 当前状态 |
| --- | --- | --- | --- | --- | --- | --- |
| E22 | en | 调查伦理、透明度、无偏提问与结果披露 | [AAPOR Standards and Ethics](https://aapor.org/standards-and-ethics/) | reference_card | 官方公开入口；具体 PDF 再分发许可待核 | needs_review |
| E23 | en | 人体研究的尊重、受益/不伤害、公正 | [HHS Belmont Report](https://www.hhs.gov/ohrp/regulations-and-policy/belmont-report/index.html) | reference_card | 政府公开材料；版本、适用法域和再利用条件待核 | needs_review |
| E24 | en | 家庭调查规划、实施、非抽样误差与分析 | [UN household survey handbooks](https://unstats.un.org/iswghs/SurveyHandbooksRevision) | reference_card | 官方公开访问；出版物许可和引用要求待核 | needs_review |
| E25 | en | 概率抽样、抽样框、设计效应与误差控制 | [UN sample design handbook](https://unstats.un.org/unsd/demographic-social/Standards-and-Methods/files/Handbooks/surveys/Series_F98-E.pdf) | reference_card | 官方 PDF；不复制全文，许可与摘要边界待核 | needs_review |
| E26 | en | 问卷、样本、现场、数据管理与质量控制 | [World Bank LSMS manual](https://www.worldbank.org/en/programs/lsms/publication/manual-for-planning-and-implementing-the-living-standards-measurement-study-surveys) | reference_card | 公开方法手册；版权、版本和改编条件待核 | needs_review |
| E27 | en | 可验证的调查方法实验、开放指南与质量评估 | [World Bank survey methods](https://www.worldbank.org/en/programs/lsms/priority-themes/survey-methods) | reference_card | 公开方法入口；具体指南许可和场域外推待核 | needs_review |
| E28 | en | 总调查误差、概率面板、问卷设计与公开舆情判断 | [Pew U.S. survey methodology](https://www.pewresearch.org/u-s-survey-methodology/) | reference_card | 公开方法页；不复制报告全文或数据，许可待核 | needs_review |
| E29 | en | 跨国调查规范、抽样、翻译、访员与数据交付 | [European Social Survey specification](https://www.europeansocialsurvey.org/methodology/methodology/ess-specification) | reference_card | 可免费访问部分文档/数据；具体使用条件待核 | needs_review |
| E30 | en | 跨文化价值调查的问卷、技术文档与方法 | [World Values Survey documentation](https://www.worldvaluessurvey.org/WVSContents.jsp?CMSID=Documentation) | reference_card | 数据和文档有使用/引用要求；不将原始数据带入公开 runtime | needs_review |
| E31 | en | 长期社会指标、变量定义、问卷与代码本 | [NORC GSS Data Explorer](https://gssdataexplorer.norc.org/gss_data) | reference_card | 公共访问入口；数据许可、再分发和个人数据边界待核 | needs_review |
| P01 | en | 受限的平台内容治理、删除与 API 研究边界 | [Reddit Data API Terms](https://redditinc.com/policies/data-api-terms?hslang=en) | reference_card | 平台条款约束；用户内容归属用户，禁止无授权 AI 训练；不保存原文 | needs_review |

### 经典著作与高影响论文的处理

- 经典著作、商业出版社教材和高影响论文可以作为书目线索、概念对照和作者自写短摘要，
  但不能因为“经典”“高影响因子”或网上可下载就复制全文、OCR、切片或训练样例。
- reference_card 只允许保存可核验的来源元数据、短摘要、方法标签和限制条件；
  training_example 只允许使用项目作者自有或已获明确授权的内容；
  prompt_fragment 只允许使用项目自写、经过提示注入审计的短模板。
- 对 Braun & Clarke 主题分析、Groves 等调查方法教材、Lazarsfeld/Merton 等经典文本，
  默认采用“书目/链接/短摘要”模式，除非另有明确的开放许可或权利人书面授权。

### 公开社会平台的额外限制

公开平台材料不是代表性调查样本，也不应直接被当作“民意”或“社会事实”。进入
Wenjin 前必须记录平台、访问方式、时间窗、抽样/检索规则、删除传播、去标识化、用户
内容权利和再利用许可。对于 Reddit 等受 API 条款约束的平台，本项目只考虑短时、最小化、
可删除的研究辅助读取或聚合元数据；不把用户原文、用户名、链接串、私信、截图或平台
内容批量写入知识包，也不把它们用于模型训练，除非取得逐项明确授权并完成独立伦理审计。

## 审核记录要求

每个候选进入 approved 前，至少要登记：原始 URL/版本日期、版权与再分发结论、语言和翻译责任、适用场域、方法标签、隐私风险、偏差与限制、审计人、批准人、内容哈希和撤销方式。若只能确认主题而不能确认可再分发权利，保持 `needs_review`。

本登记册不构成法律意见、伦理批准或材料授权证明。
