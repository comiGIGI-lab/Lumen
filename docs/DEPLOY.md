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
git pull                       # 或按需 git reset --hard origin/master

# 只改了前端 → 必须重新构建，dist/ 不会被 git 带过来
cd web && npm run build && cd ..

# 改了后端 → 重启 PM2
pm2 restart my-api

# 只改了 vendor/study-liu/data/ 下的数据文件 → 不用重启，接口每次请求都重新读盘
```

> ⚠️ `web/dist/` 在 `.gitignore` 里，**服务器上的 dist 是本地构建出来的**。
> 改了 `web/src/` 或 `web/public/` 而忘记 `npm run build`，线上不会有任何变化。

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
limit_req_zone  $binary_remote_addr  zone=api_perip:10m   rate=30r/m;
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

        limit_req  zone=api_perip  burst=10 nodelay;   # ★ 单 IP 限速
        limit_req  zone=api_global burst=20 nodelay;   # ★ 全局兜底限速
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

**实测数据**（2026-09-21 验证）：
- 4.5 秒内打 35 次 `/api/health` → **13 次 200、22 次 429**
- 限速期间 `GET /` 仍返回 200（说明限速只作用于 `/api`，不会把整站打挂）
- 停止施压 22 秒后全部恢复 200（**是自排空的限速，不是永久封禁**）
- 300KB 请求体 → **413**，请求没进到后端

**当前值够用吗**：正常浏览一次约 3-5 个 `/api` 请求，生成方案 1 个 SSE 连接，
30r/m 有充足余量。前端**没有任何轮询**（已确认无 `setInterval`），所以不会自触发。
如果现场网络环境特殊需要放宽，改 `rate=` 的值即可，改完 `reload` 生效。


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
| **接口返回 429** | **触发了限速**。看 `sudo tail /var/log/nginx/error.log` 会看到 `limiting requests ... by zone "api_perip"`。单 IP 限额 30r/m（burst 10），停手约 20 秒自动恢复。若是现场人多共用出口 IP，把 `00-limits.conf` 里的 `rate=` 放宽后 `reload` |
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
- **`tools/rate_limiter.py` 是死代码**：文件在，但 `api_server.py` 里 import 不到它，
  也就是说应用层从来没生效过。要么接进去，要么删掉。
- 公网 22 端口是开放的。建议在阿里云安全组里限制来源 IP，或改用密钥登录并关闭密码认证。

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
