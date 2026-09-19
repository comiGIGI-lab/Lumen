"""English translation table —— v19 Tier-3 #9.

All visible UI strings translated to English.
Convention: SCREAMING_SNAKE_CASE constant names mirror zh.py.
"""

# ---- App level ----
APP_TITLE = "study-liu"
APP_SUBTITLE = "Enter a course · Generate outline + resources + 7-day plan"

# ---- Header / Mode bar ----
MODE_LABEL_MOCK = "Mock Mode"
MODE_LABEL_LLM = "LLM Mode"
MODE_TIP_MOCK = "(Built-in data, no API required)"
MODE_TIP_LLM = "(Calls online LLM API)"

# ---- Buttons ----
BTN_GENERATE = "✨  Generate Plan"
BTN_GENERATING = "Generating…"
BTN_CHAT = "Ask"
BTN_THINKING = "Thinking…"
BTN_SETTINGS = "⚙  Settings"
BTN_KNOWLEDGE = "📚 My Notes"
BTN_EXPORT = "📥 Export Plan"
BTN_HISTORY = "📜 History"
BTN_CALENDAR = "📅 Calendar"
BTN_SCREENSHOT = "📷 Screenshot"
BTN_LANG_SWITCH = "🌐 中文"
BTN_SHOW = " Show "
BTN_HIDE = " Hide "
BTN_TEST = "  Test Connection  "
BTN_TESTING = " Testing… "
BTN_HELP = "  ?  Help  "
BTN_CANCEL = "  Cancel  "
BTN_SAVE = "    Save    "
BTN_OK = "    Got it    "

# ---- Input area ----
INPUT_COURSE_LABEL = "📖  What do you want to learn?"
INPUT_COURSE_PH = "e.g. Computer Systems, Python Basics, Linear Algebra…"
INPUT_CHAT_LABEL = "💬  Course Q&A"
INPUT_CHAT_PH = "e.g. What does chapter 3 cover? Can a beginner learn it? Any recommended books?"
INPUT_TIP_GENERATE = "💡 Tip: Press Enter to generate directly"

# ---- User profile ----
PROFILE_TITLE = "🎯  Who are you as a learner?"
PROFILE_LEVEL = "Level"
PROFILE_DAILY = "Daily Time"
PROFILE_GOAL = "Goal"
PROFILE_DEADLINE = "Deadline (YYYY-MM-DD)"

# ---- Three columns ----
COL_OUTLINE = "Course Outline"
COL_RESOURCES = "Resources"
COL_PLAN = "Learning Plan"

# ---- Status bar ----
STATUS_READY = "● Ready  ·  Enter a course name and click \"Generate Plan\""
STATUS_GENERATING = "⏳ Generating plan for \"{course}\", please wait…"
STATUS_DONE = "✓ Done! Plan for \"{course}\" generated  ·  {n_outline} chapters / {n_resource} resources / {n_plan} days"
STATUS_GENERATE_FAIL = "✗ Generation failed: {msg}"
STATUS_CHATTING = "⏳ Answering: {question}…"
STATUS_ANSWERED = "✓ Answered  ·  {preview}"
STATUS_ANSWER_FAIL = "✗ Q&A failed: {msg}"
STATUS_NO_INPUT_COURSE = "⚠ Please enter a course name first"
STATUS_NO_INPUT_QUESTION = "⚠ Please enter a question"
STATUS_KB_UPDATED = "Knowledge base updated"
STATUS_COLLECTED = "Saved \"{title}\" (id {note_id})"
STATUS_NO_ANSWER = "⚠ No answer available to save"
STATUS_NO_PLAN = "⚠ Please generate a plan first"
STATUS_EXPORT_OK = "Exported plan to {path}"
STATUS_EXPORT_CANCEL = "ℹ Export cancelled"
STATUS_EXPORT_FAIL = "✗ Export failed: {msg}"
STATUS_PROGRESS_OK = "✓ Progress updated for \"{course}\" ({done}/{total})"
STATUS_PROGRESS_FAIL = "✗ Progress update failed: {msg}"
STATUS_REDIRECT = "🔀 Detected as a generate request. Click \"Generate Plan\" above (or press Enter)"
STATUS_THEME_OK = "✓ Theme switched. Restart for full effect (some widgets need re-create)"
STATUS_THEME_FAIL = "Switch failed: {msg}"
STATUS_LANG_OK = "✓ Language switched. Restart for complete effect"

# ---- Chat history ----
CHAT_WELCOME = (
    "Hi! Enter a course name above and click \"Generate Plan\" to get the outline, "
    "then ask me anything here. I'll search the course knowledge base first, "
    "and fall back to the online LLM (requires LLM mode)."
)
CHAT_CLEARED = "Chat cleared. Keep asking!"
CHAT_THINKING = "Thinking…"
CHAT_SOURCE_KB = "(source: knowledge base)"
CHAT_SOURCE_LLM = "(source: online LLM)"
CHAT_FAIL = "Answer failed: {msg}"
CHAT_CONTEXT = "📌 Context: {n} turns (max {max_n})"
CHAT_DEFAULT_HINT = (
    "📌 Click \"Generate Plan\" above first to get a course, then ask details here. "
    "The AI searches the knowledge base first."
)

# ---- Settings dialog ----
SETTINGS_TITLE = "AI Model Settings"
SETTINGS_TIP_SMALL = "💡 Tips"
SETTINGS_MODE_LABEL = "Runtime Mode"
SETTINGS_MODE_OPT_MOCK = "Offline Mock Mode"
SETTINGS_MODE_OPT_LLM = "Online LLM Mode"
SETTINGS_LLM_LABEL = "Model Configuration"
SETTINGS_LLM_SUB = "(can pre-configure; takes effect after switching to LLM mode)"
SETTINGS_FIELD_PLATFORM = "Platform"
SETTINGS_FIELD_KEY = "API Key"
SETTINGS_FIELD_URL = "API Base URL"
SETTINGS_FIELD_MODEL = "Model Name"
SETTINGS_FIELD_REQUIRED = "* Required (LLM mode only)"
SETTINGS_TEST_OK = "✓ Connection OK"
SETTINGS_TEST_FAIL = "✗ Failed {code}: {err}"
SETTINGS_TESTING = "Connecting…"
SETTINGS_TEST_NEED_KEY = "Please fill in API Key first"
SETTINGS_TEST_NEED_URL = "Please fill in Base URL first"
SETTINGS_TEST_MOCK = "No connection test needed in Mock mode"
SETTINGS_TIPS = [
    "DeepSeek / OpenAI / Qwen / Zhipu GLM / Moonshot — all OpenAI-compatible",
    "Choose \"Custom\" to use your own URL and model name",
    "API Key is only stored locally in settings.json, never uploaded",
]
SETTINGS_APPEARANCE = "Appearance"
SETTINGS_LANG = "Language"
SETTINGS_LANG_TIP = "Switch takes effect immediately"

# ---- Help ----
HELP_TITLE = "Help"
HELP_SECTIONS = [
    ("Two Modes",
     "【Offline Mock】No network or Key required. Uses built-in course data to quickly generate plans, ideal for preview.\n"
     "【Online LLM】Network + API Key required. Calls a real large model for more personalized plans."),
    ("How to Use",
     "1. Select runtime mode (default Mock, switch anytime)\n"
     "2. In LLM mode: choose platform, fill API Key (click \"Show\" to see plaintext)\n"
     "3. Default URL and model are auto-filled, usually no need to change\n"
     "4. Click \"Test Connection\" to verify the Key (optional)\n"
     "5. Click \"Save Settings\" to finish"),
    ("About API Key",
     "Only stored in the local settings.json, never uploaded anywhere.\n"
     "DeepSeek offers free credits for new users; see each provider's site for pricing."),
    ("About Learning Plans",
     "Generates outline + calendar based on your goal (what, how long, hours per day).\n"
     "You can generate multiple times and pick the best."),
]

# ---- Knowledge base ----
KB_TITLE = "📚 My Notes"
KB_NEW = "New"
KB_IMPORT = "Import"
KB_SEARCH_PH = "Search keywords…"
KB_IMPORT_TIP_PDF = "Supports PDF / Markdown / TXT; drag multiple files at once"
KB_IMPORT_TIP_PASTE = "Paste text directly; auto-split by paragraphs"
KB_IMPORT_TIP_NOTION = "Supports Notion / Yuque export formats"

# ---- Collect ----
COLLECT_TITLE = "⭐ Save Last Answer"
COLLECT_LABEL_TITLE = "Title"
COLLECT_LABEL_COURSE = "Course"
COLLECT_LABEL_CONTENT = "Content"
COLLECT_BTN_SAVE = "Save"

# ---- History ----
HISTORY_TITLE = "📜 Learning History"
HISTORY_COL_COURSE = "Course"
HISTORY_COL_DATE = "Saved At"
HISTORY_COL_PROGRESS = "Progress"
HISTORY_BTN_OPEN = "Open"
HISTORY_BTN_DELETE = "Delete"
HISTORY_BTN_CLEAR = "Clear All"
HISTORY_CONFIRM_DEL = "Delete all records for \"{course}\"?"

# ---- Screenshot ----
SCREENSHOT_TITLE = "📷 Screenshot Explainer"
SCREENSHOT_BTN_LOAD = "  Load Image  "
SCREENSHOT_BTN_OCR = "  Start OCR  "
SCREENSHOT_BTN_EXPLAIN = "  Ask AI to Explain  "
SCREENSHOT_STATUS_LOADED = "✓ Loaded image: {filename} ({width}×{height})"
SCREENSHOT_STATUS_NO_FILE = "Please load an image first"
SCREENSHOT_STATUS_OCR_DONE = "✓ OCR done, extracted {n} text blocks"
SCREENSHOT_STATUS_OCR_FAIL = "✗ OCR failed: {msg}"
SCREENSHOT_STATUS_EXPLAIN = "⏳ AI is explaining…"
SCREENSHOT_STATUS_EXPLAIN_OK = "✓ Explanation done"
SCREENSHOT_STATUS_EXPLAIN_FAIL = "✗ Explanation failed: {msg}"

# ---- Calendar ----
CALENDAR_TITLE = "📅 Learning Calendar"
CALENDAR_TIP = "Export the plan as .ics — import to Google Calendar / Apple Calendar / Outlook."
CALENDAR_BTN_EXPORT = "  Export .ics File  "
CALENDAR_STATUS_OK = "✓ Exported {n} study events to {path}"
CALENDAR_STATUS_FAIL = "✗ Export failed: {msg}"
CALENDAR_STATUS_CANCEL = "ℹ Cancelled"

# ---- Common ----
COMMON_OK = "✓"
COMMON_FAIL = "✗"
COMMON_WARN = "⚠"
COMMON_INFO = "ℹ"
COMMON_HINT = "💡"

# ============================================================
# v19 main-window full integration (Tier-3 #9, batch 2)
# ============================================================
MODE_PREFIX = "Current mode: "
MODE_LABEL_LLM_FMT = "LLM Mode · {model}"
MODE_ICON_MOCK = "📦"
MODE_ICON_LLM = "🤖"

# ---- Toolbar (extra buttons) ----
BTN_KEYS = "🔐 Keys"
BTN_LOGS = "📤 Export Logs"
BTN_CLEAR_CHAT = "  🗑  Clear Chat  "
BTN_COLLECT = "  ⭐ Save Last Answer  "
BTN_LOADING = "Loading…"

# ---- Chat (extra) ----
CHAT_YOU = "You: "
CHAT_MODE_BADGE = "Mode"

# ---- Calendar dialog (extra) ----
CALENDAR_START_DATE = "Start Date"
CALENDAR_PREVIEW = "Will create {n} all-day study events (starting {start})"
CALENDAR_NO_PLAN = "⚠ No plan yet — click \"Generate Plan\" in the main window first"
CALENDAR_BTN_PREVIEW = "  Preview  "
CALENDAR_STATUS_PREVIEW = "✓ Preview OK, {n} events"

# ---- Screenshot dialog (extra) ----
SCREENSHOT_HINT = "Pick a slide / blackboard / wrong-answer screenshot and let AI explain it"
SCREENSHOT_HINT_PH = "Optional: anything specific? (e.g. the derivation in step 3)"
SCREENSHOT_LABEL_OCR = "OCR Result"
SCREENSHOT_LABEL_EXPLAIN = "AI Explanation"
SCREENSHOT_NO_BACKEND = "⚠ No OCR backend found. Run: pip install easyocr"
SCREENSHOT_RUNNING = "Working…"

# ---- Key management dialog ----
KEYMGMT_TITLE = "🔐 Key Management"
KEYMGMT_INTRO = "The API Key is stored encrypted on this machine (AES-256-GCM); decryption happens in memory only."
KEYMGMT_LABEL_MASKED = "Masked"
KEYMGMT_LABEL_STORED = "Ciphertext on disk (settings.json)"
KEYMGMT_LABEL_PLAIN = "Plaintext (local view only)"
KEYMGMT_LABEL_SOURCE = "Master password source"
KEYMGMT_LABEL_LIB = "Crypto library"
KEYMGMT_LIB_OK = "cryptography (AES-256-GCM)"
KEYMGMT_LIB_MISSING = "cryptography not installed (falls back to Base64 obfuscation)"
KEYMGMT_STATE_ENCRYPTED = "✓ Stored as ciphertext"
KEYMGMT_STATE_PLAINTEXT = "⚠ Stored as plaintext — click \"Re-encrypt & Save\" to upgrade"
KEYMGMT_STATE_EMPTY = "No API Key configured yet"
KEYMGMT_BTN_REVEAL = "  Show Plaintext  "
KEYMGMT_BTN_HIDE = "  Hide Plaintext  "
KEYMGMT_BTN_REENCRYPT = "  Re-encrypt & Save  "
KEYMGMT_BTN_COPY = "  Copy  "
KEYMGMT_BTN_CLOSE = "  Close  "
KEYMGMT_STATUS_SAVED = "✓ Re-encrypted and saved"
KEYMGMT_STATUS_DECRYPT_OK = "✓ Decrypt OK, length {n}"
KEYMGMT_STATUS_DECRYPT_FAIL = "✗ Decrypt failed (master password may have changed)"
KEYMGMT_STATUS_COPIED = "✓ Copied to clipboard"
KEYMGMT_STATUS_FAIL = "✗ Failed: {msg}"
KEYMGMT_CLEAR_CLIPBOARD = "(clipboard cleared automatically after 30 seconds)"
KEYMGMT_SOURCE_ENV = "Environment variable STUDYLIU_KEYPASS"
KEYMGMT_SOURCE_FILE = "File ~/.studyliu/keypass"
KEYMGMT_SOURCE_FALLBACK = "Built-in fallback (consider setting an env var)"

# ---- Splash screen ----
SPLASH_TIP = "Preparing your study assistant…"
SPLASH_VERSION = "Version {version}"
SPLASH_STEP_ENV = "Initializing environment…"
SPLASH_STEP_THEME = "Loading theme & strings…"
SPLASH_STEP_UI = "Building main window…"
SPLASH_STEP_DONE = "Ready"

# ---- Runtime log export ----
LOGS_STATUS_OK = "✓ Runtime logs exported to {path}"
LOGS_STATUS_FAIL = "✗ Log export failed: {msg}"
LOGS_NOTHING = "⚠ No logs to export"