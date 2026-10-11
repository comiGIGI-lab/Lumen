<script setup>
/**
 * WrongBookPage —— 独立错题本
 *
 * 数据全部走 /api/wrongbook（按浏览器隔离，落盘见 tools/wrong_book_store.py）。
 * 支持：按课程 / 关键词 / 掌握状态 / 来源 / 题型筛选，
 * 新增、编辑、标记掌握、记一次复习、删除。
 *
 * 题型（single / multi / judge）与来源（quiz / manual）不落库——wrong_book_store
 * 的存储契约是封闭的，题型由 tags 里的 "题型:多选" 派生，服务端每次读的时候
 * 挂在 item.qtype / item.qtype_label 上返回，前端只负责显示与筛选。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/api/client'
import { useI18n } from '@/i18n'

const emit = defineEmits(['back', 'go-course', 'notify'])
defineProps({
  embedded: { type: Boolean, default: false },
})
const { t } = useI18n()

const loading = ref(false)
const items = ref([])
const courses = ref([])
const stats = ref({
  total: 0, mastered: 0, unmastered: 0, due: 0, ratio: 0, by_course: [],
})

const keyword = ref('')
const courseFilter = ref('')
const statusFilter = ref('')
/** '' 全部；'quiz' 只看学习闯关带来的；'manual' 只看手工加的 */
const sourceFilter = ref('')
/** '' 全部；single | multi | judge */
const typeFilter = ref('')

const QTYPE_KEYS = {
  single: 'wrongBookQuiz.single',
  multi: 'wrongBookQuiz.multi',
  judge: 'wrongBookQuiz.judge',
}

/** 题型徽标文案。认不出来的题型（老数据没带标签）直接不显示，不留裸 key */
function qtypeLabel(q) {
  const k = QTYPE_KEYS[q]
  return k ? t(k) : ''
}

/** null = 表单关闭；有值 = 打开（id 为 null 表示新增） */
const form = ref(null)
const saving = ref(false)
const formError = ref('')

const blankForm = () => ({
  id: null,
  course: courseFilter.value || '',
  question: '',
  my_answer: '',
  answer: '',
  reason: '',
  tagsText: '',
})

const percent = computed(() => Math.round((stats.value.ratio || 0) * 100))

const activeHint = computed(() => {
  const parts = []
  if (courseFilter.value) parts.push(`课程「${courseFilter.value}」`)
  if (statusFilter.value === 'unmastered') parts.push('未掌握')
  if (statusFilter.value === 'mastered') parts.push('已掌握')
  if (typeFilter.value) parts.push(qtypeLabel(typeFilter.value))
  if (sourceFilter.value === 'quiz') parts.push(t('wrongBookQuiz.fromQuiz'))
  if (sourceFilter.value === 'manual') parts.push(t('wrongBookQuiz.manual'))
  if (keyword.value.trim()) parts.push(`含「${keyword.value.trim()}」`)
  return parts.join(' · ')
})

async function load() {
  loading.value = true
  try {
    const data = await api.wrongBookList({
      course: courseFilter.value,
      q: keyword.value.trim(),
      status: statusFilter.value,
      source: sourceFilter.value,
      type: typeFilter.value,
    })
    items.value = data.items || []
    if (data.stats) stats.value = data.stats
    courses.value = data.courses || []
  } catch (e) {
    emit('notify', { type: 'error', text: `加载失败：${e.message}` })
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openAdd() {
  form.value = blankForm()
  formError.value = ''
}

function openEdit(it) {
  form.value = {
    id: it.id,
    course: it.course || '',
    question: it.question || '',
    my_answer: it.my_answer || '',
    answer: it.answer || '',
    reason: it.reason || '',
    tagsText: (it.tags || []).join(', '),
  }
  formError.value = ''
}

async function save() {
  const f = form.value
  if (!f) return
  if (!f.question.trim()) {
    formError.value = '题干不能为空'
    return
  }
  saving.value = true
  formError.value = ''
  const payload = {
    course: f.course.trim(),
    question: f.question.trim(),
    my_answer: f.my_answer.trim(),
    answer: f.answer.trim(),
    reason: f.reason.trim(),
    tags: f.tagsText.split(/[,，]/).map((t) => t.trim()).filter(Boolean),
  }
  try {
    if (f.id) {
      await api.wrongBookUpdate(f.id, payload)
      emit('notify', { type: 'success', text: '已保存修改' })
    } else {
      await api.wrongBookAdd({ ...payload, source: 'manual' })
      emit('notify', { type: 'success', text: '已加入错题本' })
    }
    form.value = null
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function toggleMastered(it) {
  try {
    await api.wrongBookUpdate(it.id, { mastered: !it.mastered })
    await load()
  } catch (e) {
    emit('notify', { type: 'error', text: `操作失败：${e.message}` })
  }
}

async function review(it, mastered) {
  try {
    await api.wrongBookReview(it.id, mastered)
    await load()
    emit('notify', {
      type: 'success',
      text: mastered ? '已复习，并标记为掌握' : '已记一次复习',
    })
  } catch (e) {
    emit('notify', { type: 'error', text: `操作失败：${e.message}` })
  }
}

async function remove(it) {
  const head = (it.question || '').slice(0, 60)
  if (!window.confirm(`确定删除这道错题吗？\n\n${head}`)) return
  try {
    await api.wrongBookDelete(it.id)
    await load()
    emit('notify', { type: 'success', text: '已删除' })
  } catch (e) {
    emit('notify', { type: 'error', text: `删除失败：${e.message}` })
  }
}

function resetFilter() {
  keyword.value = ''
  courseFilter.value = ''
  statusFilter.value = ''
  sourceFilter.value = ''
  typeFilter.value = ''
  load()
}
</script>

<template>
  <section class="wb">
    <header v-if="!embedded" class="wb-head">
      <div>
        <p class="kicker">Wrong book</p>
        <h1>{{ t('page.wrongbookTitle') }}</h1>
        <p class="sub">{{ t('wrongBookPage.9') }}</p>
      </div>
      <div class="head-actions">
        <button type="button" class="btn btn-primary" @click="openAdd">{{ t('wrongBookPage.10') }}</button>
        <button v-if="!embedded" type="button" class="btn btn-ghost" @click="emit('back')">{{ t('wrongBookPage.11') }}</button>
      </div>
    </header>

    <!-- 概览 -->
    <div class="stat-row">
      <div class="stat">
        <span class="s-num">{{ stats.total }}</span>
        <span class="s-label">{{ t('wrongBookPage.12') }}</span>
      </div>
      <div class="stat">
        <span class="s-num">{{ stats.unmastered }}</span>
        <span class="s-label">{{ t('wrongBookPage.13') }}</span>
      </div>
      <div class="stat">
        <span class="s-num">{{ stats.mastered }}</span>
        <span class="s-label">{{ t('wrongBookPage.14') }}</span>
      </div>
      <div class="stat">
        <span class="s-num">{{ stats.due }}</span>
        <span class="s-label">{{ t('wrongBookPage.15') }}</span>
      </div>
      <div class="stat wide">
        <div class="bar" role="img" :aria-label="t('stat.mastered', { n: percent })">
          <i :style="{ width: percent + '%' }" />
        </div>
        <span class="s-label">{{ t('stat.mastered', { n: percent }) }}</span>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="filters">
      <input
        v-model="keyword"
        class="f-input"
        type="search"
        :placeholder="t('wrongBookPage.1')"
        @keyup.enter="load"
      />
      <select v-model="courseFilter" class="f-select" @change="load">
        <option value="">{{ t('wrongBookPage.16') }}</option>
        <option v-for="c in courses" :key="c" :value="c">{{ c }}</option>
      </select>
      <select v-model="sourceFilter" class="f-select" @change="load">
        <option value="">{{ t('wrongBookQuiz.allSource') }}</option>
        <option value="quiz">{{ t('wrongBookQuiz.fromQuiz') }}</option>
        <option value="manual">{{ t('wrongBookQuiz.manual') }}</option>
      </select>
      <select v-model="typeFilter" class="f-select" @change="load">
        <option value="">{{ t('wrongBookQuiz.allType') }}</option>
        <option value="single">{{ t('wrongBookQuiz.single') }}</option>
        <option value="multi">{{ t('wrongBookQuiz.multi') }}</option>
        <option value="judge">{{ t('wrongBookQuiz.judge') }}</option>
      </select>
      <div class="seg">
        <button
          type="button"
          :class="{ on: statusFilter === '' }"
          @click="statusFilter = ''; load()"
        >{{ t('wrongBookPage.17') }}</button>
        <button
          type="button"
          :class="{ on: statusFilter === 'unmastered' }"
          @click="statusFilter = 'unmastered'; load()"
        >{{ t('wrongBookPage.18') }}</button>
        <button
          type="button"
          :class="{ on: statusFilter === 'mastered' }"
          @click="statusFilter = 'mastered'; load()"
        >{{ t('wrongBookPage.19') }}</button>
      </div>
      <button type="button" class="btn btn-ghost sm" @click="load">{{ t('wrongBookPage.20') }}</button>
      <button v-if="activeHint" type="button" class="btn btn-ghost sm" @click="resetFilter">{{ t('wrongBookPage.21') }}</button>
      <span v-if="activeHint" class="f-hint">{{ activeHint }}</span>
    </div>

    <!-- 列表 -->
    <div v-if="loading" class="empty">{{ t('wrongBookPage.22') }}</div>

    <div v-else-if="!items.length" class="empty">
      <p class="e-ico">📕</p>
      <p class="e-title">{{ stats.total ? t('wrongBookPageX.1') : t('wrongBookPageX.2') }}</p>
      <p class="e-sub">
        {{ stats.total
          ? t('wrongBookPageX.3')
          : t('wrongBookPageX.4') }}
      </p>
      <button type="button" class="btn btn-primary" @click="openAdd">{{ t('wrongBookPage.23') }}</button>
    </div>

    <ul v-else class="list">
      <li v-for="it in items" :key="it.id" class="card" :class="{ mastered: it.mastered }">
        <div class="c-top">
          <span v-if="it.qtype" class="chip chip-type">{{ qtypeLabel(it.qtype) }}</span>
          <span v-if="it.source === 'quiz'" class="chip chip-quiz">{{ t('wrongBookQuiz.fromQuiz') }}</span>
          <span v-if="it.course" class="chip">{{ it.course }}</span>
          <span class="chip" :class="it.mastered ? 'chip-success' : 'chip-warn'">
            {{ it.mastered ? t('wrongBookPageX.5') : t('wrongBookPageX.6') }}
          </span>
          <span v-for="t in it.tags" :key="t" class="tag">#{{ t }}</span>
          <span class="spacer" />
          <span class="rev" :title="it.last_review_at || ''">复习 {{ it.review_count || 0 }} 次</span>
        </div>

        <p class="c-q">{{ it.question }}</p>

        <div class="c-body">
          <div v-if="it.my_answer" class="c-line wrong">
            <b>{{ t('wrongBookPage.24') }}</b>
            <span>{{ it.my_answer }}</span>
          </div>
          <div v-if="it.answer" class="c-line right">
            <b>{{ t('wrongBookPage.25') }}</b>
            <span>{{ it.answer }}</span>
          </div>
          <div v-if="it.reason" class="c-line">
            <b>{{ t('wrongBookPage.26') }}</b>
            <span>{{ it.reason }}</span>
          </div>
        </div>

        <div class="c-actions">
          <button type="button" class="btn btn-ghost sm" @click="review(it, null)">{{ t('wrongBookPage.27') }}</button>
          <button type="button" class="btn btn-ghost sm" @click="toggleMastered(it)">
            {{ it.mastered ? t('wrongBookPageX.7') : t('wrongBookPageX.8') }}
          </button>
          <button type="button" class="btn btn-ghost sm" @click="openEdit(it)">{{ t('wrongBookPage.28') }}</button>
          <button type="button" class="btn btn-ghost sm danger" @click="remove(it)">{{ t('wrongBookPage.29') }}</button>
        </div>
      </li>
    </ul>

    <!-- 表单 -->
    <div v-if="form" class="mask" @click.self="form = null">
      <div class="dialog" role="dialog" :aria-label="t('wrongBookPage.2')">
        <h2>{{ form.id ? t('wrongBookPageX.9') : t('wrongBookPageX.10') }}</h2>

        <label class="field">
          <span>{{ t('wrongBookPage.30') }}<em>*</em></span>
          <textarea v-model="form.question" rows="3" :placeholder="t('wrongBookPage.3')" />
        </label>

        <div class="row2">
          <label class="field">
            <span>{{ t('wrongBookPage.31') }}</span>
            <input v-model="form.course" type="text" :placeholder="t('wrongBookPage.4')" list="wb-courses" />
            <datalist id="wb-courses">
              <option v-for="c in courses" :key="c" :value="c" />
            </datalist>
          </label>
          <label class="field">
            <span>{{ t('wrongBookPage.32') }}</span>
            <input v-model="form.tagsText" type="text" :placeholder="t('wrongBookPage.5')" />
          </label>
        </div>

        <label class="field">
          <span>{{ t('wrongBookPage.33') }}</span>
          <textarea v-model="form.my_answer" rows="2" :placeholder="t('wrongBookPage.6')" />
        </label>

        <label class="field">
          <span>{{ t('wrongBookPage.34') }}</span>
          <textarea v-model="form.answer" rows="3" :placeholder="t('wrongBookPage.7')" />
        </label>

        <label class="field">
          <span>{{ t('wrongBookPage.35') }}</span>
          <input v-model="form.reason" type="text" :placeholder="t('wrongBookPage.8')" />
        </label>

        <p v-if="formError" class="f-err">{{ formError }}</p>

        <div class="d-actions">
          <button type="button" class="btn btn-primary" :disabled="saving" @click="save">
            {{ saving ? t('wrongBookPageX.11') : t('wrongBookPageX.12') }}
          </button>
          <button type="button" class="btn btn-ghost" @click="form = null">{{ t('wrongBookPage.36') }}</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.wb {
  max-width: 1000px;
  margin: 0 auto;
  padding: 4px 0 40px;
}

.wb-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.kicker {
  font-family: var(--font-serif);
  font-size: 11px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--primary);
}

.wb-head h1 {
  margin: 4px 0 6px;
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 400;
  color: var(--text-primary);
}

.sub {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 560px;
  line-height: 1.7;
}

.head-actions {
  display: flex;
  gap: 8px;
}

/* ---------- 概览 ---------- */
.stat-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr)) minmax(0, 2fr);
  gap: 10px;
  margin-bottom: 16px;
}

.stat {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat.wide {
  justify-content: center;
  gap: 8px;
}

.s-num {
  font-family: var(--font-serif);
  font-size: 24px;
  color: var(--text-primary);
  line-height: 1.1;
}

.s-label {
  font-size: 11.5px;
  color: var(--text-muted);
}

.bar {
  height: 7px;
  border-radius: 999px;
  background: var(--bg-soft);
  border: 1px solid var(--border);
  overflow: hidden;
}

.bar i {
  display: block;
  height: 100%;
  background: var(--primary);
  transition: width 0.3s ease;
}

/* ---------- 筛选 ---------- */
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.f-input,
.f-select {
  border: 1px solid var(--border);
  background: var(--bg-card);
  border-radius: 8px;
  padding: 7px 11px;
  font-size: 13px;
  color: var(--text-primary);
}

.f-input {
  flex: 1 1 220px;
  min-width: 160px;
}

.seg {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-card);
}

.seg button {
  border: none;
  background: transparent;
  padding: 7px 12px;
  font-size: 12.5px;
  color: var(--text-muted);
  border-right: 1px solid var(--border);
}

.seg button:last-child {
  border-right: none;
}

.seg button.on {
  background: var(--primary-soft);
  color: var(--primary-dark);
  font-weight: 600;
}

.f-hint {
  font-size: 11.5px;
  color: var(--text-faint);
}

/* ---------- 列表 ---------- */
.empty {
  text-align: center;
  padding: 44px 20px;
  background: var(--bg-card);
  border: 1px dashed var(--border-strong);
  border-radius: 12px;
  color: var(--text-muted);
}

.e-ico {
  font-size: 30px;
  margin: 0 0 8px;
}

.e-title {
  margin: 0 0 6px;
  font-size: 15px;
  color: var(--text-primary);
}

.e-sub {
  margin: 0 auto 16px;
  font-size: 13px;
  line-height: 1.75;
  max-width: 460px;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary-light);
  border-radius: 10px;
  padding: 14px 16px;
}

.card.mastered {
  border-left-color: #16a34a;
  opacity: 0.86;
}

.c-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.spacer {
  flex: 1;
}

/* 题型徽标：闯关题三种题型用不同底色区分，扫一眼就知道哪类错得多 */
.chip-type {
  background: var(--primary-soft);
  color: var(--primary-dark);
  font-weight: 600;
}

.chip-quiz {
  background: #eef2ff;
  color: #3730a3;
}

.tag {
  font-size: 11px;
  color: var(--text-muted);
}

.rev {
  font-size: 11px;
  color: var(--text-faint);
}

.c-q {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.6;
  word-break: break-word;
}

.c-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.c-line {
  display: flex;
  gap: 8px;
  font-size: 12.8px;
  line-height: 1.65;
  color: var(--text-secondary);
}

.c-line b {
  flex: none;
  width: 72px;
  font-weight: 600;
  color: var(--text-muted);
  font-size: 11.5px;
  padding-top: 1px;
}

.c-line span {
  word-break: break-word;
}

.c-line.wrong span {
  color: #b91c1c;
}

.c-line.right span {
  color: #15803d;
}

.c-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.btn.sm {
  padding: 5px 11px;
  font-size: 12px;
}

.btn.danger {
  color: #b91c1c;
  border-color: #f3c4c7;
}

.btn.danger:hover {
  background: var(--error-soft);
}

/* ---------- 表单弹窗 ---------- */
.mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(25, 25, 25, 0.35);
  display: grid;
  place-items: center;
  padding: 20px;
  overflow: auto;
}

.dialog {
  width: min(620px, 100%);
  background: var(--bg-card);
  border-radius: 14px;
  padding: 22px 24px 20px;
  box-shadow: var(--shadow);
}

.dialog h2 {
  margin: 0 0 16px;
  font-family: var(--font-serif);
  font-size: 19px;
  font-weight: 400;
  color: var(--text-primary);
}

.field {
  display: block;
  margin-bottom: 12px;
}

.field > span {
  display: block;
  margin-bottom: 5px;
  font-size: 12px;
  color: var(--text-muted);
}

.field em {
  font-style: normal;
  color: var(--primary);
}

.field input,
.field textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 11px;
  font-size: 13px;
  font-family: inherit;
  color: var(--text-primary);
  background: var(--bg-card);
  resize: vertical;
}

.field input:focus,
.field textarea:focus {
  outline: none;
  border-color: var(--primary-light);
}

.row2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.f-err {
  margin: 0 0 10px;
  font-size: 12.5px;
  color: #b91c1c;
}

.d-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 6px;
}

@media (max-width: 760px) {
  .stat-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .stat.wide {
    grid-column: 1 / -1;
  }
  .row2 {
    grid-template-columns: 1fr;
  }
}
</style>
