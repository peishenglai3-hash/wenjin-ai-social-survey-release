# 协作研究模式 V1（当前实现范围）

V1 采用显式保存和成员关系，不实现实时共同编辑。首轮实现只管理项目协作元数据，不复制访谈文本、音频、受访者信息或其它原始研究材料。

## 已实现

- 项目 owner/member 数据模型与迁移；历史项目迁移时自动补齐 owner 行。
- `owner`、`editor`、`reviewer`、`viewer` 角色；owner 可以邀请已有账户的 profile。
- 邀请的 pending/accepted/rejected 状态；重复 pending 邀请返回同一邀请，提供首轮幂等语义。
- 成员角色调整与移除；owner 不能被降级或移除。
- 项目级元数据审计事件；事件只记录 profile/id、动作和角色等元数据。
- 双用户测试覆盖：非成员无法读取或管理他人项目，受邀用户可接受邀请并获得声明角色。

端点位于受认证的 `/api/v1/collaboration` 下：

- `GET /projects/{project_id}/members`
- `POST /projects/{project_id}/invitations`
- `GET /invitations`
- `POST /invitations/{invitation_id}/accept`
- `POST /invitations/{invitation_id}/reject`
- `PATCH /projects/{project_id}/members/{member_id}`
- `DELETE /projects/{project_id}/members/{member_id}`
- `GET /projects/{project_id}/audit`

## 尚未实现

研究产物版本、批注、审核任务、可撤销脱敏分享、删除/保留策略、分页和完整统一错误 envelope 尚未完成。现有旧单人核心路由仍保持 owner-scoped 语义，协作成员不会因为本模块启用而自动获得旧数据访问权。
