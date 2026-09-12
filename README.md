# DevFlow Agent V1

DevFlow Agent V1 是一个最小的研发事件接收后端：它验证真实 GitHub Pull Request Webhook 的签名，将事件转换为 Task，保存到 PostgreSQL，并提供 Task 查询接口。

V1 支持的 GitHub PR action：

- `opened`
- `synchronize`
- `reopened`

其他 GitHub event 或 PR action 在通过签名验证后返回 `202 ignored`，不会创建 Task。V1 保存 Delivery ID，但暂不实现重复投递处理。

## 目录结构

```text
app/
  config.py       # 环境变量配置
  database.py     # SQLAlchemy Engine、Session 和依赖
  github.py       # HMAC-SHA256 签名验证
  main.py         # FastAPI 路由、Header 读取和请求处理
  models.py       # SQLAlchemy Task 表模型
  schemas.py      # 请求与响应的数据模型
  service.py      # Task 创建和状态变化
migrations/       # V0 建表迁移与 V1 增量迁移
tests/            # API、签名和持久化测试
docs/             # V0/V1 架构与面试学习材料
examples/         # 最小 PR payload 示例
```

## API

| 方法与路径 | 作用 |
| --- | --- |
| `POST /webhooks/github` | 接收并验证 GitHub Webhook |
| `GET /tasks/{task_id}` | 按 ID 查询 Task |
| `GET /tasks` | 查询最新 20 个 Task |
| `GET /health` | 检查 API 与数据库连接 |

## 使用 Docker Compose 从零运行

前提：安装并启动 Docker Desktop。

1. 创建本地环境变量文件：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 生成一个随机 Secret：

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

3. 把输出写入 `.env`：

   ```text
   GITHUB_WEBHOOK_SECRET=你的随机字符串
   ```

   `.env` 已被 Git 忽略。不要把真实 Secret 提交到仓库、写入代码或发给其他人。

4. 构建并启动 API 与 PostgreSQL：

   ```bash
   docker compose up --build
   ```

   API 容器会先执行 `alembic upgrade head`，依次应用 V0 和 V1 迁移，然后监听 <http://localhost:8000>。

5. 检查服务：

   ```bash
   curl.exe http://localhost:8000/health
   ```

   预期响应：

   ```json
   {"status":"ok","database":"reachable"}
   ```

停止服务使用 `docker compose down`。只有明确希望删除本地 Task 数据时才使用 `docker compose down -v`。

## 本地 Python 运行

前提：Python 3.12 和一个可访问的 PostgreSQL。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

修改 `.env` 中的 `DATABASE_URL` 和 `GITHUB_WEBHOOK_SECRET`，然后运行：

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

交互式 API 文档位于 <http://localhost:8000/docs>。

## 将本地服务暴露给 GitHub

GitHub 无法访问你电脑上的 `localhost`。开发测试可以安装独立的 `cloudflared`，然后开启一个临时 HTTPS Quick Tunnel：

```bash
cloudflared tunnel --url http://localhost:8000
```

命令会显示一个类似 `https://random-name.trycloudflare.com` 的临时地址。`cloudflared` 只是本地开发辅助工具，不属于本项目依赖，也不写入 Docker Compose。

Quick Tunnel 只适合临时测试。停止并重新启动后 URL 可能变化，此时需要同步更新 GitHub Webhook 的 Payload URL。官方说明见 [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/setup/#quick-tunnels-development)。

## 在 GitHub Repository Settings 添加 Webhook

你需要拥有目标仓库的管理员权限。

1. 打开目标 GitHub 仓库。
2. 进入 **Settings → Webhooks → Add webhook**。
3. **Payload URL** 填：

   ```text
   https://你的-tunnel-域名/webhooks/github
   ```

4. **Content type** 选择 `application/json`。
5. **Secret** 填入与本地 `.env` 中 `GITHUB_WEBHOOK_SECRET` 完全相同的字符串。不要包含变量名、引号或额外空格。
6. 在 **Which events would you like to trigger this webhook?** 中选择 **Let me select individual events**，只勾选 **Pull requests**。
7. 保持 **Active** 选中，然后点击 **Add webhook**。

GitHub 创建 Webhook 后会自动发送一次 `ping`。DevFlow 验签成功后会返回 `202 ignored`；这是正常结果，因为 V1 只为 Pull Request event 创建 Task。GitHub 官方配置步骤见 [Creating webhooks](https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks)。

## 触发并确认一次真实 PR Webhook

可以用以下任一操作触发受支持的 action：

- 新建 PR：`opened`
- 向已打开 PR 的源分支 push 新 commit：`synchronize`
- 重新打开已关闭的 PR：`reopened`

确认路径：

1. 在 GitHub 仓库 **Settings → Webhooks → 你的 Webhook → Recent deliveries** 中打开最新 Delivery。
2. 确认 event/action 正确，Payload URL 正确，响应状态为 `201`。
3. 记下 Request Headers 中的 `X-GitHub-Delivery`。
4. 查看 API 日志，搜索同一个 Delivery ID：

   ```bash
   docker compose logs api
   ```

5. 查询最新 Task：

   ```bash
   curl.exe http://localhost:8000/tasks
   ```

6. 也可以直接检查 PostgreSQL：

   ```bash
   docker compose exec db psql -U devflow -d devflow -c "SELECT id, repository, pr_number, github_delivery_id, github_event, github_action, status FROM tasks ORDER BY created_at DESC LIMIT 5;"
   ```

Task 中的 `github_delivery_id` 应与 GitHub Recent deliveries 和 API 日志完全一致。

## Webhook 响应规则

| 情况 | HTTP 状态 | 是否创建 Task |
| --- | --- | --- |
| 合法签名 + 支持的 PR action | `201` | 是 |
| 合法签名 + 非 PR event | `202` | 否 |
| 合法签名 + 不支持的 PR action | `202` | 否 |
| Header 缺少 event 或 Delivery ID | `400` | 否 |
| 签名缺失或错误 | `403` | 否 |
| Secret 未配置 | `503` | 否 |
| 数据库不可用 | `503` | 否 |

签名必须基于原始 HTTP body bytes。实现使用 Python 标准库的 HMAC-SHA256 和 `hmac.compare_digest()`；详见 [GitHub 官方验签说明](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)。

## 运行测试

```bash
pytest -q
```

测试通过 FastAPI 依赖覆盖使用内存 SQLite，不要求本机启动 PostgreSQL。测试会根据每次发送的原始 Body 和测试 Secret 真实计算签名。

## 配置

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `APP_NAME` | `DevFlow Agent API` | OpenAPI 应用名称 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `DATABASE_URL` | 本地 devflow PostgreSQL 地址 | SQLAlchemy 数据库连接地址 |
| `GITHUB_WEBHOOK_SECRET` | 空 | GitHub Webhook 验签 Secret；真实接收前必须设置 |

## 数据库迁移

V1 没有修改 V0 迁移，而是新增 `20260912_0002`：

- 增加可空的 `github_delivery_id`、`github_event`、`github_action`，兼容已有 V0 数据。
- 为 `github_delivery_id` 建普通索引，便于追踪。
- 暂不增加唯一约束，也不阻止重复 Delivery。

执行迁移：

```bash
alembic upgrade head
```

## 学习材料

- [V0 架构说明](docs/architecture_v0.md)
- [V0 面试问答](docs/interview_v0.md)
- [V1 架构说明](docs/architecture_v1.md)
- [V1 面试问答与两个练习](docs/interview_v1.md)

## V1 Completion Checklist

- [ ] `pytest -q` 自动测试全部通过。
- [ ] `docker compose up --build` 能正常启动 API 与 PostgreSQL，`/health` 返回 `200`。
- [ ] GitHub Repository Webhook 已使用 HTTPS Payload URL、`application/json` 和 Pull requests event。
- [ ] GitHub 与 DevFlow 配置了完全相同的 Secret。
- [ ] GitHub 真正发送过一次 `opened`、`synchronize` 或 `reopened` Webhook，并收到 `201`。
- [ ] 合法签名能够创建 Task。
- [ ] 缺失或非法签名会收到 `403`，且不会创建 Task。
- [ ] PostgreSQL 中存在由真实 GitHub 事件生成的 Task。
- [ ] Task 正确保存 `github_delivery_id`、`github_event` 和 `github_action`。
- [ ] 能用 Delivery ID 在 GitHub Recent deliveries、API 日志和 PostgreSQL 中找到同一次事件。
- [ ] 已亲自完成 `docs/interview_v1.md` 中的两个小练习。

以上全部打勾后，V1 才算真正完成。
