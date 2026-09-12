# DevFlow Agent V1 面试问答

## 1. 什么是 Webhook？本项目怎样使用它？

Webhook 是事件发生后由外部系统主动发起的 HTTP 通知。GitHub 在 PR 打开、更新提交或重新打开时，向 DevFlow 的 `POST /webhooks/github` 发送事件。

## 2. Header 和 Body 在 GitHub Webhook 中分别保存什么？

Header 保存事件类型、Delivery ID 和签名等请求元信息；JSON Body 保存 action、仓库、PR 等事件数据。本项目从两部分提取不同信息。

## 3. Webhook Secret 和签名有什么作用？

Secret 由 GitHub 配置和服务端共同持有。GitHub 用它为请求 Body 生成签名，服务端重新计算并比较签名，用来判断发送方是否持有同一 Secret，以及 Body 是否被修改。

## 4. V1 如何执行 HMAC 验签，为什么使用原始 Body？

V1 用 Secret 和原始 Body bytes 计算 HMAC-SHA256，并通过 `hmac.compare_digest()` 与 `X-Hub-Signature-256` 比较。签名针对精确 bytes，重新序列化 JSON 会改变 bytes，所以必须先读取并验证原始 Body。

## 5. `X-GitHub-Delivery` 有什么价值？

它是一次 GitHub 事件投递的 GUID。V1 将它写入 Task 和日志，使开发者能在 GitHub、应用日志和数据库之间定位同一次事件；V1 暂不利用它阻止重复投递。

## 两个必须亲手完成的练习

### 练习一：证明签名依赖原始 bytes（10–20 分钟）

目标：新增一个测试，先为某段 JSON bytes 计算合法签名，然后只改变 Body 的一个空格或换行，仍使用旧签名发送，确认接口返回 `403` 且没有创建 Task。

必要提示：JSON 解析后的数据可以完全相同，但 HMAC 的输入 bytes 已经不同。复用测试中的签名辅助函数，不要写死签名。

### 练习二：补齐 Delivery Header 边界测试（10–20 分钟）

目标：新增一个测试，发送签名正确、event 正确，但缺少 `X-GitHub-Delivery` 的请求，确认返回 `400` 且数据库中没有 Task。

必要提示：先生成完整 headers，再移除目标 Header；最后调用 `GET /tasks` 验证空列表。不要修改生产代码来迎合错误预期。

