# 知识包准入与运行时导入

问津公开仓库只提供知识导入的边界和验证器，不携带书籍、论文全文、OCR、切片、真实访谈、课程材料或内部日志。新一批中英文社会调查材料目前仍在私有审计区，全部保持 `needs_review`，不会自动进入 runtime。

## 候选材料的分层原则

- A 层优先选择官方调查方法、伦理和数据文档；B 层可作为方法参考但需要逐项确认版权、版本和场域；C 层包括预印本、受限平台内容和仅用于探索的资料。
- 影响因子、引用量、平台规模和“公开可见”只能帮助排序，不能替代权利、隐私、代表性、双语和伦理审计。
- 经典著作、商业教材和论文默认只登记书目、来源链接、作者自写短摘要和限制条件；未获明确授权时不得复制全文、OCR、切片或作为训练数据。
- 公开社会平台不是代表性样本。若候选涉及平台内容，必须记录条款、访问方式、时间窗、抽样偏差、删除传播和去标识化策略；默认只允许最小化的聚合元数据或短时研究读取，不保存用户原文、用户名、私信、截图或可重识别链接。
- 中英文材料分别完成术语、译文、文化适配和场域适用性复核；独立审计代理只能提出结论，不能自行把候选改为 approved。

## 私有包结构

部署者可以把一个未跟踪目录挂载到 `KNOWLEDGE_DIR`：

```text
knowledge-package/
  manifest.json
  approved-cards.json
```

`manifest.json` 必须声明 `wenjin-knowledge/v1`，并同时满足：

- 顶层 `status` 和 `audit_status` 都是 `approved`；
- 有 `approved_by`、`approved_at` 和审计报告引用；
- 每个条目有来源 URL、`license_status=approved`、`privacy_status=public_metadata|redacted`；
- `cards_file` 是包内相对路径，条目未撤销；
- `content_sha256` 与文件实际哈希一致。

验证器只读取 manifest 登记的文件，不会 glob 目录中的其它 JSON。每个 card 还会经过 bounded shape 校验：列表数量、文本长度、`confidence`（1-5）、`source_file` 相对路径、`language`（`zh|en|bilingual`）、`field_context`、`method_tags` 和 `material_type` 必须符合约束；未知字段、明显的 prompt 注入指令、凭据标记和私钥标记会被拒绝。单个卡片文件上限为 5 MiB、5,000 张卡片。没有配置 `KNOWLEDGE_DIR` 时，启动仍可运行，但知识卡片导入返回 `manifest_required`；manifest 或卡片无法通过时返回 `manifest_invalid`，并保留安全的通用 cluster/trigger 初始化。

卡片支持 `reference_card`、`training_example` 和 `prompt_fragment` 三种材料类型。`training_example` 与 `prompt_fragment` 仍然只是部署者已批准包中的受控输入，不代表模型训练授权，也不绕过人工事实/版权/隐私/提示注入审核。建议每个条目明确语言、调查场域和方法标签；运行时不会恢复原书全文、OCR、日志或受访者原始材料。

## 审计顺序

候选收集 → 权利/隐私初筛 → 内容与事实核查 → 中英文/场域校准 → prompt/skill 影响审计 → 独立审计代理 → 项目创建者人工批准 → 生成 approved manifest → 版本化导入。

独立审计代理不能自行把候选改成 approved；批准记录必须能追溯到来源、版本、哈希、适用场域、撤销策略和删除方式。公开仓库只提交 schema、验证器和说明，不提交私有审计报告或第三方材料。
