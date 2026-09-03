# DevFlow Agent V0 架构说明

这份说明面向刚开始学习后端的开发者。先记住一句话：API 负责接收和回答请求，业务代码负责决定做什么，数据库负责可靠地保存结果。

## 1. 这个系统解决了什么问题

研发协作中，一次 Pull Request 可能触发检查、记录和发布准备。V0 只模拟其中最小的一段：收到 PR 事件后创建一条 Task 记录，并把它从 `RECEIVED` 更新到 `PROCESSING`，最后到 `COMPLETED`。随后调用者可以用 Task ID 查询结果。

V0 的重点不是自动完成真实研发工作，而是搭好一个可运行、可测试、可解释的后端基础。

## 2. FastAPI 负责什么

FastAPI 是程序的 HTTP 入口，主要负责：

- 把 URL 和 HTTP 方法映射到 Python 函数，例如 `POST /webhooks/github`。
- 使用 Pydantic 检查请求 JSON 是否符合格式。
- 调用业务函数，并把返回对象转换成 JSON 响应。
- 生成 `/docs` 交互式接口文档。
- 把“Task 不存在”“数据库不可用”等情况转换成合适的 HTTP 状态码。

FastAPI 本身不长期保存 Task。应用进程重启后，内存中的普通变量会消失，所以持久数据交给 PostgreSQL。

## 3. PostgreSQL 负责什么

PostgreSQL 保存 `tasks` 表。每一行代表一个 Task，包括 ID、仓库名、PR 编号、状态和时间。只要数据库数据卷还在，重启 API 不会丢失这些记录。

SQLAlchemy 在 Python 对象和数据库表之间做映射；Alembic 则记录表结构如何随版本演进。它们用途不同：SQLAlchemy 用于日常读写数据，Alembic 用于改变数据库结构。

## 4. 一次 Webhook 请求经历了什么

1. 客户端向 `POST /webhooks/github` 发送 JSON。
2. FastAPI 根据 `GitHubWebhookPayload` 校验仓库名和 PR 编号。格式错误时直接返回 `422`。
3. `get_db()` 为这次请求提供一个 SQLAlchemy Session。Session 可以理解为本次数据库工作的操作窗口。
4. 路由函数调用 `create_task_from_webhook()`。
5. 业务函数创建状态为 `RECEIVED` 的 Task，并用 `flush()` 把待执行 SQL 发到数据库，让 Task 获得 ID。
6. 业务函数把状态依次改为 `PROCESSING` 和 `COMPLETED`。
7. `commit()` 提交整个事务。提交成功后，最终状态永久保存为 `COMPLETED`。
8. `refresh()` 从数据库重新读取这条记录，取得数据库生成的时间字段。
9. FastAPI 按 `TaskRead` 的格式返回 `201 Created` 和 Task JSON。

这里三个状态发生在同一个同步请求和同一个事务中。外部通常只能看到最终的 `COMPLETED`，这是有意保持简单的 V0 设计。

## 5. 每个主要文件负责什么

- `app/main.py`：创建 FastAPI 应用，定义三个路由和数据库异常响应。
- `app/config.py`：从环境变量或 `.env` 读取应用配置。
- `app/database.py`：创建 SQLAlchemy Engine、Session，并向路由提供 Session。
- `app/models.py`：定义 `tasks` 表和允许的状态名称。
- `app/schemas.py`：定义请求 JSON 和响应 JSON 的形状及校验规则。
- `app/service.py`：承载“创建 Task 并更新状态”这段业务逻辑。
- `migrations/versions/...create_tasks.py`：可重复执行的第一版建表步骤。
- `tests/conftest.py`：建立隔离的测试数据库并替换 API 的数据库依赖。
- `tests/test_api.py`：验证健康检查、创建、查询、404 和输入校验。
- `Dockerfile`：描述如何把 API 打包成容器镜像。
- `compose.yaml`：一起启动 API 和 PostgreSQL，并配置它们之间的连接。

## 6. 为什么采用当前目录结构

V0 文件不多，因此没有拆成许多层级。路由入口、数据模型、输入输出模型、数据库连接和业务流程仍然分开，避免所有代码挤在一个文件里。

这个结构的判断标准是“每个文件有一个容易说清楚的职责”。它既方便初学者顺着请求路径阅读，也为以后增加少量功能留下空间，但没有提前创建当前用不到的抽象层。

## 7. PostgreSQL 不可用时会发生什么

API 进程不一定立即退出，但任何需要数据库的接口都会连接失败：

- `/health` 返回 `503 Service Unavailable`。
- 创建或查询 Task 也返回 `503`，响应内容为 `Database is unavailable`。
- 服务端日志会记录完整数据库异常，便于排查；响应不会把内部连接信息暴露给客户端。
- Webhook 创建失败时会执行 `rollback()`，撤销本次未提交的数据库操作。

在 Compose 中，API 会等待 PostgreSQL 健康检查通过后启动；但数据库在运行期间仍可能断开，因此应用层异常处理依然必要。

## 8. 当前 V0 的明显缺陷

- Webhook 没有校验 GitHub 签名，任何人都能模拟请求。
- 只读取 payload 中两个字段，没有区分 PR 的打开、更新或关闭动作。
- 同一 PR 重复发送会创建重复 Task，没有幂等处理。
- 状态变化全部在一次请求中完成，无法看到中间状态，也没有实际处理工作。
- 如果处理逻辑失败，没有 `FAILED` 状态或失败原因字段。
- 没有鉴权、分页查询、Task 列表和删除能力。
- 测试使用 SQLite，能快速验证 API 逻辑，但不能覆盖所有 PostgreSQL 方言差异。
- 日志只有基础文本，没有请求 ID 等关联信息。

这些是刻意保留的边界，而不是遗漏：先理解一条最短链路，再逐步改进。

## 9. 下一阶段为什么可能需要接真实 GitHub

本地 mock JSON 只能证明自己的接口逻辑能运行，不能证明系统能正确接收 GitHub 的真实请求。连接真实 GitHub 后，才能验证真实 payload 结构、事件类型、请求头、Webhook 签名、重复投递和网络失败等实际情况。

下一阶段接 GitHub 的合理目标应是“可靠接收并验证真实事件”，而不是立刻增加更多复杂技术。

