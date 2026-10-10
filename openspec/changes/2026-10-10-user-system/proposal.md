# 变更提案：用户系统扩展（账号-数据打通 / 管理页 / 按用户画像与个性化）

日期：2026-10-10 · 状态：功能已落地（文件存储）；存储层将迁移至 MySQL（NFR-01 零依赖约束已于 2026-10-11 经用户正式解除，待开工）

## 背景

需求说明书 v1.0 将 FR-04（跨对话记忆与用户档案）/ FR-18（多用户隔离与账号体系）
标为「已落地」。实测（读源码核实）属于「后端真落地、前端断链、数据隔离半成品」：

1. 账号后端完整（`server/accounts.py`：PBKDF2 + HMAC token + 双角色 + 注册开关），
   6 条路由齐备；但 **前端 `client.js` 没有 `me/login/register` 方法**，
   `useAuth.js` 调用即抛 TypeError —— 登录 UI 实际不可用；
   `request()` 默认不带 `X-Auth-Token`，SSE 也不带 token。
2. 管理接口 `/api/accounts` 无任何前端调用（管理页缺失）。
3. 普通用户无自改密码。
4. 学习画像全局共享单个 `profile.json`（vendor `load_profile/save_profile`
   本身支持 filepath 参数，只是没人传）。
5. 历史 / 进度 / 错题本 / 导图全部按随机浏览器 ID（X-Client-Id）存取，与账号无关。

## 决策

- **学习数据上服务端、个性化小状态留浏览器**（混合方案不变）：
  账号、画像、历史、进度、错题本、导图等**关系型数据统一迁入 MySQL**（不再用纯文本 JSON 文件）；
  宠物、自习设置（音乐/音量/场景）仍按账号分档存 localStorage（零服务器成本）。
- **不用 SQLite，用 MySQL**：项目要长期保存大量关系型数据（错题、进度、导图、跨账号聚合查询），
  服务端是多线程 `ThreadingHTTPServer`，并发读写频繁；MySQL 在并发写入、关系查询
  （按课程/标签/掌握状态过滤、聚合统计）、横向扩展上明显优于 SQLite 的单写者锁模型。选用 **MySQL 8.x（utf8mb4）**。
- **存储层抽离到 `server/` 新模块**：MySQL 访问集中在一个新建的 `server/db.py`（连接池 + 纯 Python 驱动）。
  vendor 的 `tools/*.py` 文件存储**不再作为主存储**（保留为可选离线兜底，**不**再承载线上数据）；
  按用户画像改为直接写 MySQL `profiles` 表（JSON 列），不再依赖 `load_profile/save_profile` 的 filepath 参数。
  （注：此条推翻了初版"vendor 不动"的约定——那是纯文件存储前提下的取舍，MySQL 化必须改存储层。）
- **未登录行为完全不变**：匿名仍按 `client_id` 存取（`anonymous` 兜底不变）。
- **登录后浏览器自动绑定账号**（`client_bindings` 表，惰性）：
  登录用户直接按 `用户名` 查询；原匿名历史在首次绑定时并入账号（一次性 `UPDATE ... SET owner_username`）；
  一个浏览器同一时刻只归一个账号（重复绑定 = 改绑）。

## 硬约束

- **DB 驱动例外（已确认解除 NFR-01「后端零第三方依赖」约束，2026-10-11）**：MySQL 不在标准库内，
  允许引入纯 Python 的 `PyMySQL` 驱动（无编译依赖，用户指定）。除连接驱动外，业务代码仍尽量零重框架依赖。
- **MySQL 访问隔离**：只允许在 `server/db.py` 与新建的存储模块中 import 数据库驱动；
  `quiz.py`、向量 RAG 相关模块等既有范围闸保护的文件**不得** import `mysql`，
  否则 `tests/run_quiz_regression.py` 的 `quiz_stdlib_only` 闸会失败（见风险项）。
- 前端 auth 类接口软失败（返回 `{ok:false,error}`，不抛异常）。
- 写路径权限校验全在服务端；前端只管显示。

## 验收

- `tests/run_user_system_regression.py`（新增，43 检查）：data_scope 绑定语义 /
  画像路径穿越安全 / change_password 旧密码校验 / 路由与前端源检查，全绿。
- 全量回归（quiz/sidecar/safety/chat/plan + 用户系统）全绿；前端 vite build 通过。
- **MySQL 迁移验收（方案设计确认后实施，暂未落地）**：表结构迁移脚本可重放；
  JSON→MySQL 一次性迁移脚本可跑通且数据条数与文件一致；MySQL 后端下 6 套回归 + 用户系统回归全绿；
  并发写压测无锁等待/连接泄漏；`quiz_stdlib_only` 闸不因 MySQL 引入而变红。
