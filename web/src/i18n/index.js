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
      course: '学习方案生成',
      knowledge: '知识库',
      import: '文档导入',
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
