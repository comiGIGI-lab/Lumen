# 任务：2026-10-10 用户系统扩展

- [x] Task 1 前端鉴权层修复：client.js 补 `me/login/register/accountsList/accountAction/changePassword`
      （auth 类走 requestSoft 软失败）；`request()` 默认带 X-Auth-Token；
      `planStreamUrl` 加 auth_token 参数（EventSource 不能带自定义头）
- [x] Task 2 TDD：新增 `tests/run_user_system_regression.py`（43 检查：源检查 + 运行时）；
      先红（19 FAIL）后绿
- [x] Task 3 数据归属模块 `server/data_scope.py`（纯 stdlib）：client_id→username 绑定表
      （幂等/改绑/持久化）、`owner_keys_for` 读桶聚合、`profile_path` 画像路径
      （危险用户名走 sha256 哈希文件名，杜绝目录穿越）
- [x] Task 4 `accounts.change_password(username, old, new)`：旧密码校验 + 复用 set_password 规则
- [x] Task 5 api_server 接线：POST /api/password（登录 + 旧密码）；历史/进度/错题本/导图
      登录态按 `u:<username>` 桶读写（读聚合绑定浏览器桶）、匿名旧行为不变；
      bootstrap/plan/plan-stream/profile 按用户画像（profiles/<用户名>.json）
- [x] Task 6 前端：`AccountAdminDialog.vue`（列表/创建/改角色/重置密码/删除）；
      LoginDialog 身份卡加「修改密码」「账号管理(仅管理员)」入口；i18n 补 zh/en
- [x] Task 7 个性化持久化（纯前端）：自习设置（场景/音乐/音量/环境声）按账号分档
      存 localStorage，刷新恢复、登录换档重载（`useStudyTimer.js` + `ownerTag.js`）；
      宠物数据分档 `zjxt.pet.<用户名|anon>`（旧 key 兼容读取，`usePet.js`）；
      知识库页「官方资料库 / 我的个人库」双视图措辞（`KnowledgePage.vue`）
- [x] Task 8 验收：6 套回归全绿 + vite build 通过；快进推送 master
- [x] Task 9 存储层 MySQL 化：`server/db.py` + `server/storage_*.py` + `db/schema.sql` +
      `migrate_json_to_mysql.py`；PyMySQL 不进入 quiz.py / 向量模块 / accounts / data_scope / api_server
- [x] Task 10 匿名 LLM 双闸：`storage_ratelimit.py`（每浏览器默认 10 + 全局池默认 200）；
      chat / plan / quiz/generate / plan/stream 在匿名态 429 + ANON_LIMIT_*；登录不限；fail-open
- [x] Task 11 前端限速引导：`client.js` 派发 `zjxt:anon-limit`；`App.vue` toast + 打开 LoginDialog
- [x] Task 12 回归更新：`run_user_system_regression.py` 增加驱动隔离与限速源检查；openspec 状态改为已落地
