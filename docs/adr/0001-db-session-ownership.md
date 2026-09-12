# ADR 0001:数据库会话的所有权与事务边界

日期:2026-09-12 · 状态:已采纳

## 决定

1. **HTTP 请求路径**:会话由 FastAPI 依赖注入(`database.get_db`)创建与关闭,
   一个请求 = 一个会话;事务边界在 service 层的提交点,router 不开启新事务。
2. **后台/启动路径**(job 循环、启动恢复、settings 存储、向量嵌入等):允许且应当
   用 `async_session()` 自建会话——这些路径没有请求上下文。当前共 8 处:
   `chapter_publish`、`character_branch_generation`、`settings_store`、
   `worker_admin_service`、`runtime_tunables_service`、`startup_recovery`、
   `vector_embeddings`、`orphan_cleaner`。
3. **新增后台写入路径时**:必须在本 ADR 追加登记,并说明该路径的提交时机
   (每 job 一提交 / 每阶段 checkpoint,参考 `character_branch_generation`
   的 checkpoint 模式与 `knowledge_merger` 的单次发布提交)。
4. **禁止**:在只读辅助函数(recall、格式化、投影)里做写操作——写入必须
   属于一个明确的、有提交点的所有权路径(反例教训见森林文档树 D)。

## 后果

- 会话泄漏只可能发生在自建会话路径,review 时按本清单核对。
- 读路径的幂等/降级承诺(召回失败回空)与写路径的提交点互不干扰。
