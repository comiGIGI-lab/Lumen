# 用户系统方案设计（存储层 MySQL 化）

日期：2026-10-11 · 状态：方案设计稿（核心约束已确认，细节待定，未开工）

> 本文件是《用户系统需求分析（`proposal.md`）》的配套方案设计。需求分析中的用户系统功能
> （账号体系、按用户数据隔离、管理员页、自改密码、个性化本地持久化）**已在 master（`dc590c5`）以
> 纯文件 JSON + 标准库方式落地**。本方案设计的目标，是把其中"关系型数据"的存储后端
> **从纯文件 JSON 改造为 MySQL**，其余功能语义（隔离、绑定、权限）保持不变。
> 文档仅在确认后实施，当前不改动任何代码。

---

## 1. 背景与动机

当前已落地的实现把全部学习数据放在 `data/` 下的若干个 JSON 文件里：

- `accounts.json` / `client_bindings.json`（后端标准库读写）
- `profiles/<用户名>.json`（vendor `load_profile/save_profile`）
- `client_history.json`、`wrong_book.json`、`mindmap.json`、`progress.json`（vendor `tools/*_store.py`）

这些文件在**单用户、低频、小数据量**下没问题，但项目要长期保存**大量关系型数据**，暴露出几个痛点：

1. **并发写入互斥靠整文件重写**。每个 store 都是"读全文件 → 改内存 → 原子替换"，
   服务端是多线程 `ThreadingHTTPServer`，多个浏览器会话同时写会互相覆盖、且写放大严重
   （一道错题就把整个 `wrong_book.json` 重写一遍）。
2. **关系型查询只能靠代码遍历**。错题本按"课程 + 关键词 + 掌握状态"过滤、按账号聚合统计，
   现在是在 Python 里逐条 `if` 过滤；数据量上去后这是 O(n) 全扫，应交给数据库的索引与 SQL。
3. **归属用字符串拼接的"桶名"模拟关系**。`data_scope.py` 用 `u:<用户名>` 这类桶名 + 多桶并集
   来近似"按账号隔离"，本质是在文件存储上硬造一层关系模型，既脆弱又难维护。

**为什么不用 SQLite**：SQLite 是单文件、单写者锁（write-ahead log 下仍同一时刻只允许一个写事务）。
本服务是多线程且会面向多用户并发读写，SQLite 的写并发会成为瓶颈，且跨表关系查询、聚合统计、
未来多实例/读写分离扩展都不如 MySQL 顺手。MySQL 在并发写入、关系查询、横向扩展上更契合本项目。

**选型结论**：MySQL 8.x（utf8mb4），接入层用**纯 Python** 驱动（见第 3 节）。

---

## 2. 总体架构

```
浏览器 (Vue3 + client.js)
      │  X-Auth-Token / X-Client-Id
      ▼
api_server.py  (BaseHTTPRequestHandler，鉴权/权限校验不变)
      │
      ├─ accounts.py        —— 账号/角色/密码/token 校验（逻辑不变，落库改为查 users 表）
      ├─ data_scope.py      —— 绑定语义不变，文件读写改为查 client_bindings / profiles 表
      └─ storage 层（新建 server/db.py + server/storage_*.py）
             │  参数化 SQL（防注入）
             ▼
       MySQLConnectionPool  —— 线程安全连接池
             ▼
         MySQL 8.x（utf8mb4）
```

要点：

- **鉴权、权限校验、前端交互、个性化 localStorage 全部保持不变**；只换"数据落盘"这一层。
- 所有 SQL 走参数化查询，杜绝拼接注入。
- 存储访问集中在新模块，**绝不**外溢到 `quiz.py`、向量 RAG 等既有范围闸保护的文件。

---

## 3. 技术选型

| 项 | 选择 | 理由 |
| --- | --- | --- |
| 数据库 | MySQL 8.x | 并发写、关系查询、扩展性好；utf8mb4 原生支持 emoji/生僻字 |
| 驱动 | `PyMySQL`（纯 Python、无编译依赖；用户 2026-10-11 确认指定） | 不破坏"零编译依赖"的部署习惯；契合当前纯标准库服务端风格 |
| 连接管理 | 自带连接池（connector 的 `MySQLConnectionPool` 或 PyMySQL + 小封装） | 多线程服务每请求取一个连接，用完归还 |
| ORM | **不引入**（裸驱动 + 手写参数化 SQL） | 保持轻量，贴近现有 stdlib 风格；数据模型简单，ORM 收益有限 |
| 字符集 | `utf8mb4` / `utf8mb4_unicode_ci` | 课程名、题干可能含 emoji |
| 半结构化字段 | MySQL `JSON` 列（画像、导图节点、错题标签、方案结果） | 结构灵活，又保留可索引的关系主键 |

> 注：向量 RAG 用的 Chroma 内部自带 SQLite（≥3.35），与本项目用户数据的 MySQL 互不干扰，可并存。

---

## 4. 数据模型（ER / 表设计）

全部表归属库 `study_liu`（可在 `.env` 配置）。以下列定义即迁移脚本的权威来源。

### 4.1 `users`（替代 accounts.json 的 users）
| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK AUTO_INCREMENT | 内部主键 |
| username | VARCHAR(32) | NOT NULL, UNIQUE | 登录名（沿用现有 1–32 字符规则） |
| salt | CHAR(32) | NOT NULL | PBKDF2 salt（hex） |
| password_hash | CHAR(64) | NOT NULL | PBKDF2-HMAC-SHA256 派生值（hex） |
| role | ENUM('admin','user') | NOT NULL DEFAULT 'user' | 角色 |
| created_at | DATETIME | NOT NULL | 建号时间 |

索引：`uk_username(username)`；查询账号列表时 `KEY idx_role(role)`。

### 4.2 `client_bindings`（替代 data_scope 的 client_bindings.json）
| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK AUTO_INCREMENT | |
| client_id | VARCHAR(64) | NOT NULL, UNIQUE | 浏览器随机 ID |
| username | VARCHAR(32) | NOT NULL | 绑定的账号 |
| bound_at | DATETIME | NOT NULL | 绑定时间 |

一个 `client_id` 同一时刻只归一个账号（重复绑定 = 改绑，UPDATE 即可）。

### 4.3 `profiles`（替代 profiles/<用户名>.json）
| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| username | VARCHAR(32) | PK | 与 users.username 对应 |
| profile_json | JSON | NOT NULL | 整份学习画像 |
| updated_at | DATETIME | | 更新时间 |

画像结构灵活，用 JSON 列整体存；不再依赖 vendor `load_profile/save_profile` 的 filepath 参数。

### 4.4 `course_access`（替代 client_history.json，承载"首页学习历史"）
| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK AUTO_INCREMENT | |
| client_id | VARCHAR(64) | NOT NULL | 浏览器 ID |
| username | VARCHAR(32) | NULL | 登录后回填；NULL=仍匿名 |
| course | VARCHAR(255) | NOT NULL | 课程名 |
| last_access_at | DATETIME | NOT NULL | 最近访问 |

唯一键 `uk_client_course(client_id, course)`；登录绑定时 `UPDATE ... SET username=? WHERE client_id=? AND username IS NULL`。

> 设计取舍：登录用户的"历史课程列表"也可直接从 `plan_courses`/`wrongbook`/`mindmap` 按 `owner_username`
> 聚合得到。本表保留是为**最小化行为差异**（首页历史顺序、匿名阶段记录）。若确认可去掉，见第 11 节待确认项。

### 4.5 进度与方案（`progress.json` 的三张表）
原 `progress.json` 结构：`courses[course] = {created_at, last_seen_at, outline[], plan[], result{}}`。
拆为：

**`plan_courses`**
| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK AUTO_INCREMENT | |
| owner_username | VARCHAR(32) | NOT NULL | 归属账号 |
| course | VARCHAR(255) | NOT NULL | 课程名 |
| created_at | DATETIME | | |
| last_seen_at | DATETIME | | |
| UNIQUE(owner_username, course) | | | |

**`plan_items`**（outline / plan 勾选项）
| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK AUTO_INCREMENT | |
| course_id | BIGINT UNSIGNED | NOT NULL, FK→plan_courses.id | |
| kind | ENUM('outline','plan') | NOT NULL | 清单类型 |
| title | VARCHAR(512) | NOT NULL | 条目文本 |
| done | TINYINT(1) | NOT NULL DEFAULT 0 | 是否勾选 |
| sort_order | INT | NOT NULL DEFAULT 0 | 排序 |

**`plan_results`**（方案完整结果 blob）
| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| course_id | BIGINT UNSIGNED | PK, FK→plan_courses.id | 每课程一份 |
| result_json | JSON | NOT NULL | run_plan_pipeline 原始结果 |
| generated_at | DATETIME | | 生成时间 |

### 4.6 `wrongbook`（替代 wrong_book.json 的 items）
| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK AUTO_INCREMENT | 自增 ID（沿用原 seq 语义） |
| owner_username | VARCHAR(32) | NOT NULL | 归属账号（原 client_id，按用户隔离后归账号） |
| client_id | VARCHAR(64) | NULL | 匿名阶段链接；绑定后置 NULL |
| course | VARCHAR(255) | NOT NULL | 课程 |
| question | TEXT | | 题干 |
| my_answer | TEXT | | 我的错答 |
| answer | TEXT | | 正确解法/解析 |
| reason | VARCHAR(1000) | | 错因 |
| tags | JSON | | 标签数组（原 `tags: []`） |
| mastered | TINYINT(1) | NOT NULL DEFAULT 0 | 是否已掌握 |
| review_count | INT | NOT NULL DEFAULT 0 | 复习次数 |
| created_at | DATETIME | | |
| updated_at | DATETIME | | |
| last_review_at | DATETIME | NULL | |

索引：`idx_owner_course(owner_username, course)`、`idx_mastered(mastered)`（按掌握状态过滤）。
原写入上限（题干 4000 / 解析 6000 / 错因 1000 / 标签 12 / 每用户 500 条）在应用层校验保留。

### 4.7 `mindmap`（替代 mindmap.json 的 maps）
| 列 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK AUTO_INCREMENT | |
| owner_username | VARCHAR(32) | NOT NULL | 归属账号 |
| client_id | VARCHAR(64) | NULL | 匿名链接，绑定后置 NULL |
| course | VARCHAR(255) | NOT NULL | 课程 |
| nodes | JSON | NOT NULL | 扁平节点数组 `[{id,parent,text}]` |
| updated_at | DATETIME | | |

唯一键 `uk_owner_course(owner_username, course)`。节点数上限（400）、文本上限（400）、每用户 60 张图在应用层校验保留。

---

## 5. 按用户隔离与查询模型

文件时代用"桶名 + 多桶并集"近似隔离；MySQL 化后，所有学习数据直接以 `owner_username` 为主键维度：

- **登录用户**：所有查询 `WHERE owner_username = ?`。`data_scope.owner_keys_for()` 简化为
  `return [username]`（不再有"用户名桶 + 浏览器桶"并集），查询更快、语义更清晰。
- **匿名用户**：`WHERE client_id = ? AND owner_username IS NULL`（或 `username IS NULL`）。
- **首次登录合并**：`bind_client` 在绑定 `client_bindings` 的同时，执行一次性
  `UPDATE wrongbook/mindmap/course_access SET owner_username=?, client_id=NULL WHERE client_id=? AND owner_username IS NULL`，
  把该浏览器匿名阶段产生的数据并入账号（沿用"原匿名历史归入账号"的既有语义）。
- **画像路径穿越防护**：原 `profile_path` 用哈希文件名防目录穿越；MySQL 下画像按 `username` 主键定位，
  天然不存在路径拼接，该风险随之消除（保留 username 长度/字符校验即可）。

---

## 6. 鉴权与 Token

- 账号/角色/密码校验逻辑（`accounts.py` 的 PBKDF2、token 签发/验签）**完全保留**，仅 `list_users/create_user/...`
  的读写从 JSON 改为 `users` 表。
- **token 签名密钥存放**：原 `accounts.json` 的 `secret` 字段建议改为**环境变量**
  `STUDY_LIU_TOKEN_SECRET`（或 secrets 文件），**不入库**——数据库会被备份/迁移，密钥入表会增加泄露即伪造 token 的风险。
  具体见第 11 节待确认项。
- `allow_register` 开关同理，建议走环境变量或独立的 `system_settings(key,value)` 小表（二选一）。

---

## 7. 与现有实现的关系 & 改造点

| 现有文件 | 改造方式 |
| --- | --- |
| `server/accounts.py` | `_read/_write` 文件操作 → `users` 表参数化读写；密码/token 逻辑不变 |
| `server/data_scope.py` | `client_bindings.json` 读写 → `client_bindings` 表；`profile_path` → `profiles` 表读取；`owner_keys_for` 简化为返回 username |
| `vendor/study-liu/tools/{wrong_book,mindmap,progress}_store.py` | **不再作为主存储**。新建 `server/storage_*.py` 实现同语义的 DB 读写，api_server 改为调用新模块 |
| `server/api_server.py` | 接线处把 `wrong_book_store.* / mindmap_store.* / progress_store.*` 换成新存储模块的对应函数；逻辑分支不变 |
| 前端 `client.js` / `*.vue` | **不改动**（鉴权/个性化前端已落地） |

> 关于"vendor 不动"的初版约定：该约定是在"纯文件存储"前提下的取舍；MySQL 化必须改存储层，
> 故此约定在本方案中**明确推翻**。vendor 的 `tools/*_store.py` 改为保留为可选离线兜底，不再承载线上数据。

---

## 8. 数据迁移方案

一次性迁移脚本 `tools/migrate_json_to_mysql.py`（确认后编写，本阶段不写）：

1. 先 `db.ensure_schema()` 建表（`CREATE TABLE IF NOT EXISTS`，可重放、幂等）。
2. 逐源读取现有 JSON，写入对应表：
   - `accounts.json` → `users`；`client_bindings.json` → `client_bindings`；
     `profiles/*.json` → `profiles`；`client_history.json` → `course_access`（username 留 NULL）；
     `wrong_book.json` → `wrongbook`（owner_username 由 client_id 经绑定表反查，查不到则留 client_id 链接）；
     `mindmap.json` → `mindmap`；`progress.json` → `plan_courses` + `plan_items` + `plan_results`。
3. 幂等：按唯一键跳过已存在行；迁移后保留 JSON 文件作备份（可压缩归档），不改名删除。
4. 切换：迁移跑通、核对条数一致后，把 api_server 接线切到新存储模块（见第 7 节）。

**迁移策略**（待确认）：推荐**停机 cutover**（迁移→切换→旧 JSON 只读兜底），不推荐双写（实现复杂、易不一致）。

---

## 9. 配置与部署

`.env` 新增（与现有 `STUDY_LIU_*` 风格一致）：

```
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=study_liu
MYSQL_PASSWORD=******
MYSQL_DATABASE=study_liu
STUDY_LIU_TOKEN_SECRET=<32+ 位随机串>   # token 签名密钥，建议走 env 而非库
```

- 部署文档 `docs/DEPLOY.md` 追加一节：安装纯 Python 驱动（`pip install mysql-connector-python` 或 `pymysql`）、
  建库建用户、`utf8mb4`、首次启动自动 `ensure_schema()`。
- 启动自检：连不上 MySQL 时服务端应**降级报错并提示配置**，而非静默用文件存储（避免"以为上了 MySQL 其实没上"）。
- Chroma（向量 RAG）的 SQLite 依赖与此无关，部署不变。

---

## 10. 验收标准

- `db.ensure_schema()` 可重复执行（幂等），表/索引与第 4 节一致。
- 迁移脚本可跑通，且各表行数与源 JSON 数据条数一致（核对报告）。
- MySQL 后端下，既有 6 套回归（quiz/sidecar/safety/chat/plan + 用户系统）+ `run_user_system_regression.py`（43 检查）全绿。
- 并发写压测（多线程同时写错题/进度）无锁等待异常、无连接泄漏。
- `tests/run_quiz_regression.py` 的 `quiz_stdlib_only` 闸**不因** MySQL 引入而变红（MySQL 访问未渗入 `quiz.py` 等受闸文件）。
- 前端 vite build 通过；登录/隔离/管理员/改密/个性化行为无回归。

---

## 11. 风险与待确认项（请人工确认）

1. **推翻"不引入 MySQL"的既有范围立场**：早期 `2026-10-09-course-quiz-challenge/proposal.md`
   与向量 RAG `spec.md` 曾写明"不引入 MySQL/…"。本方案直接推翻该立场，需用户正式确认解除。
   （范围闸本身只拦 `quiz.py`/向量模块 import `mysql`；用户已于 2026-10-11 正式解除该立场，允许引入纯 Python 的 `PyMySQL`，访问隔离在 `server/db.py`/新存储模块，不破闸。）
2. **推翻"vendor 不动"与"server 纯标准库"两项初版约束**：本方案已明确推翻，用户 2026-10-11 确认接受（存储层新模块引入 PyMySQL，但 `quiz.py`/向量模块等核心零依赖文件不变）。
3. **token 签名密钥存放**：环境变量（推荐）vs `system_settings` 表。
4. **`course_access` 表是否保留**：可改为从 `plan_courses/wrongbook/mindmap` 聚合首页历史（去一表），或保留（行为差异最小）。
5. **迁移策略**：cutover（推荐）vs 双写。
6. **驱动选型**：**已定 `PyMySQL`**（用户 2026-10-11 确认指定，纯 Python、无编译依赖）。
7. **当前 master 文件版用户系统实现**：MySQL 化后旧 JSON 路径不再写入，是否保留为只读兜底 / 直接下线。
8. **画像 `profiles` 用 JSON 列**（推荐，结构灵活）vs 拆成关系列——当前画像结构不稳定，推荐 JSON 列。

> 以上均不影响方案主体；确认后据此微调并开工。本阶段**未改动任何代码**，等待人工确认。
