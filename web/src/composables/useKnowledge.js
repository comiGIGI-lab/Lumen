/**
 * useKnowledge —— 知识库数据层（对接后端真实接口）
 *
 * ⚠️ 这个文件原来是一份**纯前端演示数据**（硬编码 8 条假笔记、假文档、假分块，
 *    写入接口没接）。现在改成调 /api/knowledge 系列接口，数据是真的。
 *
 * 后端存的是**扁平**的知识库条目：{id, title, content, tags, created_at}
 * 界面要的是三层结构：**笔记 → 关联文档 → 分块**
 * 这里做一次映射（groupEntries）：
 *
 *   · 导入自文件（条目带 #pdf / #md / #txt / #image / #vision 标签）
 *     → 按「来源名」聚成一条**笔记**，该文件切出的每个块 = 一条**分块**
 *   · 手工新建 / 粘贴的条目 → 各自一条笔记，它自己就是唯一的分块
 *
 *   为什么按来源聚合而不是「一条目一笔记」：一次导入 10 块会往侧栏塞 10 条，
 *   而按来源聚合正好对应界面上那一行「文档」（一份文件 = 一行），
 *   分块预览也就自然填满了。
 *
 * 备注（remark）仍然是**只存本机 localStorage** —— 界面上那句
 * 「数据留在这台浏览器」本来就是这个意思，后端没有对应字段。
 */

import { computed, ref } from 'vue'
import { api } from '@/api/client'

export const TAG_LABEL = {
  'high-math': '高数',
  english: '英语',
  mistakes: '错题',
  others: '其他',
}

/** 从文件导入的条目会带这些标签之一 */
const FILE_TAGS = ['pdf', 'md', 'markdown', 'txt', 'text', 'docx', 'pptx', 'image', 'vision']

/** 后端扩展名标签 → 界面上的文档类型（TYPE_LABEL 的键） */
const TYPE_OF = {
  pdf: 'pdf',
  md: 'md',
  markdown: 'md',
  txt: 'txt',
  text: 'txt',
  docx: 'docx',
  pptx: 'pptx',
  image: 'image',
  vision: 'image',
  paste: 'note',
  note: 'note',
}

/** 分块标题形如「第3章 导数与微分 · 2/5」→ 取出「来源名」 */
const CHUNK_TITLE_RE = /^(.+?)\s*·\s*\d+\s*\/\s*\d+$/

function normalizeTags(tags) {
  if (Array.isArray(tags)) return tags
  if (typeof tags === 'string') return tags.split(',').map((t) => t.trim()).filter(Boolean)
  return []
}

/** 后端是「2026-09-24 15:53:48」→ 界面上想显示「09-24 15:53」 */
function fmtTime(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(s || '')
  return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]}` : (s || '—')
}

/**
 * 把后端条目映射成界面上的标签分组。
 * 后端没有「学科」概念，这里按标题/标签里的关键词归到界面上已有的几个 chip，
 * 认不出来就归到「其他」——只是为了那几个筛选按钮有意义，不影响数据本身。
 */
function guessTag(text) {
  const s = String(text || '').toLowerCase()
  if (/错题|错因|易错/.test(s)) return 'mistakes'
  if (/英语|english|长难句|听力|阅读/.test(s)) return 'english'
  if (/高数|数学|积分|导数|微分|矩阵|代数|概率|极限|统计|线性/.test(s)) return 'high-math'
  return 'others'
}

/** 把扁平条目聚成 {notes, docsByNote, chunksByDoc, docEntries} */
function groupEntries(items) {
  const groups = []
  const byBase = new Map()

  for (const raw of items || []) {
    const tags = normalizeTags(raw.tags)
    const srcTag = tags
      .map((t) => String(t).replace(/^#/, '').toLowerCase())
      .find((t) => FILE_TAGS.includes(t)) || ''
    const title = String(raw.title || '未命名')
    const m = CHUNK_TITLE_RE.exec(title)
    const base = (m ? m[1] : title).trim() || title
    const entry = { ...raw, tags, srcTag, base }

    if (srcTag) {
      let g = byBase.get(base)
      if (!g) {
        g = { key: `src:${base}`, base, type: srcTag, items: [] }
        byBase.set(base, g)
        groups.push(g)
      }
      g.items.push(entry)
    } else {
      groups.push({ key: `n:${raw.id}`, base: title, type: srcTag || 'note', items: [entry] })
    }
  }

  const notes = []
  const docsByNote = {}
  const chunksByDoc = {}
  const docEntries = {} // docId → 该文档对应的条目 id 列表（删除时要用）

  for (const g of groups) {
    const first = g.items[0]
    const docId = `doc:${g.key}`
    const created = fmtTime(first.created_at)
    const total = g.items.length

    notes.push({
      id: g.key,
      title: g.base,
      tag: guessTag(`${g.base} ${g.items.map((e) => e.tags.join(' ')).join(' ')}`),
      created,
      updated: created,
      remark: '',
      chunkCount: total,
      entryIds: g.items.map((e) => e.id),
    })

    docsByNote[g.key] = [{
      id: docId,
      name: total > 1 ? `${g.base}（${total} 块）` : g.base,
      type: TYPE_OF[g.type] || 'note',
      status: 'ready',
      chunks: total,
    }]

    chunksByDoc[docId] = g.items.map((e) => ({
      id: `${docId}#${e.id}`,
      src: e.title,
      text: e.content || '',
      entryId: e.id,
    }))
    docEntries[docId] = g.items.map((e) => e.id)
  }

  return { notes, docsByNote, chunksByDoc, docEntries }
}

// ---------------- 单例状态 ----------------
const notes = ref([])
const docsByNote = ref({})
const chunksByDoc = ref({})
const docEntries = ref({})
const currentId = ref('')
const loading = ref(false)
const error = ref('')
const lastQuery = ref('')
let loadedOnce = false

const REMARK_KEY = 'study-liu-kb-remarks'

function loadRemarks() {
  try {
    return JSON.parse(localStorage.getItem(REMARK_KEY) || '{}')
  } catch (_) {
    return {}
  }
}

function saveRemark(noteId, text) {
  try {
    const all = loadRemarks()
    all[String(noteId)] = text
    localStorage.setItem(REMARK_KEY, JSON.stringify(all))
  } catch (_) {
    /* 隐私模式下 localStorage 可能不可用，忽略即可 */
  }
}

function applyGroups(groups) {
  const remarks = loadRemarks()
  notes.value = groups.notes.map((n) => ({ ...n, remark: remarks[String(n.id)] || '' }))
  docsByNote.value = groups.docsByNote
  chunksByDoc.value = groups.chunksByDoc
  docEntries.value = groups.docEntries
  if (!notes.value.some((n) => n.id === currentId.value)) {
    currentId.value = notes.value[0]?.id || ''
  }
}

export function useKnowledge() {
  const current = computed(
    () => notes.value.find((n) => n.id === currentId.value) || notes.value[0] || null,
  )
  const currentDocs = computed(() => (current.value ? docsByNote.value[current.value.id] || [] : []))
  const currentChunks = computed(() => {
    const list = []
    currentDocs.value.forEach((doc) => {
      if (doc.status !== 'ready') return
      ;(chunksByDoc.value[doc.id] || []).forEach((c) => list.push({ ...c, docId: doc.id }))
    })
    return list
  })

  /**
   * 拉取知识库。
   * @param {string} q 关键词。传了就走后端的打分检索（能命中改写过的说法）；
   *                   不传就取全部。空结果时保留上一次的数据不闪屏。
   */
  async function refresh(q = '', options = {}) {
    loading.value = true
    error.value = ''
    lastQuery.value = q
    try {
      const res = await api.knowledgeList(q, 50, options)
      applyGroups(groupEntries(res.items || []))
      loadedOnce = true
    } catch (e) {
      error.value = e.message || String(e)
      if (!loadedOnce) applyGroups(groupEntries([]))
    } finally {
      loading.value = false
    }
  }

  function pickNote(id) {
    if (notes.value.some((n) => n.id === id)) currentId.value = id
  }

  /** 新建笔记（真实写入后端；正文留空作为待导入材料的容器） */
  async function createNote(title = '未命名笔记', options = {}) {
    const name = String(title || '').trim() || '未命名笔记'
    try {
      const res = await api.knowledgeCreate({
        title: name,
        content: '',
        tags: ['#manual'],
        scope: options.scope || 'private',
        category: options.category || '',
      })
      await refresh(lastQuery.value)
      pickNote(`src:${name}`) // 若已存在同名来源会被并到同一组
      return res.id
    } catch (e) {
      error.value = e.message || String(e)
      return ''
    }
  }

  /** 删除某个「文档」= 删掉它底下的全部条目 */
  async function removeDoc(noteId, docId) {
    const ids = docEntries.value[docId] || []
    if (!ids.length) return
    try {
      for (const id of ids) await api.knowledgeDelete(id)
      await refresh(lastQuery.value)
    } catch (e) {
      error.value = e.message || String(e)
    }
  }

  /**
   * 保留这个函数名只是为了不改动页面模板。
   * 后端导入是同步的（上传完就已经解析入库），不存在"解析失败待重试"的中间态，
   * 所以这里只做一次刷新。
   */
  async function retryDoc() {
    await refresh(lastQuery.value)
  }

  /** 备注只存本机 */
  function setRemark(noteId, text) {
    saveRemark(noteId, text)
  }

  /** 首次进入时懒加载一次 */
  function ensureLoaded() {
    if (!loadedOnce && !loading.value) refresh('')
  }

  return {
    // 状态
    notes,
    docsByNote,
    chunksByDoc,
    currentId,
    current,
    currentDocs,
    currentChunks,
    loading,
    error,
    lastQuery,
    // 操作
    refresh,
    ensureLoaded,
    pickNote,
    createNote,
    removeDoc,
    retryDoc,
    setRemark,
  }
}
