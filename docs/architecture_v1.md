# DevFlow Agent V1 架构说明

这份文档只解释 V1 新增的真实 GitHub Webhook、Header、签名验证和 Delivery 信息。V0 的 FastAPI、Session、事务和迁移基础知识仍可查看 `architecture_v0.md`。

## 1. 什么是 Webhook？

Webhook 是一种“事件发生后主动通知”的 HTTP 调用方式。你先把一个接收地址配置给 GitHub；仓库发生指定事件时，GitHub 会向这个地址发送 HTTP POST 请求。

在本项目中，指定事件是 Pull Request 事件，接收地址是 `/webhooks/github`。

## 2. GitHub 为什么能主动调用我的 FastAPI？

因为你在仓库 Settings 中把 DevFlow 的公网 HTTPS 地址登记为 Payload URL。这个 URL 必须能从互联网访问。GitHub 的服务器在事件发生后向该 URL 发请求，公网入口再把请求交给正在监听的 FastAPI。

本机的 `localhost` 只对本机可见，GitHub 无法直接访问。开发阶段可以临时使用 HTTPS tunnel，把一个公网 HTTPS 地址转发到 `http://localhost:8000`。

## 3. HTTP Header 和 JSON Body 分别是什么？

Header 是请求的元信息。本项目从 Header 读取事件类型、Delivery ID 和签名。JSON Body 是事件内容，本项目从中读取 action、仓库全名和 PR 编号。

可以把它们理解为：Header 说明“这是什么请求、如何验证和追踪”，Body 说明“这次事件具体发生了什么”。

## 4. `X-GitHub-Event` 是什么？

它表示触发本次投递的 GitHub 事件类型。例如 PR 事件的值是 `pull_request`，配置 Webhook 后的测试事件通常是 `ping`。

V1 只处理 `pull_request`，其他已通过签名验证的事件返回 `202 ignored`，不创建 Task。

## 5. `X-GitHub-Delivery` 是什么？

它是 GitHub 为一次事件投递提供的 GUID，用来识别和追踪这次 Delivery。V1 把它保存为 `github_delivery_id`，写入日志，并建立普通数据库索引，方便查询。

V1 只保存 Delivery ID，不用它阻止重复请求，也没有给它增加唯一约束。

## 6. 为什么 Webhook 需要 Secret？

Payload URL 是公网地址，知道地址的人都可以尝试发送请求。Secret 是只在 GitHub Webhook 配置和 DevFlow 环境变量中保存的共享秘密。它不随请求直接发送，而是参与生成签名。

DevFlow 只有在签名正确时才继续处理请求，因此不能只凭“请求打到了正确 URL”就信任它。

## 7. HMAC-SHA256 在这里解决什么问题？

GitHub 使用 Secret 和原始请求 Body 计算 HMAC-SHA256，再把结果放入 `X-Hub-Signature-256`。DevFlow 使用自己的同一份 Secret 和收到的 Body 计算期望值，并用 `hmac.compare_digest()` 做常量时间比较。

两边结果一致，说明发送方持有相同 Secret，并且请求内容在签名后没有被改变。这里不需要自己实现密码学算法，直接使用 Python 标准库即可。

## 8. 为什么必须对原始 Body 验签？

签名针对的是收到的精确 bytes。两个 JSON 即使表达相同数据，只要空格、换行、字段顺序或字符编码不同，bytes 就不同，签名也不同。

因此路由先执行 `await request.body()` 保存原始 bytes，先验签，成功后才让 Pydantic 解析这些 bytes。不能先把 JSON 转成对象再重新序列化后验签。

## 9. 攻击者知道 Payload URL，但不知道 Secret，会发生什么？

攻击者可以向 URL 发请求，但无法为自己构造的 Body 生成正确签名。缺少签名或签名不匹配时，DevFlow 返回 `403 Forbidden`，不会解析 PR 内容，也不会创建 Task。

Secret 本身仍必须妥善保管：不要写进代码、提交到 Git，或输出到日志。

## 10. 真实 PR Event 到 PostgreSQL 的完整数据流

1. 仓库出现 PR `opened`、`synchronize` 或 `reopened` 操作。
2. GitHub 根据 Webhook 配置生成 JSON Body。
3. GitHub 用 Webhook Secret 和原始 Body 计算 HMAC-SHA256 签名。
4. GitHub 向公网 Payload URL 发送 POST；开发环境的 tunnel 将它转发到 FastAPI。
5. FastAPI 读取原始 Body，以及 `X-Hub-Signature-256`、`X-GitHub-Event`、`X-GitHub-Delivery`。
6. DevFlow 使用环境变量中的 Secret 重新计算签名，并做常量时间比较。失败立即返回 `403`。
7. 通过验签后，代码检查 event。非 `pull_request` 返回 `202`。
8. Pydantic 只从真实 payload 解析 action、repository.full_name 和 pull_request.number，多余字段被忽略。
9. 不支持的 PR action 返回 `202`；支持的 action 进入原有 Task 创建流程。
10. SQLAlchemy 将仓库、PR 编号、Delivery ID、event、action 和状态写入 PostgreSQL，事务提交后返回 `201`。
11. 日志中的 Delivery ID、数据库中的 `github_delivery_id` 和 GitHub Recent deliveries 页面可以相互对应。

参考：[GitHub Webhook delivery headers](https://docs.github.com/en/webhooks/webhook-events-and-payloads) 和 [GitHub Webhook 签名验证](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)。
