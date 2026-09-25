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

const KEY = 'zjxt.lang'

const PACKS = {
  'zh-CN': {
    nav: {
      course: '学习方案生成',
      knowledge: '知识库',
      import: '文档导入',
      record: '录音转写',
      chat: '课程问答',
      wrongbook: '错题本',
      study: '自习空间',
      more: '更多',
      mindmap: '思维导图',
      progress: '学习进度',
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
      recordTitle: '课堂录音转写',
      chatTitle: '课程问答',
      wrongbookTitle: '错题本',
      progressTitle: '学习进度',
      mindmapTitle: '思维导图',
      studyTitle: '自习空间',
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
      course: 'Generate Plan',
      knowledge: 'Knowledge Base',
      import: 'Import Docs',
      record: 'Lecture Capture',
      chat: 'Course Q&A',
      wrongbook: 'Wrong-Answer Book',
      study: 'Study Space',
      more: 'More',
      mindmap: 'Mind Map',
      progress: 'Progress',
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
      recordTitle: 'Lecture Capture',
      chatTitle: 'Course Q&A',
      wrongbookTitle: 'Wrong-Answer Book',
      progressTitle: 'Learning Progress',
      mindmapTitle: 'Mind Map',
      studyTitle: 'Study Space',
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

const lang = ref('zh-CN')
let inited = false

function resolve(pack, path) {
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
   * @param {string} [fallback] 中英都缺时用
   */
  function t(key, fallback) {
    const v = resolve(PACKS[lang.value], key)
    if (v != null) return v
    const z = resolve(PACKS['zh-CN'], key)
    if (z != null) return z
    return fallback != null ? fallback : key
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
