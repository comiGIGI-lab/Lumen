# study-liu 学习智能助手

> 输入课程名 → 自动生成 课程大纲 + 推荐资源 + 学习计划 的桌面学习助手。

## 功能

- **生成学习方案**：输入课程名（如"机器学习"），一键生成三栏内容
  - 课程大纲：章节列表
  - 推荐资源：教程/书籍/视频推荐
  - 学习计划：7 天按天学习计划
- **课程问答**：输入问题，先搜知识库，再调大模型回答
- **知识库管理**：导入/搜索/删除学习笔记（JSON 持久化）
- **日志回放**：每次执行写入 trace 日志，可回放定位
- **双模式运行**：界面内置设置面板，运行时切换 Mock / LLM 模式，无需改 `.env`

## 技术栈

- Python 3.13
- tkinter（自带 GUI 库）
- DeepSeek / OpenAI / 通义千问 / 智谱 GLM / 月之暗面（统一 OpenAI 兼容接口）
- PyInstaller（打包 exe）

## 快速开始

### 1. 安装依赖

```bash
cd studybuddy
pip install -r requirements.txt
```

### 2. 配置密钥

**方式 A：界面设置（推荐）**

直接双击 `study-liu.exe`，点击右上角"⚙ 设置"，选 LLM 模式，从下拉里选平台（DeepSeek/OpenAI/Qwen/GLM/Kimi）并填 API Key，保存即可。

**方式 B：编辑 .env 文件**

```bash
LLM_PROVIDER=llm
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://api.deepseek.com   # 可选，默认 DeepSeek
LLM_MODEL=deepseek-chat                # 可选，默认 deepseek-chat
```

**优先级：** `界面设置（data/settings.json）` > `.env` > 系统环境变量

> 不配置也能用！程序会自动走 Mock 模式，用内置兜底数据。

### 3. 运行

```bash
python app.py          # 开发模式
./study-liu.exe        # 直接双击 exe
```

### 4. 运行测试

```bash
python -m pytest
```

## 界面设置面板

点击主界面右上角"⚙ 设置"，可配置：

| 项 | 说明 |
|---|---|
| **运行模式** | Mock（离线）/ LLM（在线 API） |
| **平台** | DeepSeek / OpenAI / 通义千问 / 智谱 GLM / 月之暗面 / 自定义 |
| **API Key** | 平台密钥（支持显示/隐藏切换） |
| **API Base URL** | 接口地址（选平台自动填） |
| **模型名称** | 模型 ID（选平台自动填） |
| **测试连接** | 一键验证 API 是否可用 |

设置保存在 `data/settings.json`，下次启动自动读取。

## 打包 exe

```bash
build.bat                                     # 一键打包
pyinstaller -F -w app.py --name study-liu    # 或手动
```

打包完成后，exe 在 `dist/study-liu.exe`，双击即可启动。

> 注意：`.env` 文件不会打包进 exe。exe 运行时查找 `.env` 顺序：exe 同目录 → 项目根 → `~/.studybuddy/` → 系统环境变量 → Mock 兜底。

## 项目结构

```
studybuddy/
├── app.py                  # 入口：启动窗口
├── ui/
│   ├── main_window.py      # 主窗口：Hero + 模式栏 + 输入 + 三栏
│   ├── settings_dialog.py  # 设置弹窗：模式/平台/API Key
│   ├── widgets.py          # 结果面板组件
│   └── theme.py            # 颜色/字体/间距常量
├── agents/
│   ├── planner.py          # Planner：课程 → 大纲
│   ├── searcher.py         # Searcher：课程 → 资源列表
│   ├── writer.py           # Writer：大纲 → 学习计划
│   └── reviewer.py         # Reviewer：质量检查
├── tools/
│   ├── knowledge_store.py  # 知识库：增删查（JSON 持久化）
│   └── resource_search.py  # 资源搜索：内置 20+ 课程资源库
├── core/
│   ├── intent.py           # 意图识别：plan / chat
│   ├── agent_loop.py       # Agent 循环 + trace 日志
│   ├── config.py           # 配置管理（settings.json 优先）
│   └── llm.py              # 大模型封装（OpenAI 兼容接口）
├── tests/
│   ├── test_intent.py      # 意图识别测试
│   ├── test_agents.py      # Agent 格式测试
│   └── test_eval.py        # 20 题 Eval 正确率测试
├── data/                   # 运行时数据（自动创建）
├── .env                    # 密钥配置
├── build.bat               # 打包脚本
├── requirements.txt        # 依赖列表
└── README.md               # 本文件
```

## Agent 架构

```
用户输入课程名
    ↓
  意图识别（plan / chat）
    ↓
[plan] Planner → Searcher → Writer → Reviewer
                                       ↓
                                  质检不过 → 重跑 Writer + Searcher（1次）
                                       ↓
                                  三栏展示结果

[chat] 知识库搜索 → 命中？→ 返回知识库回答
                      ↓ 未命中
                 调大模型 → 返回回答
```

## 演示

1. 打开软件，输入"机器学习"
2. 点击"生成方案"
3. 等待几秒，三栏自动填充大纲/资源/计划
4. 底部输入"什么是监督学习"，点击"提问"
5. 状态栏显示回答

## License

MIT