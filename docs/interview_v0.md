# DevFlow Agent V0 面试问答

## 1. 这个项目当前完成了什么？

它接收模拟 GitHub PR Webhook，创建并持久化 Task，按固定顺序把状态更新为 `COMPLETED`，并提供健康检查和按 ID 查询接口。

## 2. 为什么选择 FastAPI？

它能直接用 Python 类型和 Pydantic 模型完成请求校验、响应序列化，并自动生成接口文档，适合快速构建清晰的 HTTP API。

## 3. Pydantic 模型和 SQLAlchemy 模型有什么区别？

Pydantic 模型定义接口输入输出并校验数据；SQLAlchemy 模型定义 Python 对象如何映射到数据库表。前者面向 API 边界，后者面向持久化。

## 4. SQLAlchemy Session 是什么？

Session 是应用与数据库交互的工作单元，用于查询、添加、修改对象以及提交或回滚事务。本项目为每个请求提供一个 Session，并在请求结束后关闭。

## 5. `flush()` 和 `commit()` 有什么区别？

`flush()` 把当前变更发送到数据库，但事务还没最终提交；`commit()` 才确认事务，使变更持久生效。本项目第一次 flush 后可以取得新 Task 的 ID，最后统一 commit。

## 6. 为什么需要 Alembic？

数据库表结构会随代码变化。Alembic 用版本化迁移记录每次结构变更，让不同环境能够按相同步骤升级或回退，而不是手工改表。

## 7. Webhook 请求格式错误时会怎样？

FastAPI 和 Pydantic 会在进入业务函数前完成校验，并返回 `422 Unprocessable Entity`。例如仓库名为空或 PR 编号不大于零都会失败。

## 8. 查询不存在的 Task 为什么返回 404？

请求本身格式正确，但对应资源不存在。HTTP 的 `404 Not Found` 能准确表达这个结果，调用者也可以据此区分输入校验失败和资源不存在。

## 9. 数据库不可用时系统怎样响应？

SQLAlchemy 抛出的数据库异常会被统一转换为 `503 Service Unavailable`，内部错误写入日志。创建 Task 失败时还会回滚当前事务。

## 10. 当前测试验证了哪些行为？

测试验证数据库健康检查、Webhook 创建 Task、最终状态、按 ID 查询、查询不存在资源以及非法 Webhook 输入。测试通过依赖覆盖使用隔离的内存数据库。

## 必须由你本人完成的 3 个练习

### 练习一：添加 `event_type` 字段

目标：让 Task 保存事件类型，并从 Webhook JSON 的 `action` 字段读取它。

必要提示：需要同时修改 SQLAlchemy 模型、Pydantic payload/响应、业务函数、Alembic 迁移和测试。不要直接改已有迁移；新增一条迁移。完成后观察旧数据的字段应如何处理。

### 练习二：新增 Task 列表 API

目标：实现 `GET /tasks`，返回按 `created_at` 从新到旧排列的 Task，第一版最多返回 20 条。

必要提示：用 SQLAlchemy 的 `select()`、`order_by()` 和 `limit()`；为“没有 Task”写一个测试，确认应返回空列表而不是 404。

### 练习三：制造并排查数据库连接错误

目标：把本地 `.env` 中的 PostgreSQL 端口暂时改成错误端口，调用 `/health`，根据 HTTP 响应和服务日志解释故障发生在哪一层。

必要提示：预期客户端看到 `503`，日志中应有连接失败原因。排查后恢复正确端口并再次调用 `/health`。不要修改异常处理代码来掩盖错误。

