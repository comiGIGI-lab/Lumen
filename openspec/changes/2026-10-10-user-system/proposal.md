# 变更提案：用户系统扩展（账号-数据打通 / 管理页 / 按用户画像与个性化）

日期：2026-10-10 · 状态：已落地

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

- **学习数据上服务端、个性化小状态留浏览器**（用户确认的混合方案）：
  历史/进度/错题本/导图/画像按账号隔离（纯文本 JSON，KB 级/用户，2G 服务器无压力）；
  宠物、自习设置（音乐/音量/场景）按账号分档存 localStorage（零服务器成本）。
- **vendor 不动**：按用户画像走 `load_profile/save_profile` 已有的 `filepath` 参数；
  错题本/导图的多桶聚合读在 `api_server.py` 侧完成。
- **未登录行为完全不变**：匿名仍走 client_id 桶（`anonymous` 兜底不变）。
- **登录后浏览器自动绑定账号**（`data_scope.bind_client`，惰性）：
  登录用户读「用户名桶 + 绑定过的浏览器桶」并集，原匿名历史归入账号；
  一个浏览器同一时刻只归一个账号（重复绑定 = 改绑）。

## 硬约束

- server 保持纯标准库（`data_scope.py` 只用 stdlib）。
- 前端 auth 类接口软失败（返回 `{ok:false,error}`，不抛异常）。
- 写路径权限校验全在服务端；前端只管显示。

## 验收

- `tests/run_user_system_regression.py`（新增，43 检查）：data_scope 绑定语义 /
  画像路径穿越安全 / change_password 旧密码校验 / 路由与前端源检查，全绿。
- 全量回归（quiz/sidecar/safety/chat/plan + 用户系统）全绿；前端 vite build 通过。
