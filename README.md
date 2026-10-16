# 智识有方 LUMEN · 多模态教学智能体

> **把「资料 → 检索 → 答疑 → 练习 → 反馈」串成闭环的教学智能体。**
> 课件、笔记、录音进同一套可检索的个人知识库；AI 只从你自己的材料里讲、出题、判分。

![Vue3](https://img.shields.io/badge/前端-Vue3%20%2B%20Vite-42b883)
![Python](https://img.shields.io/badge/后端-Python%20http.server-3776ab)
![SSE](https://img.shields.io/badge/链路-Planner%20→%20Searcher%20→%20Writer%20→%20Reviewer-6366f1)

- **线上体验**：http://47.106.76.244
- **代码仓库**：https://gitee.com/zhang-binxiang666/ai-coding
- **赛事**：粤港澳大湾区 AI Coding 创新大赛 · 方向一「AI + 教学管理助手 → 多模态教学智能体」
- **团队**：黄思扬（光电信息科学与工程 · 队长）/ 张斌翔（软件工程）/ 刘名芝（计算机科学与技术）

> 仓库与代码内部仍沿用早期工程名 `study-liu`，产品正式名为 **智识有方 / LUMEN**。

---

## 1. 它解决什么问题

大学生自学一门新课，通常卡在四个环节：资料散落在课件、PDF 与课堂录音里，无法统一检索；遇到问题无人及时答疑，通用大模型又容易脱离课程材料编造答案；学到哪一步没有客观记录，进度不可控；长期独学缺乏正反馈，中途放弃率高，极端情绪下还缺少恰当的求助通道。

现有工具要么只解决检索（网盘、笔记软件），要么只解决问答（通用 ChatBot），两者不与「这门课、这个学习目标」绑定。本项目的做法是让 **检索、生成、答疑、练习、反馈共享同一份用户自有资料**，并且全过程可观测、可干预、可降级。

---

## 2. 四个核心功能

首页欢迎层（Hero）的四张能力卡，与主导航入口严格一一对应。每一项都有对应的需求条目、技术方案与界面实现，详见 [`docs/核心功能说明书-v1.0.md`](docs/核心功能说明书-v1.0.md)。

| # | 功能 | 一句话 | 主要落点 |
|---|---|---|---|
| **01** | **学习方案生成** | 输入课程名 + 画像，四段式 Agent 实时生成「大纲 / 资源 / 计划」三栏结果 | `CourseForm.vue`、`PipelineStepper.vue`、`ResultsGrid.vue`、`usePlanStream.js`、`GET /api/plan/stream` |
| **02** | **知识库** | 课件 / PDF / 图片 / 音频导入建库，问答与出题先从这里取依据 | `KnowledgePage.vue`、`ImportPage.vue`、`TranscribePage.vue`、`server/kb_ingest.py`、`server/retrieval_hybrid.py` |
| **03** | **课程问答闯关** | 基于自有资料回答并标注引用；按课程出单选题，服务端判分，答错进错题本 | `ChatPage.vue`、`QuizPanel.vue`、`WrongBookPage.vue`、`server/quiz.py`、`server/wrongbook_quiz.py` |
| **04** | **自习空间** | 场景背景 + 专注计时 + 环境音混音，配待办 / 月历备忘 / 倒数日三个悬浮窗 | `StudySpacePage.vue`、`StudyDock.vue`、`SceneBackdrop.vue`、`useStudyTimer.js`、`useSpace.js` |

---

## 3. 完整能力全景

四个核心功能之外，系统还包含以下已落地能力：

- **多模态资料解析**：PDF（文本层抽取，扫描件走 MinerU 侧车）、Office（OOXML）、图片（模型视觉能力）、音频（离线转写，浏览器端解码）
- **可编辑思维导图**：扁平节点 + 父级引用，后端强制校验「有且只有一个根、无环、父节点存在」
- **错题本**：闯关答错自动归集，支持按题型分类、标记掌握、复习计数
- **方案导出**：Markdown / 浏览器打印 PDF / Word（自写 438 行文档生成器，手写 XML）
- **学伴宠物**：像素学伴常驻右下角，等级 / 经验 / 进化 / 连签 / 更换，提供正反馈
- **内容安全五层门**：复合词组 → 拼音层 → 意图句式 → 议题词 + 语境豁免，84 条用例 0 误伤 0 漏网
- **危机干预 B30**：命中自伤求助信号时短路返回 200 + 权威热线，**零次大模型调用、毫秒级返回**，并对所有回答做号码白名单清洗
- **混合检索**：0.6×向量语义 + 0.4×词法加权融合，弱命中时可走联网检索补题
- **账号体系**：注册 / 登录 / 自助改密 / 管理员建号与改权，密码 PBKDF2 加盐哈希，签名令牌无服务端会话；匿名（`X-Client-Id`）与登录（归属桶 `u:<用户名>` + 绑定的浏览器桶）双轨，登录后原匿名数据一次性并入账号
- **中英双语与暗色模式**：508 条语言包、回退链兜底，25 个组件 93 处硬编码颜色变量化
- **窄屏适配**：430px 断点，导航高度由 140px 压到 58px

---

## 4. 快速开始

### 前置要求

- **Python 3.9+**（`python --version` 能跑即可）
- **Node.js 18+**

### 方式 A：双击 `start.bat`（推荐）

自动定位 `node.exe`，拉起 Python API（:8000）+ Vite（:5173），就绪后自动打开浏览器，关窗口即停。

| 场景 | 命令 |
|---|---|
| 正常启动 | 双击 `start.bat` |
| 强制重启 | `set FORCE=1 && start.bat` |
| 不自动开浏览器 | `set OPEN=0 && start.bat` |

`start.bat` 内容全 ASCII + 使用 `%~dp0` 自定位，放在中文路径下也不会乱码。等价命令：`npm run dev`。

### 方式 B：两个终端手动启动

```bash
# 终端 1 —— 后端
python server/api_server.py --port 8000

# 终端 2 —— 前端
cd web && npm install && npm run dev
```

浏览器打开 <http://127.0.0.1:5173>。

### 运行依赖说明

后端主体**零第三方依赖**（Python 标准库 `http.server`）。仅两处经评估后的例外，均不影响主服务启动：

| 例外 | 范围 | 缺失时行为 |
|---|---|---|
| `PyMySQL` | 用户数据存储层（`server/db.py`、`server/storage_*.py`） | 抛 `DbUnavailable`，存储层 **fail-open 回退 JSON**，服务照常 |
| `langchain-tavily` | 闯关联网出题（`server/quiz.py`） | 记 warning 日志后回退纯知识库出题 |

安装：`pip install -r server/requirements.txt`（只装联网出题那一项；MySQL 驱动按需安装）。

#### 依赖策略与三层证据判据（2026-10-16 新增）

背景复盘：`langchain-tavily` 的传递依赖（PyPI `requires_dist`）包含完整 `langchain>=1.0.0,<2`。此前「不引入完整 LangChain 框架」的说法只查了源码 import 层、未查依赖闭包，判据错配导致口径失实。自本节起约定：凡对外声称「用了 / 没用某依赖」，必须三层证据齐全——源码 import 层（grep）→ 声明层（`server/requirements.txt` 一律钉版本，上下界）→ 实际闭包层（`importlib.metadata` 解析传递依赖，由 `tests/run_dependency_facts.py` 机器复验）。依赖缺失导致的降级一律记 warning 日志，禁止静默；测试中「跳过」必须计 WARN 并在报告末尾列出，不得伪装成 PASS。

---

## 5. 目录结构

```
ai-coding/
├── start.bat                 # ★ 一键启动（自动找 node + 自动开浏览器）
├── package.json              # 工作区脚本
├── .gitignore                # 已排除 .env / data/ / node_modules / dist 等
├── db/
│   └── schema.sql            # MySQL 表结构（10 张表，可重放幂等）
├── docs/
│   ├── 核心功能说明书-v1.0.md  # ★ 四个核心功能：需求 / 技术方案 / 界面
│   ├── 需求分析说明书-v1.0.md  # ★ FR-01~FR-18 + NFR-01~NFR-06 需求基线
│   ├── 技术选型解读.md         # ★ D1~D10 决策点与遗留缺陷（含后续演进说明）
│   ├── DEPLOY.md              # 部署手册
│   ├── 文件地图-已完成工作.md    # 每个文件干什么、哪些不要重写
│   ├── API-Contract-knowledge-base-v0.2-2026-09-20.md
│   ├── 危机干预-B30实现说明-2026-09-22.md
│   ├── 向量RAG-发布与回填指南.md
│   ├── 多模态能力实现路线图-2026-09-21.md
│   ├── 敏感词过滤-后端合入指南-2026-09-22.md
│   ├── 敏感词过滤-放行制方案对照与缺陷清单-2026-09-22.md
│   ├── 敏感词过滤-白名单为主的最小改动建议-2026-09-20.md
│   ├── 后端合入指南-大白话版-2026-09-26.md
│   ├── 演示视频脚本-全功能走查-2026-09-26.md
│   ├── screenshot.png
│   └── seed/knowledge.json
├── openspec/changes/          # ★ 变更提案 → 方案设计 → 任务清单
│   ├── 2026-10-07-document-parse-speech-sidecars/
│   ├── 2026-10-09-course-quiz-challenge/
│   ├── 2026-10-09-quiz-day6-types-report/
│   ├── 2026-10-10-user-system/          # 用户系统：需求分析 + 方案设计 + 任务
│   ├── 2026-10-10-vector-rag-agentic/
│   └── 2026-10-11-wrongbook-quiz-types/
├── scripts/dev.mjs            # 无额外依赖的双进程启动器
├── tests/                     # 11 套回归套件（见 §10）
├── server/                    # ★ Python 后端（主体零第三方依赖）
│   ├── api_server.py          #   HTTP API，2089 行，48 处路由分支
│   ├── accounts.py            #   账号/角色/密码/令牌
│   ├── data_scope.py          #   client_id ↔ username 绑定语义
│   ├── db.py                  #   MySQL 连接池（全仓唯一 import pymysql 处之一）
│   ├── storage_*.py           #   存储层：users/bindings/profiles/progress/
│   │                          #            wrongbook/mindmap/ratelimit
│   ├── quiz.py                #   闯关出题与判分（44 KB）
│   ├── wrongbook_quiz.py      #   错题按题型回练
│   ├── kb_ingest.py           #   知识库导入：解析、分块、入库
│   ├── retrieval_hybrid.py    #   混合检索（向量 + 词法）
│   ├── embeddings.py / vector_store.py / embed_backfill.py / web_tools.py
│   ├── doc_parse.py           #   PDF 侧车：MinerU 可选，pypdf 兜底
│   ├── office_parse.py        #   OOXML 解析
│   ├── parse_blocks.py / markitdown_fallback.py
│   ├── asr.py / whisper_cpp.py #  语音转写：Vosk 默认，whisper.cpp 可选
│   ├── safety_gate.py / safety_rules.py / safety_words.py
│   ├── crisis.py              #   B30 危机干预（独立模块）
│   ├── error_text.py / form_parser.py
│   └── requirements.txt       #   唯一一项：langchain-tavily
├── vendor/study-liu/          # 原版 Agent 源码（仅代码）
└── web/                       # ★ Vue3 + Vite 前端工程
    ├── public/
    │   ├── hero-desk.jpg      # Hero 书桌图
    │   ├── pet/               # 九只学伴图
    │   ├── scenes/ sounds/ music/
    │   └── prototypes/        # 早期静态原型（设计先行，主应用不走这里）
    ├── scripts/               # 无浏览器验证工具（见 §10）
    └── src/
        ├── App.vue            # 总装（引导 → 欢迎 → 主应用）
        ├── components/        # 43 个组件，见下方分组
        ├── composables/       # usePlanStream / useKnowledge / useAuth /
        │                      # usePet / useSpace / useStudyTimer / useTheme ...
        ├── api/client.js      # REST + SSE 客户端
        ├── i18n/              # 中英语言包（508 条）
        └── styles/global.css  # 设计令牌
```

**前端组件分组**：

- 核心功能：`CourseForm` / `PipelineStepper` / `ResultsGrid` / `ResultPanel` / `PlanPanel` / `KnowledgePage` / `ImportPage` / `TranscribePage` / `ChatPage` / `ChatPanel` / `QuizPanel` / `WrongBookPage` / `StudySpacePage` / `StudyDock` / `SceneBackdrop`
- 欢迎与导航：`WelcomeScreen` / `AppHeader` / `TopNav` / `TourDialog` / `TourBubble` / `HandbookPage`
- 账号：`LoginDialog` / `AccountAdminDialog`
- 学伴：`PetCompanion` / `PetGuide` / `PetProfileDialog` / `PetSprite`
- 悬浮窗与自习：`SpaceLayer` / `SpacePanel` / `FloatWin` / `DateDock` / `TodoDock` / `CountdownTimer`
- 通用：`ExportPreview` / `HistoryDialog` / `TraceDrawer` / `SettingsDialog` / `MindMapPage` / `LearningProgress` / `ModalDialog` / `SnakeBar` / `StatusBar`

---

## 6. 技术架构

```
浏览器 (Vue3 + Vite)
      │  X-Auth-Token / X-Client-Id
      ▼
api_server.py   (BaseHTTPRequestHandler，鉴权 / 权限校验)
      │
      ├─ 内容安全闸 → 危机干预短路（命中即返回热线，零模型调用）
      ├─ Planner → Searcher → Writer → Reviewer   （vendor/study-liu Agent 链路）
      ├─ 知识库检索（向量 + 词法融合）→ 注入 → 生成
      └─ 存储层 storage_*.py ──► MySQL 8.x（utf8mb4，10 张表）
                              └─ 不可用时 fail-open 回退 JSON
```

### 关键决策

**为什么后端不是 Node 而是 Python？**
Agent 逻辑只有一份。`Planner / Searcher / Writer / Reviewer`、`run_plan_pipeline`、意图识别、用户画像、缓存、进度存储全部由原项目的 `core/`、`agents/`、`tools/` 提供。Web 层若重写一遍就会出现两套会漂移的实现。后端只做三件事：定位源码目录 → `sys.path.insert`；把函数调用包成 JSON 接口；把 `agent_loop` 写出的 `data/trace.log` 实时转成 SSE 事件流。

**为什么后端主体零第三方依赖？**
`http.server` + `json` + `threading` 就是全部。原项目只有 `requests` 是硬依赖，系统 Python 通常自带；`dotenv`、`cryptography` 在源码里都是 `try/except` 可选导入。这换来「clone 即跑」和「2 核 1.6 GiB 内存机器仍能演示」。后端在 `import core.config` 之前用标准库自行解析 `.env`，不依赖 dotenv。

**为什么用 SSE 而不是 WebSocket？**
「一条链路」的价值在于看得见推进过程。SSE 是单向服务端推送，正好匹配「Agent 一步一步跑完」的语义，浏览器原生 `EventSource` 自动处理断流重连。前端还做了降级：SSE 连不上时自动回落到 `POST /api/plan`。

**为什么知识库数据迁到 MySQL？**
文件存储下每个 store 都是「读全文件 → 改内存 → 原子替换」，多线程并发写会互相覆盖且写放大严重；按「课程 + 关键词 + 掌握状态」过滤只能在 Python 里 O(n) 全扫。MySQL 在并发写入、关系查询、横向扩展上更契合。选型为 MySQL 8.x + 纯 Python 驱动 `PyMySQL`，不引入 ORM，全部参数化 SQL。详见 [`openspec/changes/2026-10-10-user-system/design.md`](openspec/changes/2026-10-10-user-system/design.md)。

**数据隔离模型**
未登录按 `X-Client-Id` 存取，行为与早期版本完全一致；登录后浏览器自动绑定账号，原匿名数据一次性并入账号；一个浏览器同一时刻只归一个账号。宠物、自习设置等个性化小状态仍按账号分档存 localStorage，零服务器成本。

---

## 7. API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查，返回源码目录与 trace 路径 |
| GET | `/api/bootstrap` | 启动元信息：模式 / 画像 / 可选项 / 历史 |
| GET | `/api/mode` | 当前运行模式（mock / llm） |
| POST | `/api/profile` | 保存用户画像 |
| **GET** | **`/api/plan/stream`** | **★ SSE：课程名 → 完整链路（step / trace / result 事件）** |
| POST | `/api/plan` | 非流式生成（SSE 降级用） |
| POST | `/api/chat` | 课程问答（知识库优先，带引用） |
| GET | `/api/trace?limit=` | trace.log 尾部 |
| GET | `/api/history` | 历史课程列表 |
| GET | `/api/progress/overview` | 学情总览 |
| POST | `/api/progress/done` | 进度勾选（乐观更新 + 失败回滚） |
| GET / POST | `/api/knowledge` | 知识库查询 / 写入 |
| POST | `/api/knowledge/import` | 文档导入 |
| GET | `/api/knowledge/capabilities` | 当前可用的解析能力 |
| GET / POST | `/api/knowledge/categories` | 分类 |
| POST | `/api/knowledge/share` / `/redeem` | 分享码 / 兑换 |
| POST | `/api/asr` | 语音转写 |
| GET / POST | `/api/mindmap` | 思维导图读写 |
| GET / POST / DELETE | `/api/wrongbook` | 错题本 |
| POST | `/api/wrongbook/from-quiz` | 闯关错题归集 |
| **GET** | **`/api/quiz/stream`** | **★ SSE：边出边答** |
| POST | `/api/quiz/generate` | 出题（标准答案只存服务端） |
| POST | `/api/quiz/grade` | 判分 |
| GET / POST | `/api/quiz/report` | 复盘报告 |
| POST | `/api/export` | 导出（Markdown / Word） |
| POST | `/api/settings` / `/settings/test` | 切换 Mock / LLM 模式、连通性测试 |
| POST | `/api/cache/clear` | 清空结果缓存 |
| GET | `/api/me` | 当前身份 |
| POST | `/api/login` / `/api/register` | 登录 / 注册 |
| GET / POST | `/api/accounts` | 账号管理（管理员） |
| POST | `/api/password` | 修改密码（需旧密码） |

### SSE 事件协议

```
event: meta      → { course, profile, profile_text, mode, stages, started_at }
event: trace     → { ts, event, data }          # 原始 trace 行
event: step      → { key, status, index, hint, data }   # 驱动流水线状态条
event: result    → { outline, resources, plan, plan_items, stats, markdown, ... }
event: error     → { error }
event: done      → { ok, duration_ms }
```

```bash
curl -N "http://127.0.0.1:8000/api/plan/stream?course=机器学习&level=入门&daily_hours=2h&goal=兴趣&use_cache=0"
```

---

## 8. Mock / LLM 双模式

| 模式 | 行为 |
|---|---|
| **Mock**（默认） | 不调用任何在线接口。Planner 走课程分类模板，Searcher 走内置资源库，Writer 走活动模板。**离线可跑，演示零风险。** |
| **LLM** | 调用 DeepSeek / OpenAI / Qwen / GLM / Kimi。API 失败时自动降级到模板，并在界面顶部弹出橙色告警说明「本次方案并非大模型生成」。 |

配置优先级：**界面设置（`data/settings.json`）> `.env` > 系统环境变量**，API Key 落盘自动加密（AES-GCM + PBKDF2）。

排查用：`curl http://127.0.0.1:8000/api/mode` 返回 `reason` / `env_loaded` / `has_key` / `env_file_exists`。

> 已知的一个坑：所用模型会「先推理、再作答」，若输出额度写死过小（如 2000），推理阶段会吃光额度导致正式回答为空且不报错、只静默降级。排查规则是**先怀疑输出额度，再怀疑服务商**。

---

## 9. 数据与安全

- **不入库的**：`.env`、`data/`、API Key、token 签名密钥（`STUDY_LIU_TOKEN_SECRET` 走环境变量）已在 `.gitignore` 排除
- **密码**：PBKDF2-HMAC-SHA256 加盐哈希，不存明文；登录凭证为签名令牌，无服务端会话，重启不掉线
- **权限**：不允许删掉最后一个管理员；自助注册只创建普通账号，管理员必须由现有管理员创建
- **SQL**：全部参数化查询，杜绝拼接注入
- **存储隔离**：MySQL 访问只出现在 `server/db.py` 与 `server/storage_*.py`，不得外溢到 `quiz.py` 与向量模块（有回归闸守护）
- **匿名限速**：`/api/chat`、`/api/plan`、`/api/plan/stream`、`/api/quiz/generate`、`/api/quiz/stream` 五个消耗 token 的入口，在匿名态叠加「每浏览器每日」与「全局匿名每日池」两道闸，超限返回 429，登录用户不受限；数据库异常时 fail-open

---

## 10. 测试与回归

```bash
python tests/run_safety_regression.py        # 内容安全 84 条
python tests/run_crisis_regression.py        # 危机干预
python tests/run_quiz_regression.py          # 闯关（含 quiz_stdlib_only 依赖闸）
python tests/run_user_system_regression.py   # 用户系统 + MySQL 驱动隔离 + 匿名限速
python tests/run_vector_rag_regression.py    # 向量 RAG
python tests/run_structured_parse_regression.py
python tests/run_wrongbook_quiz_regression.py
python tests/run_kb_scope_regression.py
python tests/run_plan_kb_regression.py
python tests/run_chat_retrieved_regression.py
python tests/run_sidecar_regression.py       # MinerU / whisper.cpp 侧车（假 CLI）
```

前端无浏览器验证：

```bash
cd web
node scripts/ssr-check.mjs            # ① 能渲染吗 → SSR 渲染 + 内容抽查
node scripts/click-test.mjs dist-ct1  # ② 点了有反应吗 → jsdom 真实点击
node scripts/minimal-dom-test.mjs     # ③ 对照实验
```

> ① 与 ② 的区别很关键：SSR 只能证明「组件能渲染」，证明不了「事件能响应」——「点按钮没反应」属于后者，必须用 ② 才能复现。

---

## 11. 文档索引

| 想看什么 | 看这份 |
|---|---|
| 四个核心功能的需求 / 技术方案 / 界面 | [`docs/核心功能说明书-v1.0.md`](docs/核心功能说明书-v1.0.md) |
| 全部需求条目与验收标准（FR-01~FR-18、NFR-01~06） | [`docs/需求分析说明书-v1.0.md`](docs/需求分析说明书-v1.0.md) |
| 技术决策点与遗留缺陷（D1~D10） | [`docs/技术选型解读.md`](docs/技术选型解读.md) |
| 用户系统（账号 / 隔离 / MySQL 迁移） | [`openspec/changes/2026-10-10-user-system/`](openspec/changes/2026-10-10-user-system/) |
| 混合检索与向量 RAG | [`openspec/changes/2026-10-10-vector-rag-agentic/`](openspec/changes/2026-10-10-vector-rag-agentic/) |
| 闯关与复盘 | [`openspec/changes/2026-10-09-course-quiz-challenge/`](openspec/changes/2026-10-09-course-quiz-challenge/) |
| 文档解析与语音侧车 | [`openspec/changes/2026-10-07-document-parse-speech-sidecars/`](openspec/changes/2026-10-07-document-parse-speech-sidecars/) |
| 部署上线 | [`docs/DEPLOY.md`](docs/DEPLOY.md) |
| 每个文件干什么、哪些不要重写 | [`docs/文件地图-已完成工作.md`](docs/文件地图-已完成工作.md) |
| 危机干预 B30 | [`docs/危机干预-B30实现说明-2026-09-22.md`](docs/危机干预-B30实现说明-2026-09-22.md) |
| 早期 UI 原型 | `web/public/prototypes/`（静态 HTML，可直接双击打开） |

`openspec/changes/` 下每个变更目录固定三件套：`proposal.md`（为什么做 / 需求）→ `design.md`（怎么做 / 方案设计）→ `tasks.md`（任务清单与完成情况）。

---

## 12. 常见问题

**Q：点「生成方案」没反应？**
先确认后端在跑：`curl http://127.0.0.1:8000/api/health`。前端状态栏会直接提示「后端未启动」。

**Q：为什么每次生成的方案一模一样？**
Mock 模式下章节/资源来自内置模板，这是预期行为。同课程 + 同画像在 24 小时内会命中结果缓存（状态栏显示 `⚡ 缓存命中`），取消勾选「允许命中结果缓存」可强制重算。改动数据结构时必须同步升级缓存版本号，否则旧缓存会继续返回旧结构，表现为「改了没用」。

**Q：流水线节点一直卡在「生成中」？**
说明 `data/trace.log` 没有新增内容。检查后端控制台是否有异常堆栈。后端已把 `data_dir()` 做了不可写回退（会落到 `~/.study-liu/data`），不会因权限问题静默失败。

**Q：改了后端但新接口一直 404？**
改了后端或业务模块**必须重启后端进程**——前端构建成功、页面也变了，但进程还在跑旧代码。

**Q：匿名使用被限流了？**
未登录状态对大模型类接口有每日配额（每浏览器 + 全局池两道闸），超限返回 429，前端会提示并打开登录框。登录用户不受限。

**Q：能否只部署前端？**
可以。`npm run build` 产出 `web/dist/`，交给任意静态服务器托管；把 `/api` 反代到 Python 后端即可（跨域已在后端放开）。注意 nginx 必须 `proxy_buffering off`，否则 SSE 流式输出会被缓冲。

---

## 13. 界面预览

![界面截图](./docs/screenshot.png)

首页欢迎层为全幅书桌摄影 + 遮罩 + LUMEN 刊名，下方是四张 CSS 3D 纵深叠卡（对应第 2 节的四个核心功能），再往下是 CTA 与页脚。关闭欢迎层即进入工具主界面。

---

*文档随代码更新。若发现描述与实现不符，以源码为准，欢迎提 issue。*
