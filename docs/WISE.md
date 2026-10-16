# WISE 提案与记忆准入

WISE（可审议的微创新与记忆机制）把模型输出和持久化状态分开：模型只能产生候选提案，不能直接写入长期记忆。

## 生命周期

`pending → approved | rejected | revoked`

- `pending`：候选内容、短证据引用和适用范围已保存，等待研究者判断。
- `approved`：只有此状态转换会把 `candidate_memory` 提升到当前用户的 `user_memories`。
- `rejected`：提案被否决，不产生长期记忆。
- `revoked`：待审提案可撤销；已经批准的候选会被降为低置信度（0.1），避免继续作为有效记忆注入。

## API

- `POST /api/v1/wise/proposals`：创建用户提案；请求体严格拒绝未知字段。
- `GET /api/v1/wise/proposals`：仅查看当前 profile 的提案，可用 `?status=pending` 筛选。
- `GET /api/v1/wise/proposals/{id}`：读取自己的提案。
- `POST /api/v1/wise/proposals/{id}/approve`：人工批准并原子化提升候选记忆。
- `POST /api/v1/wise/proposals/{id}/reject`：人工否决。
- `POST /api/v1/wise/proposals/{id}/revoke`：撤销提案或已批准记忆。

所有接口都从认证 profile 推导归属；请求不能通过 `profile_id` 越权。`idempotency_key` 用于重试时复用同一提案。证据字段只接受引用标识，不鼓励把原始访谈全文复制进提案。

## 当前边界

Copilot 和反思流程生成的候选记忆已经进入 WISE 待审区。现有手动记忆编辑/确认接口仍保留，用于用户主动管理已有记忆；它们不代表模型自动批准。多人共同审核、提案分页、跨项目审议和可撤销的完整审计链属于后续协作版本。
