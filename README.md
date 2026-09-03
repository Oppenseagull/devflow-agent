# DevFlow Agent V0

DevFlow Agent 的 V0 是一个最小后端：它接收一份模拟 GitHub Pull Request Webhook，创建 Task，按确定性顺序更新状态，并允许查询结果。

当前范围只有 FastAPI、PostgreSQL、SQLAlchemy、Pydantic、pytest、Docker 和 Docker Compose。V0 不连接真实 GitHub，也不包含智能决策或后台任务系统。

## 目录结构

```text
app/
  config.py       # 环境变量配置
  database.py     # 数据库引擎、Session 和依赖
  main.py         # FastAPI 应用和三个 API
  models.py       # SQLAlchemy Task 表模型
  schemas.py      # 请求与响应的数据校验模型
  service.py      # 创建 Task 和更新状态的业务流程
migrations/       # Alembic 数据库迁移
tests/            # API 测试
docs/             # 架构与面试学习材料
compose.yaml      # API + PostgreSQL
Dockerfile        # API 镜像构建方式
```

## 最快运行方式：Docker Compose

前提：安装并启动 Docker Desktop。

```bash
docker compose up --build
```

API 启动时会先执行 `alembic upgrade head`，创建 `tasks` 表，然后监听 <http://localhost:8000>。

验证健康状态：

```bash
curl http://localhost:8000/health
```

发送模拟 Webhook：

```bash
curl -X POST http://localhost:8000/webhooks/github \
  -H "Content-Type: application/json" \
  --data-binary @examples/github_pr_opened.json
```

如果在 PowerShell 中 `curl` 被映射成其他命令，可以使用 `curl.exe` 执行同一命令。

响应中的 `id` 可用于查询：

```bash
curl http://localhost:8000/tasks/<task_id>
```

交互式接口文档位于 <http://localhost:8000/docs>。

停止容器：

```bash
docker compose down
```

如果还要删除本项目的数据库数据卷，可明确执行 `docker compose down -v`。这会删除已经创建的 Task 数据。

## 本地开发运行

前提：Python 3.12 和一个可访问的 PostgreSQL。

1. 创建虚拟环境并安装依赖：

   ```bash
   python -m venv .venv
   # PowerShell
   .venv\Scripts\Activate.ps1
   pip install -r requirements-dev.txt
   ```

2. 从示例创建 `.env`，并按实际数据库修改 `DATABASE_URL`：

   ```powershell
   Copy-Item .env.example .env
   ```

3. 执行迁移并启动 API：

   ```bash
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

## 运行测试

```bash
pytest -q
```

测试通过 FastAPI 的依赖覆盖使用内存 SQLite，因此运行 API 测试时不必启动 PostgreSQL。生产运行路径仍使用 PostgreSQL；数据库迁移应在 PostgreSQL 上执行。

## 配置

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `APP_NAME` | `DevFlow Agent API` | OpenAPI 中的应用名称 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `DATABASE_URL` | 本地 devflow PostgreSQL 地址 | SQLAlchemy 数据库连接地址 |

## 数据库变更方式

不要在应用启动时调用 `create_all()` 修改生产表结构。模型变化后，应生成并检查一条 Alembic 迁移，再执行迁移：

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

V0 已包含第一条创建 `tasks` 表的迁移。
