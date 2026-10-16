# 知识包准入与运行时导入

问津公开仓库只提供知识导入的边界和验证器，不携带书籍、论文全文、OCR、切片、真实访谈、课程材料或内部日志。新一批中英文社会调查材料目前仍在私有审计区，全部保持 `needs_review`，不会自动进入 runtime。

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

验证器只读取 manifest 登记的文件，不会 glob 目录中的其它 JSON。没有配置 `KNOWLEDGE_DIR` 时，启动仍可运行，但知识卡片导入返回 `manifest_required`；manifest 无法通过时返回 `manifest_invalid`，并保留安全的通用 cluster/trigger 初始化。

## 审计顺序

候选收集 → 权利/隐私初筛 → 内容与事实核查 → 中英文/场域校准 → prompt/skill 影响审计 → 独立审计代理 → 项目创建者人工批准 → 生成 approved manifest → 版本化导入。

独立审计代理不能自行把候选改成 approved；批准记录必须能追溯到来源、版本、哈希、适用场域、撤销策略和删除方式。公开仓库只提交 schema、验证器和说明，不提交私有审计报告或第三方材料。
