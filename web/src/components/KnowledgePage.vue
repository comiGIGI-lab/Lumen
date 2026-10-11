<script setup>
/**
 * KnowledgePage —— 主应用内正式知识库页（已接真实后端）
 *
 * 数据来自 /api/knowledge；笔记/文档/分块的层级由 useKnowledge 从后端的扁平条目映射出来。
 * 搜索框走**后端的打分检索**（分词 + 字段加权 + 覆盖率），所以「换个说法问」也能命中，
 * 这正是把「整句子串匹配」换掉的意义所在。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import SnakeBar from './SnakeBar.vue'
import TranscribePage from './TranscribePage.vue'
import MindMapPage from './MindMapPage.vue'
import WrongBookPage from './WrongBookPage.vue'
import { api } from '@/api/client'
import { useKnowledge } from '@/composables/useKnowledge'

const emit = defineEmits(['back', 'open-import', 'go-course', 'notify'])
const props = defineProps({
  section: { type: String, default: 'notes' },
})
const { t } = useI18n()

const SCOPES = computed(() => [
  { id: 'all', label: t('kb.scopeAll') },
  { id: 'private', label: t('kb.scopePrivate') },
  { id: 'public', label: t('kb.scopePublic') },
])

function typeLabel(type) {
  return { pdf: 'PDF', image: t('kb.typeImage'), md: 'Markdown', txt: t('kb.typeText'), note: t('kb.typeNote'), docx: 'Word', pptx: 'PPT' }[type] || type
}
function statusLabel(status) {
  return { ready: t('kb.stReady'), parsing: t('kb.stParsing'), queue: t('kb.stQueue'), failed: t('kb.stFailed') }[status] || status
}

const ACCEPT = '.pdf,.md,.markdown,.txt,.text,.docx,.pptx,.png,.jpg,.jpeg,.webp,.bmp,.gif'
const MAX_FILES = 10
const MAX_BYTES = 16 * 1024 * 1024

const {
  notes,
  currentId,
  current,
  currentDocs,
  currentChunks,
  loading,
  error,
  lastQuery,
  refresh,
  ensureLoaded,
  pickNote,
  createNote,
  removeDoc,
  retryDoc,
  setRemark,
} = useKnowledge()

ensureLoaded()

const KB_SECTIONS = ['speech', 'map', 'wrong']
const section = ref(KB_SECTIONS.includes(props.section) ? props.section : 'notes')
const SECTIONS = computed(() => [
  { id: 'notes', label: t('kb.sNotes') },
  { id: 'speech', label: t('kb.sSpeech') },
  { id: 'map', label: t('kb.sMap') },
  { id: 'wrong', label: t('kb.sWrong') },
])

const scope = ref('all')
const category = ref('')
const categories = ref([])
const uploadScope = ref('private')
const uploadCategory = ref('')
const keyword = ref('')
const showImport = ref(false)
const showShare = ref(false)
const shareCode = ref('')
const redeemCode = ref('')
const shareNote = ref('')
const savedHint = ref(false)
const picked = ref([])
const dragOn = ref(false)
const running = ref(false)
const importNote = ref('')
const fileInput = ref(null)
const caps = ref(null)
let seq = 0
let searchTimer = 0
let hintTimer = 0

api.knowledgeCapabilities().then((c) => { caps.value = c }).catch(() => {})

/** 搜索防抖 300ms 后打后端；清空则回到全量列表 */
async function loadCategories() {
  try {
    const res = await api.knowledgeCategories()
    categories.value = res.categories || []
  } catch (_) {
    categories.value = []
  }
}

const CATEGORY_LABEL = {
  '#import': 'kb.catImport',
  '#test': 'kb.catTest',
  '#t': 'kb.catUnnamed',
}

function categoryLabel(raw) {
  const name = String(raw || '').trim()
  if (CATEGORY_LABEL[name]) return t(CATEGORY_LABEL[name])
  return name.replace(/^#/, '') || t('kb.catUnnamed')
}

function tagLabel(tag) {
  const map = { 'high-math': 'kb.tagHighMath', english: 'kb.tagEnglish', mistakes: 'kb.tagMistakes', others: 'kb.tagOthers' }
  return map[tag] ? t(map[tag]) : (tag || t('kb.tagOthers'))
}

function listOptions() {
  return {
    scope: scope.value === 'all' ? '' : scope.value,
    category: category.value,
  }
}

watch(() => props.section, (next) => {
  section.value = KB_SECTIONS.includes(next) ? next : 'notes'
})

watch(keyword, (q) => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => refresh(String(q || '').trim(), listOptions()), 300)
})
watch([scope, category], () => refresh(keyword.value.trim(), listOptions()))
loadCategories()

const sectionLead = computed(() => {
  if (section.value === 'speech') return t('kb.leadSpeech')
  if (section.value === 'map') return t('kb.leadMap')
  if (section.value === 'wrong') return t('kb.leadWrong')
  return t('knowledgePage.6')
})

const empty = computed(() => !loading.value && notes.value.length === 0)

const filtered = computed(() => notes.value)

function reload() {
  refresh(lastQuery.value || '', listOptions())
  loadCategories()
}

function clearBrowse() {
  scope.value = 'all'
  category.value = ''
  keyword.value = ''
}

function downloadNote() {
  if (!current.value) return
  const docs = currentDocs.value
    .map((doc) => `## ${doc.name}`)
    .join('\n')
  const body = currentChunks.value
    .map((chunk) => `### ${chunk.src}\n\n${chunk.text}`)
    .join('\n\n')
  const text = `# ${current.value.title}\n\n${docs}\n\n${body}\n`
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${current.value.title || t('kb.sNotes')}.txt`
  link.click()
  URL.revokeObjectURL(url)
}

async function makeShare() {
  const ids = current.value?.entryIds || []
  if (!ids.length) return
  shareNote.value = ''
  try {
    const res = await api.knowledgeShare(ids)
    shareCode.value = res.code || ''
    shareNote.value = t('kb.shareMade')
  } catch (e) {
    shareNote.value = e.message || String(e)
  }
}

async function redeemShare() {
  const code = redeemCode.value.trim()
  if (!code) return
  shareNote.value = ''
  try {
    const res = await api.knowledgeRedeem(code)
    redeemCode.value = ''
    shareNote.value = t('kb.redeemed', { n: res.count || 0 })
    scope.value = 'private'
    await refresh('', listOptions())
  } catch (e) {
    shareNote.value = e.message || String(e)
  }
}

async function copyCode() {
  if (!shareCode.value || !navigator.clipboard) return
  await navigator.clipboard.writeText(shareCode.value)
  shareNote.value = t('kb.copied')
}

async function addCategory() {
  const name = window.prompt(t('kb.newCatPh'), '')
  if (name === null) return
  const categoryName = name.trim()
  if (!categoryName) return
  await api.knowledgeCreateCategory(categoryName)
  uploadCategory.value = categoryName
  await loadCategories()
}

function newNote() {
  const title = window.prompt(t('kb.newNotePh'), t('kb.newNoteDefault'))
  if (title === null) return
  createNote(title.trim() || t('kb.newNoteDefault'), {
    scope: uploadScope.value,
    category: uploadCategory.value,
    list: listOptions(),
  })
}

function saveRemark() {
  if (!current.value) return
  setRemark(current.value.id, current.value.remark || '')
  savedHint.value = true
  clearTimeout(hintTimer)
  hintTimer = setTimeout(() => {
    savedHint.value = false
  }, 1400)
}

async function deleteDoc(doc) {
  if (!current.value || !doc) return
  if (!window.confirm(t('kb.deleteDoc', { name: doc.name, n: doc.chunks }))) return
  await removeDoc(current.value.id, doc.id)
}

// ---------- 页内快速导入（与导入文档页共用后端的同一个接口）----------
function fmtSize(bytes) {
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB'
  if (bytes >= 1024) return Math.round(bytes / 1024) + ' KB'
  return bytes + ' B'
}

function openImport() {
  showImport.value = true
  picked.value = []
  importNote.value = ''
  dragOn.value = false
}

function closeImport() {
  if (running.value) return
  showImport.value = false
  picked.value = []
}

function addFiles(fileList) {
  const room = MAX_FILES - picked.value.length
  const list = Array.from(fileList || []).slice(0, Math.max(0, room))
  list.forEach((file) => {
    if (file.size > MAX_BYTES) {
      importNote.value = t('kb.skipBig', { name: file.name, size: fmtSize(file.size) })
      return
    }
    picked.value.push({
      id: 'k' + ++seq,
      file,
      name: file.name,
      size: fmtSize(file.size),
      status: 'waiting',
      chunks: 0,
      error: '',
    })
  })
}

function onPickClick() {
  if (running.value) return
  fileInput.value?.click()
}

function onFileChange(e) {
  addFiles(e.target.files)
  e.target.value = ''
}

function onDrop(e) {
  e.preventDefault()
  dragOn.value = false
  if (!running.value) addFiles(e.dataTransfer?.files)
}

async function startUpload() {
  if (running.value || !picked.value.length) return
  running.value = true
  importNote.value = t('kb.uploading')
  let ok = 0
  for (const row of picked.value) {
    row.status = 'uploading'
    try {
      const res = await api.knowledgeImport([row.file], {
        title: current.value?.title || '', // 归到当前正在看的这条笔记下
        scope: uploadScope.value,
        category: uploadCategory.value,
      })
      const r = (res.results || [])[0] || {}
      if (r.ok) {
        row.status = 'ready'
        row.chunks = r.chunks || 0
        ok += 1
      } else {
        row.status = 'failed'
        row.error = r.error || t('kb.importFail')
      }
    } catch (e) {
      row.status = 'failed'
      row.error = e.message || String(e)
    }
  }
  await refresh('', listOptions())
  keyword.value = ''
  running.value = false
  importNote.value = ok
    ? `${t('kb.imported', { ok })}${picked.value.length - ok ? `，${picked.value.length - ok} ${t('kb.stFailed')}` : ''}。`
    : t('kb.importFailedAll')
}

onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  clearTimeout(hintTimer)
})
</script>

<template>
  <div class="kb">
    <div class="kb-bar">
      <div>
        <p class="eyebrow">Knowledge</p>
        <h2>{{ t('knowledgePage.5') }}</h2>
        <p class="lead">{{ sectionLead }}</p>
      </div>
      <div class="kb-actions">
        <button type="button" class="ghost" @click="emit('back')">{{ t('knowledgePage.7') }}</button>
        <template v-if="section === 'notes'">
          <button type="button" class="ghost" @click="emit('open-import')">{{ t('knowledgePage.8') }}</button>
          <button type="button" class="ok" @click="openImport">{{ t('knowledgePage.9') }}</button>
        </template>
      </div>
    </div>

    <div class="kb-sections" role="tablist" :aria-label="t('knowledgePage.5')">
      <button
        v-for="item in SECTIONS"
        :key="item.id"
        type="button"
        role="tab"
        :class="{ on: section === item.id }"
        :aria-selected="section === item.id"
        @click="section = item.id"
      >{{ item.label }}</button>
    </div>

    <TranscribePage
      v-if="section === 'speech'"
      embedded
      @back="section = 'notes'"
      @open-knowledge="section = 'notes'"
    />
    <MindMapPage
      v-else-if="section === 'map'"
      embedded
      @back="section = 'notes'"
      @notify="emit('notify', $event)"
    />
    <WrongBookPage
      v-else-if="section === 'wrong'"
      embedded
      @back="section = 'notes'"
      @go-course="emit('go-course')"
      @notify="emit('notify', $event)"
    />

    <template v-else>
    <div class="kb-groups">
      <div class="kb-group">
        <span class="kb-group-name">{{ t('kb.range') }}</span>
        <div class="seg" role="group" :aria-label="t('kb.range')">
          <button
            v-for="item in SCOPES"
            :key="item.id"
            type="button"
            :class="{ on: scope === item.id }"
            :aria-pressed="scope === item.id"
            @click="scope = item.id"
          >{{ item.label }}</button>
        </div>
      </div>
      <div class="kb-group">
        <span class="kb-group-name">{{ t('kb.cat') }}</span>
        <div class="cats" role="group" :aria-label="t('kb.cat')">
          <button type="button" :class="{ on: category === '' }" @click="category = ''">{{ t('kb.catAll') }}</button>
          <button
            v-for="item in categories"
            :key="item"
            type="button"
            :class="{ on: category === item }"
            :title="item"
            @click="category = item"
          >{{ categoryLabel(item) }}</button>
          <button type="button" class="ghost" @click="addCategory">{{ t('kb.catNew') }}</button>
        </div>
      </div>
      <div class="kb-group">
        <span class="kb-group-name">{{ t('kb.new') }}</span>
        <select v-model="uploadScope" :aria-label="t('kb.new')">
          <option value="private">{{ t('kb.scopePrivate') }}</option>
          <option value="public">{{ t('kb.scopePublic') }}</option>
        </select>
        <select v-model="uploadCategory" :aria-label="t('kb.cat')">
          <option value="">{{ t('kb.catNone') }}</option>
          <option v-for="item in categories" :key="`upload-${item}`" :value="item">{{ categoryLabel(item) }}</option>
        </select>
      </div>
    </div>

    <div class="kb-search">
      <input v-model="keyword" type="search" :placeholder="t('knowledgePage.1')" />
      <button type="button" class="ghost" @click="showShare = true">{{ t('kb.share') }}</button>
      <button v-if="keyword" type="button" class="ghost" @click="keyword = ''">{{ t('kb.clearSearch') }}</button>
      <span v-if="loading" class="kb-state">{{ t('knowledgePage.10') }}</span>
      <span v-else-if="error" class="kb-state err">{{ error }}</span>
      <span v-else-if="lastQuery" class="kb-state">{{ t('kb.showing', { q: lastQuery }) }}</span>
    </div>

    <div v-if="empty" class="empty">
      <h3>{{ t('knowledgePage.11') }}</h3>
      <p>{{ t('knowledgePage.12') }}</p>
      <ol>
        <li><b>{{ t('knowledgePage.13') }}</b><span>{{ t('knowledgePage.14') }}</span></li>
        <li><b>{{ t('knowledgePage.15') }}</b><span>{{ t('knowledgePage.16') }}</span></li>
        <li><b>{{ t('knowledgePage.17') }}</b><span>{{ t('knowledgePage.18') }}</span></li>
      </ol>
      <div class="empty-btns">
        <button type="button" class="ok" @click="openImport">{{ t('knowledgePage.19') }}</button>
        <button type="button" class="ghost" @click="emit('open-import')">{{ t('knowledgePage.20') }}</button>
        <button type="button" class="ghost" @click="section = 'speech'">{{ t('kb.sSpeech') }}</button>
        <button type="button" class="ghost" @click="section = 'map'">{{ t('kb.sMap') }}</button>
        <button type="button" class="ghost" @click="emit('go-course')">{{ t('knowledgePage.21') }}</button>
      </div>
    </div>

    <div v-else class="shell">
      <aside>
        <div class="sb-head">
          <span>{{ t('knowledgePage.22') }}</span>
          <em>{{ t('stat.knowledge', { n: filtered.length }) }}</em>
          <button type="button" class="ghost small" @click="reload">{{ t('knowledgePage.23') }}</button>
        </div>
        <div class="note-list">
          <button
            v-for="n in filtered"
            :key="n.id"
            type="button"
            class="note"
            :class="{ on: n.id === currentId }"
            @click="pickNote(n.id)"
          >
            <span class="note-t">{{ n.title }}</span>
            <span class="chip">{{ tagLabel(n.tag) }}</span>
            <span class="note-d">{{ n.updated }}</span>
          </button>
          <p v-if="!filtered.length" class="none">
          {{ t('knowledgePage.24') }}
          <button type="button" class="ghost small" @click="clearBrowse">{{ t('kb.returnAll') }}</button>
        </p>
        </div>
        <button type="button" class="ghost new" @click="newNote">{{ t('knowledgePage.25') }}</button>
      </aside>

      <section v-if="current" class="detail">
        <div class="note-facts">
          <span>{{ current.scope === 'private' ? t('kb.private') : t('kb.public') }}</span>
          <span v-if="current.category">{{ categoryLabel(current.category) }}</span>
          <button type="button" class="ghost small" @click="showShare = true">{{ t('kb.shareNote') }}</button>
          <button type="button" class="ghost small" @click="downloadNote">{{ t('kb.download') }}</button>
        </div>

        <label class="title-lab">
          <span>{{ t('knowledgePage.26') }}</span>
          <input v-model="current.title" readonly :title="t('knowledgePage.2')" />
        </label>

        <dl class="meta">
          <div><dt>{{ t('knowledgePage.27') }}</dt><dd>{{ current.created }}</dd></div>
          <div><dt>{{ t('knowledgePage.28') }}</dt><dd>{{ current.updated }}</dd></div>
          <div><dt>{{ t('knowledgePage.29') }}</dt><dd>{{ tagLabel(current.tag) }}</dd></div>
          <div><dt>{{ t('knowledgePage.30') }}</dt><dd>{{ currentDocs.length }}</dd></div>
        </dl>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{{ t('knowledgePage.31') }}</th>
                <th>{{ t('knowledgePage.32') }}</th>
                <th>{{ t('knowledgePage.33') }}</th>
                <th>{{ t('knowledgePage.34') }}</th>
                <th>{{ t('knowledgePage.35') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!currentDocs.length">
                <td colspan="5" class="empty-cell">{{ t('knowledgePage.36') }}</td>
              </tr>
              <tr v-for="d in currentDocs" :key="d.id" :class="{ fail: d.status === 'failed' }">
                <td>{{ d.name }}</td>
                <td>{{ typeLabel(d.type) }}</td>
                <td>
                  <span class="st" :class="d.status">{{ statusLabel(d.status) }}</span>
                  <span v-if="d.status === 'parsing'" class="pct">{{ d.progress }}%</span>
                  <SnakeBar v-if="d.status === 'parsing'" :progress="d.progress" status="parsing" />
                </td>
                <td>{{ d.chunks || '—' }}</td>
                <td class="ops">
                  <button v-if="d.status === 'failed'" type="button" class="danger" @click="retryDoc(d)">{{ t('knowledgePage.37') }}</button>
                  <button type="button" class="ghost small" @click="deleteDoc(d)">{{ t('knowledgePage.38') }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="chunks">
          <h3>{{ t('knowledgePage.39') }}</h3>
          <p v-if="!currentDocs.length" class="empty-chunk">{{ t('knowledgePage.40') }}<button type="button" class="ok" @click="openImport">{{ t('knowledgePage.41') }}</button>
          </p>
          <p v-else-if="!currentChunks.length" class="empty-chunk">{{ t('knowledgePage.42') }}<button type="button" class="ok" @click="openImport">{{ t('knowledgePage.43') }}</button>
          </p>
          <article v-for="c in currentChunks" :key="c.id">
            <header><span>{{ c.src }}</span></header>
            <p>{{ c.text }}</p>
          </article>
        </div>

        <div class="remark">
          <h3>{{ t('knowledgePage.44') }}</h3>
          <textarea v-model="current.remark" rows="4" :placeholder="t('knowledgePage.3')"></textarea>
          <div class="remark-row">
            <button type="button" class="ok" @click="saveRemark">{{ t('knowledgePage.45') }}</button>
            <em :class="{ show: savedHint }">{{ t('knowledgePage.46') }}</em>
            <span>{{ t('knowledgePage.47') }}</span>
          </div>
        </div>
      </section>
    </div>

    <Teleport to="body">
      <div v-if="showShare" class="mask" @click.self="showShare = false">
        <div class="modal" role="dialog" :aria-label="t('kb.shareNote')">
          <header>
            <h3>{{ t('kb.shareTitle', { title: current?.title || t('kb.sNotes') }) }}</h3>
            <button type="button" class="x" @click="showShare = false">×</button>
          </header>
          <p class="modal-hint">{{ t('kb.shareHint') }}</p>
          <div class="share-row">
            <button type="button" class="ok" @click="makeShare">{{ t('kb.makeShare') }}</button>
            <strong v-if="shareCode">{{ shareCode }}</strong>
            <button v-if="shareCode" type="button" class="ghost" @click="copyCode">{{ t('kb.copy') }}</button>
            <button type="button" class="ghost" @click="downloadNote">{{ t('kb.download') }}</button>
          </div>
          <label class="redeem">
            <span>{{ t('kb.redeemLabel') }}</span>
            <input v-model="redeemCode" type="text" maxlength="12" :placeholder="t('kb.redeemPh')" />
          </label>
          <p v-if="shareNote" class="demo-note">{{ shareNote }}</p>
          <footer>
            <button type="button" class="ghost" @click="showShare = false">{{ t('knowledgePage.51') }}</button>
            <button type="button" class="ok" @click="redeemShare">{{ t('kb.redeemBtn') }}</button>
          </footer>
        </div>
      </div>
      <div v-if="showImport" class="mask" @click.self="closeImport">
        <div class="modal" role="dialog" :aria-label="t('knowledgePage.4')">
          <header>
            <h3>{{ t('knowledgePage.48') }}</h3>
            <button type="button" class="x" :disabled="running" @click="closeImport">×</button>
          </header>
          <div
            class="drop"
            :class="{ on: dragOn }"
            @click="onPickClick"
            @dragenter.prevent="dragOn = true"
            @dragover.prevent="dragOn = true"
            @dragleave.prevent="dragOn = false"
            @drop="onDrop"
          >
            <p>{{ t('knowledgePage.49') }}</p>
            <span>{{ t('knowledgePage.50') }}</span>
            <input
              ref="fileInput"
              type="file"
              multiple
              :accept="ACCEPT"
              class="hidden-input"
              @change="onFileChange"
            />
          </div>
          <p class="modal-hint">{{ t('kb.importHint', { title: current?.title || t('knowledgePageX.1') }) }}</p>
          <div v-if="picked.length" class="up">
            <div v-for="row in picked" :key="row.id" class="up-row">
              <div class="up-meta">
                <span>{{ row.name }}</span>
                <em v-if="row.status === 'ready'">{{ t('kb.chunksDone', { n: row.chunks }) }}</em>
                <em v-else-if="row.status === 'failed'" class="err">{{ row.error }}</em>
                <em v-else>{{ row.status === 'uploading' ? t('knowledgePageX.2') : t('knowledgePageX.3') }}</em>
              </div>
            </div>
          </div>
          <p v-if="importNote" class="demo-note">{{ importNote }}</p>
          <footer>
            <button type="button" class="ghost" :disabled="running" @click="closeImport">{{ t('knowledgePage.51') }}</button>
            <button type="button" class="ok" :disabled="running || !picked.length" @click="startUpload">
              {{ running ? t('knowledgePageX.4') : t('knowledgePageX.5') }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
    </template>
  </div>
</template>

<style scoped>
.kb {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
.kb-sections {
  display: flex;
  gap: 0;
  width: fit-content;
  max-width: 100%;
  overflow-x: auto;
  border-bottom: 1px solid var(--border);
}
.kb-sections button {
  min-height: 36px;
  padding: 0 14px;
  white-space: nowrap;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
}
.kb-sections button.on {
  color: var(--text);
  border-bottom-color: var(--accent);
}
.kb-bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.eyebrow {
  font-family: var(--font-serif);
  font-style: italic;
  letter-spacing: 0.16em;
  color: var(--accent);
  font-size: 13px;
}
h2 {
  font-size: 28px;
  margin-top: 4px;
}
.lead {
  max-width: 40em;
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.7;
}
.demo-note {
  margin: 10px 0 0;
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-muted);
}
.kb-actions,
.empty-btns,
.remark-row,
.sb-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.kb-groups {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.kb-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-height: 36px;
}
.kb-group-name {
  flex: none;
  width: 3em;
  color: var(--text-muted);
  font-size: 12px;
}
.kb-group select {
  border: 1px solid var(--border);
  background: var(--bg-card);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 13px;
}
.kb-tools,
.kb-search {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.seg,
.cats,
.note-facts,
.share-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.seg button,
.cats button {
  border: 1px solid var(--border);
  background: var(--bg-card);
  border-radius: 1000px;
  padding: 6px 12px;
  font-size: 13px;
}
.seg button.on {
  background: var(--text-primary);
  color: var(--bg-app);
  border-color: var(--text-primary);
}
.cats button.on {
  background: var(--bg-soft);
  color: var(--text-primary);
  border-color: var(--accent);
}
.note-facts span {
  border: 1px solid var(--border);
  background: var(--bg-soft);
  border-radius: 1000px;
  padding: 4px 10px;
  font-size: 12px;
}
.redeem {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}
.kb-search input,
.title-lab input,
textarea,
.redeem input {
  width: 100%;
  border: 1px solid var(--border);
  background: var(--bg-card);
  padding: 10px 12px;
  border-radius: 1000px;
}
textarea {
  border-radius: 12px;
  resize: vertical;
}
.shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
}
aside {
  min-width: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 10px;
}
.sb-head {
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}
.note-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 420px;
  overflow: auto;
}
.note {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 8px;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  padding: 8px;
}
.note.on {
  background: var(--bg-soft);
  box-shadow: inset 3px 0 0 var(--accent);
}
.note-t {
  grid-column: 1;
  font-size: 13px;
}
.note .chip {
  grid-column: 2;
}
.note-d {
  grid-column: 1 / -1;
  font-size: 11px;
  color: var(--text-muted);
}
.new {
  width: 100%;
  margin-top: 8px;
}
/* 「没有匹配的笔记」原来只共享了颜色规则，没有内边距 ——
   .note-list 是 flex 容器、自身无 padding，所以这行字会贴着侧栏左边缘，
   和上面 .note 按钮里的文字对不齐。这里补上与 .note 一致的内缩。 */
.none {
  padding: 6px 12px;
  line-height: 1.6;
}
.detail {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.chip {
  border: 1px solid var(--border);
  background: var(--bg-soft);
  border-radius: 1000px;
  padding: 4px 10px;
  font-size: 12px;
}
.chip.on {
  background: #191919;
  color: #fff;
  border-color: var(--text-primary);
}
.meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 12px;
}
dt {
  color: var(--text-muted);
  font-size: 12px;
}
.table-wrap {
  overflow-x: auto;
  background: var(--bg-card);
  border: 1px solid var(--border);
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 560px;
  font-size: 13px;
}
th, td {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
.empty-cell {
  color: var(--text-muted);
  font-size: 12px;
}
.fail {
  background: var(--primary-soft);
}
.st.ready { color: #2e7d32; }
.st.parsing, .st.queue { color: var(--accent); }
.st.failed { color: var(--error); }
.pct { font-size: 11px; color: var(--text-muted); margin-left: 6px; }
.chunks article,
.remark,
.title-lab,
.empty {
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 14px;
}
.chunks header {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-muted);
}
.ok, .ghost, .danger {
  border-radius: 1000px;
  padding: 7px 14px;
  font-size: 13px;
}
.ok {
  border: 1px solid var(--primary);
  background: var(--primary);
  color: #fff;
}
.ghost {
  border: 1px solid var(--border);
  background: var(--bg-card);
}
.danger {
  border: 1px solid var(--error);
  color: var(--error);
  background: var(--bg-card);
}
.remark-row em {
  opacity: 0;
  font-style: normal;
  color: #2e7d32;
  font-size: 12px;
}
.remark-row em.show { opacity: 1; }
.remark-row span, .none, .tm, .empty-chunk { color: var(--text-muted); font-size: 12px; }
.empty-chunk {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin: 0;
  line-height: 1.7;
}
.ops {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.small {
  padding: 4px 10px;
  font-size: 12px;
}
.empty ol {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 0;
  list-style: none;
}
.empty li {
  border: 1px solid var(--border);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.empty b { font-weight: 400; font-family: var(--font-serif); }
.mask {
  position: fixed;
  inset: 0;
  z-index: 170;
  background: rgba(25, 25, 25, 0.28);
  display: grid;
  place-items: center;
  padding: 16px;
}
.modal {
  width: min(520px, 100%);
  background: var(--bg-app);
  border: 1px solid var(--border);
  padding: 16px;
}
.modal header, .modal footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.x { border: none; background: transparent; font-size: 20px; }
.drop {
  margin: 12px 0;
  padding: 36px 16px;
  border: 1px dashed var(--border);
  background: var(--bg-soft);
  text-align: center;
  cursor: pointer;
}
.drop.on { border-color: var(--accent); background: var(--warning-soft); }
.up { display: flex; flex-direction: column; gap: 10px; margin: 12px 0; }
.up-meta { display: flex; justify-content: space-between; font-size: 12px; }
/* 接真实后端后补的几条 */
.hidden-input { display: none; }
.kb-state { margin-left: 10px; font-size: 12px; color: var(--text-muted); }
.kb-state.err { color: #c62828; }
.modal-hint { margin: 10px 0 0; font-size: 12px; color: var(--text-muted); line-height: 1.6; }
.up-meta em.err { color: #c62828; }

/* 断点从 860 下调到 760：860 偏高，窗口稍窄（或系统缩放 150%）就压成一栏，
   侧栏变成横向滚动条、右侧详情挤到下面，页面看着很空。 */
@media (max-width: 760px) {
  .shell { grid-template-columns: 1fr; }
  .note-list { flex-direction: row; overflow-x: auto; max-height: none; }
  .note { min-width: 190px; }
  .meta, .empty ol { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 390px) {
  h2 { font-size: 22px; }
  .meta, .empty ol { grid-template-columns: 1fr; }
  .kb-actions { width: 100%; }
  .kb-actions button { flex: 1 1 auto; }
}
</style>
