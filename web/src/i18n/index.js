/**
 * i18n —— 轻量中英切换
 *
 * 为什么不用 vue-i18n：与项目「零依赖」原则一致（服务器内存小，
 * 多一个依赖就多一个装不上的可能）。这里只需要「查表 + 回退 + 切换」，几十行足够。
 *
 * 回退策略：当前语言缺某个键 → 回退中文 → 再回退调用方给的默认值 → 最后返回 key 本身。
 * 这样**漏翻不会显示成空白或 undefined**，而是显示中文原文，不会把界面弄坏。
 *
 * 覆盖范围（务实）：导航、各页面标题与主要动作按钮。
 * 长尾文案（引导气泡、设置弹窗细节等）暂留中文，见文件末尾 TO_BE_TRANSLATED。
 */
import { computed, ref } from 'vue'
import autoZh from './auto-zh.json'
import autoEn from './auto-en.json'

const KEY = 'zjxt.lang'

/** 手工维护的核心文案（导航、通用词、页面标题，key 是语义化的点号路径） */
const MANUAL = {
  'zh-CN': {
    nav: {
      home: '首页',
      course: '学习方案生成',
      knowledge: '知识库',
      import: '文档导入',
      transcribe: '语音转写',
      chat: '课程问答',
      wrongbook: '错题本',
      study: '自习空间',
      more: '更多',
      mindmap: '思维导图',
      progress: '学习进度',
      manual: '使用手册',
      space: '个人空间',
      settings: 'AI 模型设置',
      history: '历史',
      trace: '日志',
      needKey: '填入 API Key',
      toDark: '深色模式',
      toLight: '浅色模式',
      toEn: 'English',
      toZh: '中文',
    },
    common: {
      back: '返回',
      save: '保存',
      cancel: '取消',
      delete: '删除',
      edit: '编辑',
      close: '关闭',
      refresh: '刷新',
      loading: '加载中…',
      search: '查询',
      clear: '清除筛选',
      empty: '这里还是空的',
    },
    page: {
      knowledgeTitle: '知识库',
      importTitle: '文档导入',
      chatTitle: '课程问答',
      wrongbookTitle: '错题本',
      progressTitle: '学习进度',
      mindmapTitle: '思维导图',
      studyTitle: '自习空间',
      transcribeTitle: '语音转写',
      transcribeBack: '返回学习方案',
    },
    trPage: {
      lead: '把讲课录音、听课时记的语音、或者直接对着手机说的一段话，转成文字。识别在自己服务器上离线完成，音频不上传任何第三方接口。',
      engineDown: '语音识别引擎当前不可用',
      pickTitle: '选择或拖入一段音频',
      pickHint: '支持 mp3 / m4a / wav / ogg / webm，单次最长 8 分钟',
      browse: '选择音频文件',
      capture: '用手机录一段',
      current: '当前音频',
      wait: '待转写',
      done: '已转写',
      result: '转写结果（可直接编辑）',
      speed: '识别速度 {x}× 实时',
      chars: '共 {n} 字',
      again: '换一段',
      copy: '复制全文',
      download: '下载 .txt',
      engine: '识别引擎',
      engineName: '模型',
      limit: '单次时长上限',
      vad: '语音活动检测（VAD）',
      privacy: '默认 Vosk 离线中文模型；若服务器装了 whisper.cpp 侧车则优先用它。音频不会发给 OpenAI、DeepSeek 等任何外部服务。',
      privacyWhisper: '当前走 whisper.cpp 侧车（ggml 多语言模型，-l zh）。音频留在本机服务器，不经 Docling / openai-whisper。',
      toKb: '存入知识库',
      kbTitle: '笔记标题',
      saveBtn: '存入知识库',
      saved: '已存入',
      kbHint: '存进去之后，在「课程问答」里就能就这段内容直接提问。',
      howto: '使用提示',
      howto1: '支持格式',
      howto2: '准确率',
      howto2v: '普通话最佳',
      howto3: '长音频',
      howto3v: '请分段',
      howtoTip: '小模型对口语、方言和专有名词会有偏差。识别完可以直接在文本框里改，再存进知识库。',
    },
    // 账号与权限（知识库删除是管理员专属）
    auth: {
      title: '账号登录',
      login: '登录',
      logout: '退出登录',
      signupTitle: '注册账号',
      signinSub: '登录后管理知识库与学习方案',
      signupSub: '注册后即可导入资料、生成学习方案',
      username: '账号',
      usernamePlaceholder: '请输入账号',
      password: '密码',
      passwordPlaceholder: '请输入密码',
      confirmPlaceholder: '请再次输入密码',
      signup: '注册',
      signingUp: '注册中…',
      needBoth: '请填写账号和密码',
      mismatch: '两次输入的密码不一致',
      failed: '登录失败',
      signupFailed: '注册失败',
      loggingIn: '登录中…',
      togglePw: '显示或隐藏密码',
      signedInAs: '当前登录身份',
      roleAdmin: '管理员',
      roleUser: '普通账号',
      adminHint: '你是管理员，可以删除知识库里的内容。',
      userHint: '普通账号可以查看、导入和提问；删除知识库内容需要管理员账号。',
      noAccount: '还没有账号？',
      haveAccount: '已有账号？',
      goSignup: '立即注册',
      goSignin: '去登录',
      signinNote: '普通账号可查看、导入和提问；删除知识库内容需要管理员账号。',
      signupNote: '注册的账号为普通账号，可查看、导入和提问；删除知识库内容需要管理员。',
      adminOnly: '仅管理员可删',
      adminOnlyTip: '删除知识库内容需要管理员账号',
      // 自助改密 + 账号管理（用户系统扩展）
      changePw: '修改密码',
      changePwSub: '修改成功后请用新密码重新登录',
      oldPwPlaceholder: '请输入原密码',
      newPwPlaceholder: '请输入新密码（至少 6 位）',
      changePwConfirmPlaceholder: '请再次输入新密码',
      changing: '提交中…',
      changePwShort: '新密码至少 6 位',
      changePwMismatch: '两次输入的新密码不一致',
      changePwOk: '密码已更新，下次请用新密码登录',
      manage: '账号管理',
      manageSub: '创建账号、调整角色、重置密码或删除账号',
      createAccount: '创建账号',
      newUsernamePlaceholder: '新账号名',
      newPasswordPlaceholder: '初始密码（至少 6 位）',
      role: '角色',
      toAdmin: '设为管理员',
      toUser: '设为普通账号',
      resetPw: '重置密码',
      del: '删除',
      resetPwPrompt: '输入「{name}」的新密码（至少 6 位）：',
      confirmDel: '确定删除账号「{name}」吗？此操作不可撤销。',
      empty: '暂无账号',
      back: '返回',
    },
    plan: {
      outline: '课程大纲',
      resources: '推荐资源',
      days: '学习计划',
      export: '导出方案',
      generate: '生成方案',
    },
  },

  'en-US': {
    nav: {
      home: 'Home',
      course: 'Generate Plan',
      knowledge: 'Knowledge Base',
      import: 'Import Docs',
      transcribe: 'Transcribe',
      chat: 'Course Q&A',
      wrongbook: 'Wrong-Answer Book',
      study: 'Study Space',
      more: 'More',
      mindmap: 'Mind Map',
      progress: 'Progress',
      manual: 'Handbook',
      space: 'My Space',
      settings: 'AI Settings',
      history: 'History',
      trace: 'Logs',
      needKey: 'Enter API Key',
      toDark: 'Dark mode',
      toLight: 'Light mode',
      toEn: 'English',
      toZh: '中文',
    },
    common: {
      back: 'Back',
      save: 'Save',
      cancel: 'Cancel',
      delete: 'Delete',
      edit: 'Edit',
      close: 'Close',
      refresh: 'Refresh',
      loading: 'Loading…',
      search: 'Search',
      clear: 'Clear filters',
      empty: 'Nothing here yet',
    },
    page: {
      knowledgeTitle: 'Knowledge Base',
      importTitle: 'Import Documents',
      chatTitle: 'Course Q&A',
      wrongbookTitle: 'Wrong-Answer Book',
      progressTitle: 'Learning Progress',
      mindmapTitle: 'Mind Map',
      studyTitle: 'Study Space',
      transcribeTitle: 'Speech to Text',
      transcribeBack: 'Back to Plan',
    },
    trPage: {
      lead: 'Turn a lecture recording, a voice note, or a clip recorded on your phone into text. Recognition runs offline on our own server — audio is never sent to any third-party API.',
      engineDown: 'Speech recognition engine unavailable',
      pickTitle: 'Choose or drop an audio file',
      pickHint: 'mp3 / m4a / wav / ogg / webm, up to 8 minutes each',
      browse: 'Choose audio file',
      capture: 'Record on phone',
      current: 'Current audio',
      wait: 'Ready',
      done: 'Transcribed',
      result: 'Transcript (editable)',
      speed: '{x}× realtime',
      chars: '{n} characters',
      again: 'Use another',
      copy: 'Copy all',
      download: 'Download .txt',
      engine: 'Recognition engine',
      engineName: 'Model',
      limit: 'Max length',
      vad: 'Voice activity (VAD)',
      privacy: 'Vosk offline Chinese by default; whisper.cpp sidecar is used when installed. Audio is never sent to OpenAI, DeepSeek or any external service.',
      privacyWhisper: 'Running the whisper.cpp sidecar (multilingual ggml, -l zh). Audio stays on this server — not Docling ASR or openai-whisper.',
      toKb: 'Save to Knowledge Base',
      kbTitle: 'Note title',
      saveBtn: 'Save to Knowledge Base',
      saved: 'Saved',
      kbHint: 'Once saved, you can ask questions about this content in Course Q&A.',
      howto: 'Tips',
      howto1: 'Formats',
      howto2: 'Accuracy',
      howto2v: 'Best on Mandarin',
      howto3: 'Long audio',
      howto3v: 'Split it',
      howtoTip: 'The small model struggles with casual speech, dialects and proper nouns. Edit the transcript in the box before saving it.',
    },
    // Accounts & permissions (deleting knowledge base content is admin-only)
    auth: {
      title: 'Sign in',
      login: 'Sign in',
      logout: 'Sign out',
      signupTitle: 'Create account',
      signinSub: 'Sign in to manage your knowledge base and study plans',
      signupSub: 'Sign up to import materials and generate study plans',
      username: 'Username',
      usernamePlaceholder: 'Enter your username',
      password: 'Password',
      passwordPlaceholder: 'Enter your password',
      confirmPlaceholder: 'Repeat your password',
      signup: 'Sign up',
      signingUp: 'Signing up\u2026',
      needBoth: 'Please enter both username and password',
      mismatch: 'The two passwords do not match',
      failed: 'Sign-in failed',
      signupFailed: 'Sign-up failed',
      loggingIn: 'Signing in\u2026',
      togglePw: 'Show or hide password',
      signedInAs: 'Signed in as',
      roleAdmin: 'Admin',
      roleUser: 'Member',
      adminHint: 'You are an admin \u2014 you can delete knowledge base content.',
      userHint: 'Members can view, import and ask. Deleting content requires an admin.',
      noAccount: 'No account yet?',
      haveAccount: 'Already have an account?',
      goSignup: 'Sign up now',
      goSignin: 'Sign in',
      signinNote: 'Members can view, import and ask; deleting content requires an admin.',
      signupNote: 'New accounts are members: view, import and ask. Deleting content requires an admin.',
      adminOnly: 'Admin only',
      adminOnlyTip: 'Deleting knowledge base content requires an admin account',
      changePw: 'Change password',
      changePwSub: 'Use the new password next time you sign in',
      oldPwPlaceholder: 'Current password',
      newPwPlaceholder: 'New password (at least 6 characters)',
      changePwConfirmPlaceholder: 'Repeat the new password',
      changing: 'Submitting\u2026',
      changePwShort: 'New password must be at least 6 characters',
      changePwMismatch: 'The two new passwords do not match',
      changePwOk: 'Password updated. Use it next time you sign in',
      manage: 'Manage accounts',
      manageSub: 'Create accounts, change roles, reset passwords or delete',
      createAccount: 'Create account',
      newUsernamePlaceholder: 'New username',
      newPasswordPlaceholder: 'Initial password (at least 6 characters)',
      role: 'Role',
      toAdmin: 'Make admin',
      toUser: 'Make member',
      resetPw: 'Reset password',
      del: 'Delete',
      resetPwPrompt: 'New password for "{name}" (at least 6 characters):',
      confirmDel: 'Delete account "{name}"? This cannot be undone.',
      empty: 'No accounts yet',
      back: 'Back',
    },
    plan: {
      outline: 'Course Outline',
      resources: 'Recommended Resources',
      days: 'Study Plan',
      export: 'Export',
      generate: 'Generate',
    },
  },
}

/**
 * 合并两份来源：
 *   - MANUAL：手工维护，key 形如 nav.course（点号路径，便于阅读与复用）
 *   - auto-*：脚本从模板抽取，key 形如 courseForm.1（平铺，量大）
 * 两边 key 空间不重叠，直接展开合并即可。
 */
const PACKS = {
  'zh-CN': { ...MANUAL['zh-CN'], ...autoZh },
  'en-US': { ...MANUAL['en-US'], ...autoEn },
}

const lang = ref('zh-CN')
let inited = false

function resolve(pack, path) {
  // 自动抽取的 key 是平铺的（courseForm.1），先直接命中；
  // 没命中再按点号路径逐层下钻（nav.course）
  if (Object.prototype.hasOwnProperty.call(pack, path)) return pack[path]
  return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), pack)
}

function apply(l) {
  lang.value = PACKS[l] ? l : 'zh-CN'
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lang.value
  }
  try {
    localStorage.setItem(KEY, lang.value)
  } catch (_) {
    /* 隐私模式写不了，忽略 */
  }
}

export function useI18n() {
  if (!inited && typeof window !== 'undefined') {
    inited = true
    let saved = ''
    try {
      saved = localStorage.getItem(KEY) || ''
    } catch (_) {
      saved = ''
    }
    // 没选过就看浏览器语言：zh 开头用中文，其余用英文
    if (!saved) {
      const nav = (navigator.language || 'zh-CN').toLowerCase()
      saved = nav.startsWith('zh') ? 'zh-CN' : 'en-US'
    }
    apply(saved)
  }

  /**
   * 取文案。缺翻译时逐级回退，永远不会返回 undefined。
   * @param {string} key 形如 'nav.course'
   * @param {object|string} [params] 插值变量 {n: 3}，模板里写 {n}。
   *   中英语序不同（「共 3 条」vs "3 in total"），必须参数化而不是字符串拼接。
   *   传字符串时按旧签名当 fallback。
   */
  function t(key, params) {
    // key 可能是 undefined（例如 v-for 里未配置的 labelKey），必须挡住，
    // 否则 resolve 里的 path.split 会抛 TypeError 把整个组件拖垮
    if (key == null || key === '') return typeof params === 'string' ? params : ''

    let v = resolve(PACKS[lang.value], key)
    if (v == null) v = resolve(PACKS['zh-CN'], key)
    if (v == null) v = typeof params === 'string' ? params : key

    if (params && typeof params === 'object') {
      Object.keys(params).forEach((k) => {
        v = String(v).split('{' + k + '}').join(String(params[k]))
      })
    }
    return v
  }

  return {
    t,
    lang,
    isEn: computed(() => lang.value === 'en-US'),
    setLang: apply,
    toggle: () => apply(lang.value === 'zh-CN' ? 'en-US' : 'zh-CN'),
  }
}

/**
 * 尚未抽取的文案（长尾部分），列在这里便于后续补齐：
 * - TourDialog / TourBubble（新手引导气泡）
 * - SettingsDialog（模型设置弹窗内部字段）
 * - WelcomeScreen 的三张介绍卡
 * - 各页面的空态提示、错误提示详情
 */
export const TO_BE_TRANSLATED = '见 i18n/index.js 文件末尾注释'
