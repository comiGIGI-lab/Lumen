"""中文文案表 —— v19 第三梯队 #9。

所有 UI 可见的中文文案都集中在这里，方便英文版翻译对照。
约定：常量名 = 用途，不重复内容（如 BTN_GENERATE 不能叫 BTN_XIANGMU）。
"""

# ---- 应用级 ----
APP_TITLE = "study-liu"
APP_SUBTITLE = "输入课程名 · 一键生成大纲 + 资源 + 7 天计划"

# ---- 顶部 / 模式栏 ----
MODE_LABEL_MOCK = "Mock 模式"
MODE_LABEL_LLM = "LLM 模式"
MODE_TIP_MOCK = "（内置数据，无需 API）"
MODE_TIP_LLM = "（调用在线大模型 API）"

# ---- 按钮 ----
BTN_GENERATE = "✨  生成方案"
BTN_GENERATING = "生成中…"
BTN_CHAT = "提问"
BTN_THINKING = "思考中…"
BTN_SETTINGS = "⚙  设置模式"
BTN_KNOWLEDGE = "📚 我的笔记"
BTN_EXPORT = "📥 导出方案"
BTN_HISTORY = "📜 历史"
BTN_CALENDAR = "📅 学习日历"
BTN_SCREENSHOT = "📷 截图讲解"
BTN_LANG_SWITCH = "🌐 EN"
BTN_SHOW = " 显示 "
BTN_HIDE = " 隐藏 "
BTN_TEST = "  测试连接  "
BTN_TESTING = " 测试中… "
BTN_HELP = "  ?  使用说明  "
BTN_CANCEL = "  取消  "
BTN_SAVE = "    保存设置    "
BTN_OK = "    知道了    "

# ---- 输入区 ----
INPUT_COURSE_LABEL = "📖  想学什么课程？"
INPUT_COURSE_PH = "例如：计算机系统、Python 入门、线性代数…"
INPUT_CHAT_LABEL = "💬  课程问答"
INPUT_CHAT_PH = "例如：第 3 章讲什么？零基础能学会吗？推荐什么参考书？"
INPUT_TIP_GENERATE = "💡 提示：回车键也能直接生成"

# ---- 用户画像 ----
PROFILE_TITLE = "🎯  你是哪类学习者？"
PROFILE_LEVEL = "水平"
PROFILE_DAILY = "每日时长"
PROFILE_GOAL = "目标"
PROFILE_DEADLINE = "截止日（YYYY-MM-DD）"

# ---- 三栏 ----
COL_OUTLINE = "课程大纲"
COL_RESOURCES = "推荐资源"
COL_PLAN = "学习计划"

# ---- 状态栏 ----
STATUS_READY = "● 就绪  ·  输入课程名，点击「生成方案」开始"
STATUS_GENERATING = "⏳ 正在为「{course}」生成方案，请稍候…"
STATUS_DONE = "✓ 完成！课程「{course}」方案已生成  ·  大纲 {n_outline} 章 / 资源 {n_resource} 项 / 计划 {n_plan} 天"
STATUS_GENERATE_FAIL = "✗ 生成失败：{msg}"
STATUS_CHATTING = "⏳ 正在回答：{question}…"
STATUS_ANSWERED = "✓ 已回答  ·  {preview}"
STATUS_ANSWER_FAIL = "✗ 问答失败：{msg}"
STATUS_NO_INPUT_COURSE = "⚠ 请先输入课程名"
STATUS_NO_INPUT_QUESTION = "⚠ 请输入问题"
STATUS_KB_UPDATED = "已更新知识库"
STATUS_COLLECTED = "已收藏「{title}」(id {note_id})"
STATUS_NO_ANSWER = "⚠ 还没有可收藏的回答"
STATUS_NO_PLAN = "⚠ 还没有生成方案，请先生成"
STATUS_EXPORT_OK = "已导出方案到 {path}"
STATUS_EXPORT_CANCEL = "ℹ 已取消导出"
STATUS_EXPORT_FAIL = "✗ 导出失败：{msg}"
STATUS_PROGRESS_OK = "✓ 进度已更新「{course}」({done}/{total})"
STATUS_PROGRESS_FAIL = "✗ 进度更新失败：{msg}"
STATUS_REDIRECT = "🔀 已识别为生成请求，请点上方「生成方案」（或直接回车）"
STATUS_THEME_OK = "✓ 已切换，重启生效（部分组件需重建）"
STATUS_THEME_FAIL = "切换失败：{msg}"
STATUS_LANG_OK = "✓ 语言已切换，部分文字需重启后完全生效"

# ---- 聊天历史 ----
CHAT_WELCOME = (
    "你好！先在上面输入课程名，点「生成方案」得到课程大纲，"
    "然后在这里问任何细节都可以。我会先查课程知识库，"
    "找不到再调用在线大模型（需切到 LLM 模式）。"
)
CHAT_CLEARED = "对话已清空。继续问吧～"
CHAT_THINKING = "正在思考…"
CHAT_SOURCE_KB = "（来自：知识库）"
CHAT_SOURCE_LLM = "（来自：在线大模型）"
CHAT_FAIL = "回答失败：{msg}"
CHAT_CONTEXT = "📌 当前上下文：{n} 轮（最多 {max_n} 轮）"
CHAT_DEFAULT_HINT = (
    "📌 先点上方「生成方案」得到课程，再在这里问细节；"
    "AI 会先查知识库再回答。"
)

# ---- 设置对话框 ----
SETTINGS_TITLE = "AI 模型设置"
SETTINGS_TIP_SMALL = "💡 小提示"
SETTINGS_MODE_LABEL = "运行模式"
SETTINGS_MODE_OPT_MOCK = "离线 Mock 模式"
SETTINGS_MODE_OPT_LLM = "在线 LLM 模式"
SETTINGS_LLM_LABEL = "模型配置"
SETTINGS_LLM_SUB = "（可提前配置；切到 LLM 模式后生效）"
SETTINGS_FIELD_PLATFORM = "平台"
SETTINGS_FIELD_KEY = "API Key"
SETTINGS_FIELD_URL = "API Base URL"
SETTINGS_FIELD_MODEL = "模型名称"
SETTINGS_FIELD_REQUIRED = "* 必填（LLM 模式下需要）"
SETTINGS_TEST_OK = "✓ 连接成功"
SETTINGS_TEST_FAIL = "✗ 失败 {code}: {err}"
SETTINGS_TESTING = "连接中…"
SETTINGS_TEST_NEED_KEY = "请先填 API Key"
SETTINGS_TEST_NEED_URL = "请先填 Base URL"
SETTINGS_TEST_MOCK = "Mock 模式下无需测试连接"
SETTINGS_TIPS = [
    "DeepSeek / OpenAI / 通义千问 / 智谱 GLM / 月之暗面都兼容 OpenAI 格式",
    "选「自定义」可以填自己的 URL 和模型名",
    "API Key 只保存在本机 settings.json，不联网传输",
]
SETTINGS_APPEARANCE = "外观"
SETTINGS_LANG = "语言"
SETTINGS_LANG_TIP = "切换后立即生效"

# ---- 使用说明 ----
HELP_TITLE = "使用说明"
HELP_SECTIONS = [
    ("两种模式",
     "【离线 Mock】无需联网、无需 Key，使用内置的课程数据快速生成计划，适合先看效果。\n"
     "【在线 LLM】需要联网 + API Key，会调用真实大模型生成更个性化的方案。"),
    ("怎么用",
     "1. 选择运行模式（默认 Mock，可随时切换）\n"
     "2. LLM 模式下选平台、填 API Key（点\"显示\"看明文）\n"
     "3. 默认 URL 和模型会自动填好，一般不用改\n"
     "4. 点\"测试连接\"验证 Key 是否可用（可选）\n"
     "5. 点\"保存设置\"完成"),
    ("关于 API Key",
     "只保存在本机配置文件 settings.json，不会上传到任何地方。\n"
     "DeepSeek 注册送额度，新用户够用一段时间；详细价格看各平台官网。"),
    ("关于学习计划",
     "根据你输入的目标（学什么、花多久、每天几小时）生成大纲 + 日历。\n"
     "可以多次生成对比，挑一个最合适的保存。"),
]

# ---- 知识库 ----
KB_TITLE = "📚 我的笔记"
KB_NEW = "新建"
KB_IMPORT = "导入"
KB_SEARCH_PH = "搜索关键词…"
KB_IMPORT_TIP_PDF = "支持 PDF / Markdown / TXT；可一次拖入多个文件"
KB_IMPORT_TIP_PASTE = "直接粘贴文本，自动按段落拆分"
KB_IMPORT_TIP_NOTION = "支持 Notion / 语雀 导出格式"

# ---- 收藏 ----
COLLECT_TITLE = "⭐ 收藏最后回答"
COLLECT_LABEL_TITLE = "标题"
COLLECT_LABEL_COURSE = "所属课程"
COLLECT_LABEL_CONTENT = "内容"
COLLECT_BTN_SAVE = "保存"

# ---- 历史 ----
HISTORY_TITLE = "📜 学习历史"
HISTORY_COL_COURSE = "课程"
HISTORY_COL_DATE = "保存时间"
HISTORY_COL_PROGRESS = "进度"
HISTORY_BTN_OPEN = "打开"
HISTORY_BTN_DELETE = "删除"
HISTORY_BTN_CLEAR = "清空全部"
HISTORY_CONFIRM_DEL = "确定要删除「{course}」的全部记录吗？"

# ---- 截图识别 ----
SCREENSHOT_TITLE = "📷 截图讲解"
SCREENSHOT_BTN_LOAD = "  加载图片  "
SCREENSHOT_BTN_OCR = "  开始识别  "
SCREENSHOT_BTN_EXPLAIN = "  让 AI 讲解  "
SCREENSHOT_STATUS_LOADED = "✓ 已加载图片：{filename}（{width}×{height}）"
SCREENSHOT_STATUS_NO_FILE = "请先加载图片"
SCREENSHOT_STATUS_OCR_DONE = "✓ 识别完成，提取到 {n} 段文字"
SCREENSHOT_STATUS_OCR_FAIL = "✗ 识别失败：{msg}"
SCREENSHOT_STATUS_EXPLAIN = "⏳ AI 正在讲解…"
SCREENSHOT_STATUS_EXPLAIN_OK = "✓ 讲解完成"
SCREENSHOT_STATUS_EXPLAIN_FAIL = "✗ 讲解失败：{msg}"

# ---- 日历 ----
CALENDAR_TITLE = "📅 学习日历"
CALENDAR_TIP = "把学习计划导出为 .ics 文件，可导入 Google Calendar / 苹果日历 / Outlook。"
CALENDAR_BTN_EXPORT = "  导出 .ics 文件  "
CALENDAR_STATUS_OK = "✓ 已导出 {n} 个学习日程到 {path}"
CALENDAR_STATUS_FAIL = "✗ 导出失败：{msg}"
CALENDAR_STATUS_CANCEL = "ℹ 已取消"

# ---- 通用 ----
COMMON_OK = "✓"
COMMON_FAIL = "✗"
COMMON_WARN = "⚠"
COMMON_INFO = "ℹ"
COMMON_HINT = "💡"

# ============================================================
# v19 主窗口全量接入补充（#9 第二批）
# ============================================================
MODE_PREFIX = "当前模式："
MODE_LABEL_LLM_FMT = "LLM 模式 · {model}"
MODE_ICON_MOCK = "📦"
MODE_ICON_LLM = "🤖"

# ---- 工具栏（补充按钮） ----
BTN_KEYS = "🔐 密钥"
BTN_LOGS = "📤 导出日志"
BTN_CLEAR_CHAT = "  🗑  清空对话  "
BTN_COLLECT = "  ⭐ 收藏最后回答  "
BTN_LOADING = "载入中…"

# ---- 聊天（补充） ----
CHAT_YOU = "你："
CHAT_MODE_BADGE = "模式"

# ---- 日历弹窗（补充） ----
CALENDAR_START_DATE = "开始日期"
CALENDAR_PREVIEW = "将生成 {n} 个全天学习日程（从 {start} 起）"
CALENDAR_NO_PLAN = "⚠ 还没有生成方案，请先在主窗口点「生成方案」"
CALENDAR_BTN_PREVIEW = "  预览  "
CALENDAR_STATUS_PREVIEW = "✓ 预览正常，共 {n} 个日程"

# ---- 截图弹窗（补充） ----
SCREENSHOT_HINT = "选择一张课件 / 板书 / 错题截图，AI 帮你讲解"
SCREENSHOT_HINT_PH = "可选：想重点讲解什么？（如：第 3 步推导）"
SCREENSHOT_LABEL_OCR = "识别结果"
SCREENSHOT_LABEL_EXPLAIN = "AI 讲解"
SCREENSHOT_NO_BACKEND = "⚠ 未检测到 OCR 后端，请先 pip install easyocr"
SCREENSHOT_RUNNING = "处理中…"

# ---- 密钥管理弹窗 ----
KEYMGMT_TITLE = "🔐 密钥管理"
KEYMGMT_INTRO = "API Key 在本机以密文保存（AES-256-GCM），解密只在内存中发生。"
KEYMGMT_LABEL_MASKED = "遮蔽显示"
KEYMGMT_LABEL_STORED = "磁盘上的密文（settings.json）"
KEYMGMT_LABEL_PLAIN = "明文（仅本机可见）"
KEYMGMT_LABEL_SOURCE = "主密码来源"
KEYMGMT_LABEL_LIB = "加密库"
KEYMGMT_LIB_OK = "cryptography（AES-256-GCM）"
KEYMGMT_LIB_MISSING = "未安装 cryptography（降级为 Base64 混淆）"
KEYMGMT_STATE_ENCRYPTED = "✓ 当前为密文存储"
KEYMGMT_STATE_PLAINTEXT = "⚠ 当前为明文存储，点击「重新加密保存」即可升级"
KEYMGMT_STATE_EMPTY = "尚未配置 API Key"
KEYMGMT_BTN_REVEAL = "  显示明文  "
KEYMGMT_BTN_HIDE = "  隐藏明文  "
KEYMGMT_BTN_REENCRYPT = "  重新加密保存  "
KEYMGMT_BTN_COPY = "  复制  "
KEYMGMT_BTN_CLOSE = "  关闭  "
KEYMGMT_STATUS_SAVED = "✓ 已重新加密保存"
KEYMGMT_STATUS_DECRYPT_OK = "✓ 解密成功，长度 {n}"
KEYMGMT_STATUS_DECRYPT_FAIL = "✗ 解密失败（主密码可能已变更）"
KEYMGMT_STATUS_COPIED = "✓ 已复制到剪贴板"
KEYMGMT_STATUS_FAIL = "✗ 操作失败：{msg}"
KEYMGMT_CLEAR_CLIPBOARD = "（为安全起见，30 秒后自动清空剪贴板）"
KEYMGMT_SOURCE_ENV = "环境变量 STUDYLIU_KEYPASS"
KEYMGMT_SOURCE_FILE = "文件 ~/.studyliu/keypass"
KEYMGMT_SOURCE_FALLBACK = "内置兜底（建议设置环境变量）"

# ---- 启动画面 ----
SPLASH_TIP = "正在准备学习助手…"
SPLASH_VERSION = "版本 {version}"
SPLASH_STEP_ENV = "初始化运行环境…"
SPLASH_STEP_THEME = "加载主题与文案…"
SPLASH_STEP_UI = "构建主界面…"
SPLASH_STEP_DONE = "就绪"

# ---- 运行日志导出 ----
LOGS_STATUS_OK = "✓ 运行日志已导出到 {path}"
LOGS_STATUS_FAIL = "✗ 导出日志失败：{msg}"
LOGS_NOTHING = "⚠ 没有可导出的日志"