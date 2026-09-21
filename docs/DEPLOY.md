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

## 6. nginx 完整配置

文件：`/etc/nginx/sites-available/default`（`sites-enabled/default` 是它的软链）

```nginx
server {
    listen 80;
    server_name 47.106.76.244;

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

        proxy_buffering off;      # ★ SSE 必需
        proxy_cache off;

        proxy_read_timeout 300s;  # 大模型生成慢，给足
        proxy_send_timeout 300s;
    }
}
```

改完务必：`sudo nginx -t && sudo systemctl reload nginx`
（`nginx -t` 失败时 nginx 会继续用旧配置跑，不会把站点弄挂）

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

## 9. 已知事项 / 待办

- **知识库检索是「整句子串匹配」**（`tools/knowledge_store.py` 的 `search`），
  即用整句问题去 `in` 标题/正文/标签。所以只有提问措辞和笔记高度接近时才会命中，
  否则一律走大模型兜底。想稳定演示「知识库优先」，要么提问尽量贴笔记标题，
  要么改 `search` 做分词/关键词加权。
- **没有 HTTPS / 域名**，仅 `IP:80`。比赛演示建议挂域名 + 免费证书。
- `vendor/study-liu/data/knowledge.json` 是**部署时手动拷贝**的，`git pull` 不会更新它。
  改了 `docs/seed/knowledge.json` 后要重新拷一次。
- 公网 22 端口是开放的。建议在阿里云安全组里限制来源 IP，或改用密钥登录并关闭密码认证。
