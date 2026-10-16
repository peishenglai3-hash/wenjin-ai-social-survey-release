# 协作研究模式 V1（当前实现范围）

V1 采用显式保存和成员关系，不实现实时共同编辑。首轮实现只管理项目协作元数据，不复制访谈文本、音频、受访者信息或其它原始研究材料。

## 已实现

- 项目 owner/member 数据模型与迁移；历史项目迁移时自动补齐 owner 行。
- `owner`、`editor`、`reviewer`、`viewer` 角色；owner 可以邀请已有账户的 profile。
- 邀请的 pending/accepted/rejected 状态；重复 pending 邀请返回同一邀请，提供首轮幂等语义。
- 成员角色调整与移除；owner 不能被降级或移除。
- 项目级元数据审计事件；事件只记录 profile/id、动作和角色等元数据。
- 双用户测试覆盖：非成员无法读取或管理他人项目，受邀用户可接受邀请并获得声明角色。

## C2 已实现：显式研究产物协作

- `research_artifacts`：项目内的产物键、类型和标题；旧的单人核心表不会被自动改成共享表。
- `research_artifact_versions`：显式版本号、脱敏内容、内容哈希、变更说明和幂等键。
- `research_annotations`：成员可以针对脱敏版本留下带可选字符范围的批注。
- `research_review_tasks`：编辑请求审核，reviewer/editor/owner 按角色完成批准、退回修改或拒绝。
- `research_shares`：只有已经批准且标记为 `redacted` 的版本可以创建短期分享；令牌只返回一次、数据库只保存摘要，解析令牌使用 POST body 而不是 URL。
- 明显的邮箱、手机号、API key、Bearer token 和私钥标记会在版本/批注提交时被拒绝；这不是完整的隐私识别器，研究者仍需人工复核。
- 前端协作工作台已提供成员元数据和研究产物创建的最小闭环；入口默认由 `VITE_COLLABORATION_V1_ENABLED=false` 关闭，启用前应先完成部署者的权限、脱敏和保留策略审阅。

对应接口在受认证的 `/api/v1/collaboration` 下：

- `POST/GET /projects/{project_id}/artifacts`
- `GET /artifacts/{artifact_id}`
- `POST/GET /artifacts/{artifact_id}/versions`
- `GET /versions/{version_id}`
- `POST/GET /versions/{version_id}/annotations`
- `POST/GET /versions/{version_id}/review-tasks`
- `POST /review-tasks/{task_id}/decision`
- `POST /versions/{version_id}/shares`
- `POST /shares/resolve`、`POST /shares/{share_id}/revoke`

端点位于受认证的 `/api/v1/collaboration` 下：

- `GET /projects/{project_id}/members`
- `POST /projects/{project_id}/invitations`
- `GET /invitations`
- `POST /invitations/{invitation_id}/accept`
- `POST /invitations/{invitation_id}/reject`
- `PATCH /projects/{project_id}/members/{member_id}`
- `DELETE /projects/{project_id}/members/{member_id}`
- `GET /projects/{project_id}/audit`

## 安全与实时边界

协作 API 只接受登录后的 access token；研究产物分享令牌只通过一次性响应返回，服务端保存摘要。田野实时 WebSocket 是独立的认证入口，不等同于实时协作编辑：客户端必须通过 `bearer` 子协议提交内存 access token，服务端不会从 URL 查询参数读取 token。

## 尚未实现

列表接口已经支持 `limit`/`offset`（默认 50、最大 100），并返回 `pagination.has_more` 和 `next_offset`；分页不是权限边界，服务端仍会先执行项目成员检查。批量审核、跨项目审议和完整统一错误 envelope 尚未完成；研究产物保留/删除策略仍需在进入生产部署前单独确定。现有旧单人核心路由仍保持 owner-scoped 语义，协作成员不会因为本模块启用而自动获得旧数据访问权；当前版本也不实现实时共同编辑。
