# 服务器部署文档（DEPLOY.md）

> 面向：需要把这套东西重新部署、迁移、或排查线上问题的队友。
> 本文档描述的是 **2026-09-21 实际线上环境**（`http://47.106.76.244`），不是「理想架构」。

---

## 1. 服务器概况

| 项 | 值 |
|---|---|
| 公网地址 | `http://47.106.76.244` |
| 实例 | 阿里云 ECS `iZwz96u1cl8ru02vjl4bceZ` · Ubuntu · 内核 6.8 |
| 登录账号 | `admin`（uid 1000，**免密 sudo**；没有加进 sudo 组，靠 sudoers.d 规则） |
| 登录方式 | 阿里云控制台 → ECS → 远程连接（Workbench 网页终端）；或本机 SSH 到 22 端口 |
| 项目目录 | `/home/admin/ai-coding` |
| Web 根目录 | `/home/admin/ai-coding/web/dist` |
| 备份目录 | `/home/admin/backups` |
| 运行时 | Node **v20.20.2** / npm **10.8.2**（`/usr/bin/node`）· Python 3 |
| 进程管理 | **PM2**，进程名 `my-api`（fork 模式） |
| Web 服务器 | nginx 1.24.0，站点文件 `/etc/nginx/sites-available/default` |

---

## 2. 架构

```
浏览器 ──▶ nginx :80 ──┬── location /        → 静态文件 /home/admin/ai-coding/web/dist
                       │                        （SPA 回退：找不到就返回 index.html）
                       └── location /api/  → proxy_pass 127.0.0.1:8000
                                                    │
                                            PM2: my-api
                                            python3 server/api_server.py
                                                    │
                                        vendor/study-liu/（原版 Agent 源码）
                                                    │
                                        data/（缓存 · 历史 · 知识库 · trace）
```

两个关键点，**少一个就会出问题**：

1. **`location /api/` 必须 `proxy_buffering off`。**
   默认的 `proxy_buffering on` 会把 SSE（`/api/plan/stream`）的事件攒在 nginx 里，
   前端 `Planner→Searcher→Writer→Reviewer` 的推进动画会退化成一闪而过。
   后端虽然发了 `X-Accel-Buffering: no`，但不能指望它一定生效，显式关掉最稳。
2. **`index.html` 必须 `Cache-Control: no-cache`。**
   Vite 产物文件名带内容哈希，每次构建都会变。`index.html` 一旦被浏览器启发式缓存住，
   就会拿旧的哈希去请求已经被删掉的 `assets/*.js`，被 SPA 回退成 HTML 返回，
   浏览器报 `Unexpected token '<'`，**整页白屏**。

---

## 3. 首次部署（从零开始）

```bash
# ① 拉代码
cd /home/admin
git clone https://gitee.com/zhang-binxiang666/ai-coding.git ai-coding
cd ai-coding

# ② 装知识库种子（data/ 被 .gitignore 排除，不会随仓库来，必须手动放）
mkdir -p vendor/study-liu/data
cp docs/seed/knowledge.json vendor/study-liu/data/knowledge.json

# ③ 装前端依赖并构建
cd web && npm install && npm run build && cd ..

# ④ 起后端（PM2）
pm2 start server/api_server.py --name my-api --interpreter python3
pm2 save                      # 保存进程列表，配合 pm2 startup 实现开机自启

# ⑤ 配 nginx（配置见第 6 节），然后：
sudo nginx -t && sudo systemctl reload nginx
```

**API Key**：不需要 `.env`。运行模式与 Key 存在
`vendor/study-liu/data/settings.json`（权限 600），由前端「设置」弹窗写入。
首次部署后需要有人在页面上点右上角模式角标填一次 DeepSeek Key。

---

## 4. 日常更新（改了代码之后怎么上）

```bash
cd /home/admin/ai-coding
# 备份当前 dist 与 settings，再快进。不要 git reset --hard（会丢掉未跟踪改动）。
cp -a web/dist /home/admin/backups/dist-$(date +%Y%m%d-%H%M)
git pull --ff-only

# 只改了前端 → 必须重新构建，dist/ 不会被 git 带过来
cd web && npm run build && cd ..

# 改了后端 → 重启 PM2
pm2 restart my-api

# 只改了 vendor/study-liu/data/ 下的数据文件 → 不用重启，接口每次请求都重新读盘
```

> ⚠️ `web/dist/` 在 `.gitignore` 里，**服务器上的 dist 是本地构建出来的**。
> 改了 `web/src/` 或 `web/public/` 而忘记 `npm run build`，线上不会有任何变化。
>
> **决赛冲刺（Day1 问答引用 + Day2 方案引用知识库 + MinerU 内存闸）已合入 Gitee master。** Day3 Word/PPT 侧车见第 14 节。
> `git pull` 才会更新服务器上的源码。push 本身不会改 `http://47.106.76.244`。
> 有服务器登录的队友按上面做：备份 dist → `git pull --ff-only` → `cd web && npm run build` → `pm2 restart my-api`。改 nginx 才需要 sudo。用户本人没有登录通道，不要替他 SSH。

---

## 5. 关键路径清单

```
/home/admin/ai-coding/
├── server/api_server.py                     后端（纯标准库 HTTP API）
├── scripts/dev.mjs                          本地双进程启动器（服务器上不用）
├── docs/
│   ├── seed/knowledge.json                  ★ 知识库种子（部署时要拷进 data/）
│   ├── DEPLOY.md                            本文档
│   └── API-Contract-knowledge-base-*.md     接口契约
├── vendor/study-liu/                        原版 Agent 源码（core/agents/tools/ui）
│   └── data/                                ★ 运行时数据，不随 git
│       ├── knowledge.json                   知识库（种子拷贝过来）
│       ├── cache.json                       方案缓存
│       ├── progress.json                    课程历史与生成结果
│       ├── client_history.json              浏览器(client_id) ↔ 课程 映射
│       ├── profile.json                     用户画像
│       ├── settings.json                    运行模式与 API Key（600）
│       └── trace.log                        链路日志（前端「日志」抽屉读它）
└── web/
    ├── src/                                 Vue3 源码
    ├── public/                              原样拷进 dist 的静态资源
    │   ├── favicon.ico
    │   └── prototypes/                      三页界面原型 + index.html 索引页
    ├── index.html
    └── dist/                                ★ nginx 实际服务的目录（构建产物）
```

---

## 6. nginx 配置

分两个文件：

### 6.1 `/etc/nginx/conf.d/00-limits.conf` —— 限速 zone 定义

`nginx.conf` 的 `http{}` 块里有一行 `include /etc/nginx/conf.d/*.conf;`，
且排在 `include sites-enabled/*` 之前，所以 zone 可以定义在这里，
**完全不用改 `nginx.conf`**。

```nginx
limit_req_zone  $binary_remote_addr  zone=api_perip:10m   rate=120r/m;   # 2026-10-09 由 30r/m 放宽
limit_req_zone  $server_name         zone=api_global:10m  rate=60r/m;
limit_conn_zone $binary_remote_addr  zone=conn_perip:10m;

limit_req_status  429;
limit_conn_status 429;
```

### 6.2 `/etc/nginx/sites-available/default` —— 站点配置

（`sites-enabled/default` 是它的软链）

```nginx
server {
    listen 80;
    server_name 47.106.76.244;

    client_max_body_size 256k;      # ★ 请求体上限

    location / {
        root /home/admin/ai-coding/web/dist;
        index index.html;
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache";
    }

    location /assets/ {
        root /home/admin/ai-coding/web/dist;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Connection "";

        proxy_buffering off;        # ★ SSE 必需
        proxy_cache off;

        proxy_read_timeout 300s;    # 大模型生成慢，给足
        proxy_send_timeout 300s;

        limit_req  zone=api_perip  burst=60 nodelay;   # ★ 单 IP 限速（2026-10-09 由 burst=10 放宽）
        limit_req  zone=api_global burst=120 nodelay;  # ★ 全局兜底限速（2026-10-09 由 burst=20 放宽）
        limit_conn conn_perip 16;                      # ★ 单 IP 并发上限
    }
}
```

改完务必：`sudo nginx -t && sudo systemctl reload nginx`
（`nginx -t` 失败时 nginx 会继续用旧配置跑，不会把站点弄挂）

### 6.3 三条 ★ 标记的指令各自解决什么问题

| 指令 | 解决什么 | 不加会怎样 |
|---|---|---|
| `proxy_buffering off` | SSE 事件被 nginx 攒着一起发 | 「链路推进」动画退化成一闪而过 |
| `Cache-Control: no-cache`（在 `location /`） | `index.html` 被浏览器启发式缓存 | 拿旧哈希请求已删的 `assets/*.js`，被 SPA 回退成 HTML，报 `Unexpected token '<'` **整页白屏** |
| `client_max_body_size 256k` | 后端 `_read_body()` 按 `Content-Length` 把 body 整体读进内存 | 一个超大 POST 就能吃满可用内存（实例只有 ~1.6GB） |
| `limit_req` ×2 + `limit_conn` | API 无鉴权、无限速，任何人可无限刷 `/api/plan` **烧 LLM 额度** | 地址传开后额度会被刷光 |

**为什么限速要「单 IP + 全局」两条**：
只做单 IP 的话，展会/评委若连同一个 wifi、共用一个出口 IP，
同一出口下多台机器一起刷就挡不住；只做全局的话，
单个攻击者能把全局限额占满，反而把正常演示挤掉。两条一起才既挡得住又不误伤。

**实测数据**：

改前（2026-09-21，30r/m + burst 10）：
- 4.5 秒内打 35 次 `/api/health` → **13 次 200、22 次 429**
- 限速期间 `GET /` 仍返回 200（说明限速只作用于 `/api`，不会把整站打挂）
- 停止施压 22 秒后全部恢复 200（**是自排空的限速，不是永久封禁**）
- 300KB 请求体 → **413**，请求没进到后端

改后（2026-10-09 放宽，实测于 1e23121 时的线上配置）：
- 连续 **50** 次 `/api/health` → **50 次 200、零 429**（终检脚本硬指标，跑两轮都过）
- 连续 **70** 次 → **63 次 200、7 次 429**；`error.log` 记
  `limiting requests, excess: 60.59 by zone "api_perip"`（限流仍在拦，没被改废）

**★ `burst=N` 的语义**：在速率之上**再放行 N 次**，即实际放行 **N+1** 次 ——
实测 burst=10 时连打 15 次正好是「200×11 后全是 429」。所以要让一次 50 连发全过，burst 必须 ≥ 50。

**★ 两条 `limit_req` 会叠加**：只抬「单 IP」那条不够，全局那条（burst 更早耗尽时）照样会掐。
反过来，`burst` 只影响「突发额度」，**持续速率由 `rate=` 决定** ——
本次只抬 burst、不动全局 rate（仍 60r/m），所以常态防护没有变弱。

**★ 两个容易踩的时序**：
- `reload` 会重置 zone 计数（测试前后互不干扰）
- 但打完一次突发后，该 IP 要等 `burst ÷ rate` 秒才排空
  （当前 60 ÷ 2/s ≈ **30 秒**），期间同 IP 的其他 `/api/*` 仍会 429 ——
  终检脚本跑完别立刻接着连点，或者把两次连发隔开半分钟

**当前值够用吗**：正常浏览一次约 3-5 个 `/api` 请求，生成方案 1 个 SSE 连接，
120r/m + burst 60 有充足余量。前端**没有任何轮询**（已确认无 `setInterval`），不会自触发。
若现场网络环境特殊还需更宽，**`00-limits.conf` 的 `rate=` 与 `default` 里的 `burst=` 要一起改**，改完 `reload` 生效。


---

## 7. 备份与恢复

```bash
# 手动备份
TS=$(date +%Y%m%d-%H%M%S)
cd /home/admin/ai-coding
tar czf /home/admin/backups/ai-coding-$TS.tar.gz vendor/study-liu/data web/dist docs
sudo cp -a /etc/nginx/sites-available/default /home/admin/backups/nginx-default-$TS.conf

# 恢复数据
tar xzf /home/admin/backups/ai-coding-<TS>.tar.gz -C /home/admin/ai-coding
```

`data/` 目录里有历史用户的生成记录与 Key，**不要提交到 Git，也不要在群里发**。

---

## 8. 排查手册

| 症状 | 先查什么 |
|---|---|
| 页面白屏，控制台 `Unexpected token '<'` | `index.html` 被缓存了旧哈希。确认 `Cache-Control: no-cache` 生效，然后硬刷新 |
| 链路动画「一闪而过」，没有逐步推进 | `location /api/` 少了 `proxy_buffering off`，或改完没 `reload nginx` |
| 页面 200 但内容不对（返回的是首页） | nginx 的 SPA 回退。**判断某个文件存不存在不能看状态码**，要看响应体长度是否等于 `index.html` 的长度 |
| **接口返回 429** | **触发了限速**。看 `sudo tail /var/log/nginx/error.log` 会看到 `limiting requests ... by zone "api_perip"`。单 IP 限额 **120r/m（burst 60，2026-10-09 由 30r/m + burst 10 放宽）**，突发打满后约 **30 秒**自动恢复。若是现场人多共用出口 IP，把 `00-limits.conf` 的 `rate=` 与 `default` 里的 `burst=` **一起**放宽后 `reload` |
| **接口返回 413** | 请求体超过 `client_max_body_size 256k`。正常接口最大也就 40KB 左右，出现 413 说明有异常大的请求，**属于预期拦截**，值得看一眼是谁在发 |
| 生成方案报错 / 一直卡在「生成中」 | `pm2 logs my-api --lines 100`；再看 `data/trace.log` |
| 「来源：知识库」从来没出现过 | 知识库为空。`curl /api/knowledge` 看 `total`；为 0 就检查 `data/knowledge.json` 是否存在 |
| 改了代码线上没变化 | 忘了 `npm run build`，或 build 输出不在 `web/dist` |
| 后端起不来 | `pm2 list` / `pm2 logs my-api`；确认 8000 端口没被别的进程占 |

端口与进程现状自查：

```bash
sudo ss -ltnp | grep -E ':80|:8000'    # 8000 应只监听 127.0.0.1（不要暴露到公网）
pm2 list
```

---

## 9. 数据归属（重要，涉及演示表现）

**没有数据库**，是四个 JSON 文件。归属关系不一致，演示前要知道：

| 文件 | 归属 | 能被改动吗 |
|---|---|---|
| `knowledge.json` 知识库 | **所有人公用一份** | ❌ 目前**只读** —— `KnowledgeStore.add()` / `delete()` 从未被任何接口调用 |
| `profile.json` 学习画像 | **所有人公用一份** | ✅ `POST /api/profile`（`save_profile()` 不带 client_id） |
| `progress.json` 方案结果 | 全局存一份，靠映射表过滤「谁看得见」 | 间接 |
| `client_history.json` | **按浏览器隔离**（`X-Client-Id`） | 间接 |

⚠️ **演示风险**：画像和知识库是「所有人的默认值」。**一个评委改了学习画像，另一个评委刷新后会看到被改过的值。**

## 10. 已知事项 / 待办

### 10.1 已经堵住的

- **API 无鉴权、无限速** → 已在 nginx 层用 `limit_req` + `limit_conn` 兜住（见 §6）。
  但注意这是**网络层限速**，不是身份认证 —— 真要防住恶意使用，得在应用层加 API Key
  （代价是评委也得多一步，演示不友好，目前不做）。
- **请求体无大小上限** → 已在 nginx 层用 `client_max_body_size 256k` 兜住。
  后端 `_read_body()` 本身仍没有上限，**如果以后绕过 nginx 直接暴露后端，这个洞还在**。
- **文件上传撑爆磁盘** → 目前**不可能**：后端 17 个接口没有任何一个接收文件，
  代码里没有 `multipart` / 文件写入逻辑，`_read_body()` 只把 body 解析到内存不落盘。
  「文档导入页」只是静态原型，不连后端。**以后真要实现上传，必须同时加上：文件大小上限、
  存储配额、类型白名单。**
- **接口泄露服务器绝对路径** → `/api/health`、`/api/mode`、`/api/bootstrap` 原本返回
  `/home/admin/ai-coding/vendor/study-liu` 这类绝对路径，而前端会把 `source_dir`
  **直接显示在界面上**（「业务逻辑来源：…」）—— 等于公开服务器的用户名与目录结构。
  已用 `api_server._rel()` 统一转成相对项目根的路径（`vendor/study-liu`），
  界面观感不变、不再泄露位置。**加了新的路径类字段时记得也过一遍 `_rel()`。**
- **`trace.log` 里混着测试残留** → ⚠️ 这个文件前端「日志」抽屉会读（`/api/trace` 取最后 200 行），
  **评委点开就能看到**。历史上积累过 `开盒教程`、`如何分尸抛尸`、`卖白粉` 等测试输入
  （有些不是近期产生的）。已按「安全层判定 BLOCK + 显式黑名单」过滤，729 → 420 行，
  只留正经学科。**演示前建议再扫一遍**：

  ```bash
  # 看日志抽屉会显示什么（最后 200 行里有敏感字样就该清了）
  tail -200 /home/admin/ai-coding/vendor/study-liu/data/trace.log \
    | grep -cE "开盒|分尸|碎尸|肢解|特朗普|白粉|翻墙|自杀|自残|性|\?\?\?\?"
  ```

### 10.2 还没处理的

- **知识库检索是「整句子串匹配」**（`tools/knowledge_store.py` 的 `search`），
  即用整句问题去 `in` 标题/正文/标签。所以只有提问措辞和笔记高度接近时才会命中，
  否则一律走大模型兜底。实测「索引失效的常见情形」命中，
  而「费曼技巧是什么」「番茄工作法怎么用」不命中。
  想稳定演示「知识库优先」，要么提问尽量贴笔记标题，要么改 `search` 做分词/关键词加权。
- **`progress.json` / `trace.log` 无上限**：
  | 文件 | 现状 | 是否有界 |
  |---|---|---|
  | `cache.json` | ~100 KB | ✅ 有界：`cache_store.MAX_ENTRIES=30` + LRU + 24h TTL |
  | `progress.json` | ~250 KB | ❌ 无界，每生成一门课 +约 10KB |
  | `trace.log` | ~38 KB | ❌ 无界，`log_trace()` 纯追加**不轮转**，每跑一次链路 +约 1.5KB |

  按当前节奏跑一年约几十 MB，**不会「爆炸」**，但确实一直涨。要处理的话：
  给 `progress.json` 按课程数截断、给 `trace.log` 加 `logrotate`。
- **没有 HTTPS / 域名**，仅 `IP:80`。比赛演示建议挂域名 + 免费证书。
- `vendor/study-liu/data/knowledge.json` 是**部署时手动拷贝**的，`git pull` 不会更新它。
  改了 `docs/seed/knowledge.json` 后要重新拷一次。
- ~~**`tools/rate_limiter.py` 是死代码**~~ ← **这条是错的，已更正**。
  它**一直在生效**：`core/llm.py` 的 `chat()` 每次调用前都会 `acquire()`，
  滑动窗口默认 30 次/60 秒（可用环境变量 `LLM_RATE_MAX` / `LLM_RATE_WINDOW` 覆盖）。
  当初只查了 `api_server.py` 就下了结论，没查 `vendor/study-liu/core/`，属于取证不全。
- **公网 22 端口是开放的**。建议在阿里云安全组里限制来源 IP，或改用密钥登录并关闭密码认证。
  （另：`sshd_config` 里 `PermitRootLogin yes` 是开着的，建议关掉。）

### 10.3 排查：生成结果里出现「内置资源库（LLM 不可用时兜底）」

界面上出现这句话 = 某个 Agent 拿到的是内置兜底内容，而不是模型生成的。
这是**降级**，不是报错，所以很容易被误判成"模型变笨了"。按下面顺序查：

**① 先看 trace.log 里的 `degraded` 行**（它会写明确原因）：

```bash
grep degraded /home/admin/ai-coding/vendor/study-liu/data/trace.log | tail -5
```

**② 对照错误信息定位：**

| trace 里的 error | 真实原因 | 处理 |
|---|---|---|
| `模型推理占满了 max_tokens(4000)，未产出正式回答` | **最常见**。思考模型（DeepSeek V4 系、GLM 等）先在 `reasoning_content` 里推理再产出 `content`；prompt 一复杂，推理就把 `max_tokens` 吃光，`content` 为空 | 调大 `LLM_MAX_TOKENS` |
| `请求过于频繁` | 应用层限流（默认 30 次/60 秒）。一次生成要调 4~8 次 LLM | 调大 `LLM_RATE_MAX` |
| `请求超时` | 第三方网关常见 10~45 秒；超时默认 90 秒 | 调大 `LLM_TIMEOUT`，或换更快的模型 |
| `模型返回空内容（网关未正常响应…）` | 网关对某个模型名不可用时会返回 HTTP 200 + 空内容 | 核对模型名 |

**③ 环境变量怎么加**（PM2）：

```bash
pm2 restart my-api --update-env     # 加完变量后必须带 --update-env
# 或在 ecosystem 配置里加 env: { LLM_MAX_TOKENS: "8000" }
```

**★ 2026-09-22 就踩过这个坑**：`max_tokens` 原本写死 2000，导致
searcher / writer 长期静默降级，而 planner 正常（它的 prompt 简单、推理短）——
表现为"有的 Agent 好、有的不好"，查了很久才定位到。
当时还一度误判成"第三方网关坏了"，其实**和供应商无关**。
同类现象出现时，**先怀疑 max_tokens，再怀疑网关**。

## 11. 快速体检命令

```bash
# 站点与接口
curl -sI http://127.0.0.1/ | head -3
curl -s http://127.0.0.1/api/health
curl -s http://127.0.0.1/api/knowledge | head -c 200

# 服务与端口
pm2 list
sudo ss -ltnp | grep -E ':80|:8000'

# 资源
df -h /            # 磁盘（40G，正常应 <20%）
free -h            # 内存（1.6G，Swap 应为 0 使用）
du -sh /home/admin/ai-coding/vendor/study-liu/data/

# 限速是否在拦人
sudo tail -20 /var/log/nginx/error.log | grep -i limiting || echo "  最近没有触发限速"
```

---

## 12. 语音转写（whisper.cpp `small` 优先 / Vosk 回退）—— 模型不在仓库里，换服务器必须手动搬

`/api/asr` 依赖两个**仓库外**的东西（模型 66MB，进不了 git，Gitee 会拒）：

| 路径 | 内容 | 体积 |
|---|---|---|
| `/home/admin/asr/libs` | `pip3 install --target` 装出来的 vosk + cffi 等 | 33MB |
| `/home/admin/asr/vosk-model-small-cn-0.22` | 中文小模型 | 66MB |

代码里的默认路径就是这两个；本地调试可用环境变量覆盖：
`STUDY_LIU_ASR_LIBS` / `STUDY_LIU_ASR_MODEL`。

**新服务器上怎么恢复**（两条命令 + 一次重启）：

```bash
mkdir -p /home/admin/asr
pip3 install --target /home/admin/asr/libs --no-cache-dir \
  -i https://pypi.tuna.tsinghua.edu.cn/simple vosk
# 模型从旧机器 scp 过来，或从 https://alphacephei.com/vosk/models 下载
scp -r 旧机器:/home/admin/asr/vosk-model-small-cn-0.22 /home/admin/asr/
pm2 restart my-api
```

**没搬模型也不会出事**：`server/asr.py` 里 vosk 是**延迟 import** 的，
引擎或模型缺失时只有 `/api/asr` 返回中文提示（界面会把入口置灰并说明原因），
`api_server` 照常启动，其它功能完全不受影响。
排查就一句：`curl -s localhost:8000/api/asr` —— `available` 为 false 时会带上 `reason`。

**资源占用**（2 vCPU / 1.6G 的机器上实测）：模型加载 0.61s；
PM2 常驻内存从 49MB 涨到约 162MB（峰值 178MB）；
120 秒音频解码 12.66s（约 10 倍实时），期间并发请求 21~33ms 正常返回
（vosk 的 C 调用会释放 GIL，长音频**不会**卡住整站）。
单次上限 15MB ≈ 8.2 分钟，卡在 nginx `client_max_body_size 20m` 之下。

**别上大模型**：`vosk-model-cn-0.22`（1.3GB）加载后放不进 1.6G 的机器。

**回滚**：`rm -rf /home/admin/asr` 即彻底移除依赖；代码侧 revert 对应 commit 后
重新 `npm run build` + `pm2 restart my-api`。部署前备份在 `/home/admin/backups/dist-pre-asr-*`。

**whisper.cpp 可选侧车**（不要把 openai-whisper / Docling ASR 装进 api_server）：

二进制和 ggml 模型同样放仓库外。这台 1.6G 机器**只用**多语言 `ggml-small.bin`（约 852MB 可放）。**不要用 `ggml-medium.bin`（约 2.1GB，放不下）**，**不要用 `*.en`**。浏览器已经把音频重采样成 16 kHz PCM，服务端只包 WAV 头，不依赖 ffmpeg。

```bash
# 示例路径（代码默认值）
# /home/admin/asr/whisper/whisper-cli
# /home/admin/asr/whisper/ggml-small.bin
# 或用环境变量覆盖：
# STUDY_LIU_WHISPER_BIN  STUDY_LIU_WHISPER_MODEL
# 强制引擎：STUDY_LIU_ASR_ENGINE=whisper|vosk
# 可选 VAD（官方 README：`--vad` 默认关，且必须同时给 `-vm`）：
# /home/admin/asr/whisper/ggml-silero-v6.2.0.bin   # 约 864KB，不进 git
# STUDY_LIU_WHISPER_VAD_MODEL  / STUDY_LIU_WHISPER_VAD=0 强制关
```

官方：https://github.com/ggml-org/whisper.cpp#voice-activity-detection-vad 。有 Silero ggml 才传 `--vad -vm`；缺模型则整段转写，不传 `--vad`。不要改 `--vad-threshold` 等调参。可选量化：本机 `quantize ggml-small.bin ggml-small-q5_0.bin q5_0` 后把 `STUDY_LIU_WHISPER_MODEL` 指过去，不要上 medium。

`GET /api/asr` 现在会多 `engine` 与 `backends`：有 whisper.cpp 就优先，且 **status() 不再加载约 150MB 的 Vosk**；没有 whisper 才回退 Vosk。两侧都缺时 `available=false`，界面照旧置灰。1.6G 机器不要同时常驻 Vosk 大模型和任何 whisper 模型，也不要上 medium。

## 13. PDF 解析（pypdf 默认 / MinerU 可选侧车）

`POST /api/knowledge/import` 的 HTTP 契约不变。数字文本 PDF 仍走 pypdf；文本层少于约 200 字且文件 ≥ 50KB 时，**并且** `MemAvailable` ≥ 2GiB，才尝试 `mineru-kit parse --tier basic`。1.6G 机器低于这条线：路由保留、扫描件走 pypdf，不要强装。Docling 不作为中文 PDF 主引擎，也不把 MinerU 4.0 整包 import 进 `api_server`。

```bash
# 可选：把 mineru-kit 放到 PATH，或
# export STUDY_LIU_MINERU_BIN=/home/admin/asr/mineru/mineru-kit
# export STUDY_LIU_MINERU_TIER=basic
# 强制：STUDY_LIU_PDF_ENGINE=mineru|pypdf
# 探测：curl -s localhost:8000/api/knowledge/capabilities
```

未装 MinerU、或内存不足 2GiB 时导入照常工作，只是扫描件几乎抽不到字。`GET /api/knowledge/capabilities` 的 `document.mineru.available` 为 false，`note` 会写明是缺二进制还是内存不够。不要在这台 1.6G 机器上用 `--tier standard` / `--tier advanced`。测试可覆盖：`STUDY_LIU_MINERU_RAM_KB` / `STUDY_LIU_MINERU_MIN_RAM_KB`（0 关闭闸）。

## 14. Word / PPT 导入（Docling 可选侧车 / OOXML 标准库回退）

`POST /api/knowledge/import` 现接受 `.docx` / `.pptx`。Docling **不作为中文 PDF 主引擎**（PDF 仍走第 13 节），也不 import 进 `api_server`。有 CLI 时：

```bash
docling convert lecture.docx --to md --no-ocr --output /tmp/docling-out
```

官方参考：<https://docling-project.github.io/docling/reference/cli/>。不要 `--pipeline vlm`，不要 GraniteDocling。缺 `docling` 时 `server/office_parse.py` 用 zipfile + xml 抽 OOXML 正文，服务仍能起。强制：`STUDY_LIU_OFFICE_ENGINE=docling|ooxml`。探测：`curl -s localhost:8000/api/knowledge/capabilities` 看 `document.office`。

