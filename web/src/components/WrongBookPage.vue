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
import { usePet } from '@/composables/usePet'

const emit = defineEmits(['back', 'go-course', 'notify'])
defineProps({
  embedded: { type: Boolean, default: false },
})
const { t } = useI18n()
const { logExp, XP_WRONGBOOK_CONSOLIDATE, XP_REINFORCE_QUIZ_PER, quizAccMult } = usePet()

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

// ---------------- 错题重做 ----------------
// 取当前筛选出的全部错题，交给后端为每道生成一道同知识点的新题，再复用答题 / 判分 / 复盘。
const redo = ref({
  active: false,
  loading: false,
  error: '',
  quiz: null, // { quiz_id, course, difficulty, questions:[...] }（无答案）
  index: 0,
  picked: null,
  judged: null, // api.quizGrade 响应
  results: [], // [{id, correct, knowledge_point}]
  finished: false,
  report: null,
  awarded: false, // 重做结算经验只发一次
})
const redoDiff = ref('medium')
const RE_DO_DIFFS = [{ key: 'easy' }, { key: 'medium' }, { key: 'hard' }]

const redoCurrent = computed(() =>
  redo.value.quiz ? redo.value.quiz.questions[redo.value.index] : null)
const redoTotal = computed(() =>
  redo.value.quiz ? redo.value.quiz.questions.length : 0)

function redoTypeLabel(q) {
  const k = QTYPE_KEYS[q]
  return k ? t(k) : ''
}

function startRedo() {
  if (!items.value.length) return
  redo.value = {
    active: true, loading: true, error: '', quiz: null,
    index: 0, picked: null, judged: null, results: [], finished: false, report: null, awarded: false,
  }
  const ids = items.value.map((i) => i.id)
  api.quizFromWrongbook(ids, redoDiff.value)
    .then((res) => {
      if (!res.ok) {
        redo.value.error = res.error || t('wrongBookRedo.genFail')
        redo.value.loading = false
        return
      }
      redo.value.quiz = res
      redo.value.loading = false
    })
    .catch((e) => {
      redo.value.error = `${t('wrongBookRedo.genFail')}：${e.message}`
      redo.value.loading = false
    })
}

function redoSelect(key) {
  if (redo.value.judged) return
  redo.value.picked = key
}
function redoToggleMulti(key) {
  if (redo.value.judged) return
  const arr = Array.isArray(redo.value.picked) ? redo.value.picked.slice() : []
  const i = arr.indexOf(key)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(key)
  redo.value.picked = arr
}
function redoIsPicked(key) {
  const cur = redoCurrent.value
  if (!cur) return false
  if (cur.type === 'multi') return Array.isArray(redo.value.picked) && redo.value.picked.includes(key)
  return redo.value.picked === key
}
function redoSelectedForSubmit() {
  const cur = redoCurrent.value
  if (!cur) return null
  if (cur.type === 'multi') return Array.isArray(redo.value.picked) ? redo.value.picked : []
  return redo.value.picked
}
async function redoSubmit() {
  const cur = redoCurrent.value
  if (!cur) return
  const sel = redoSelectedForSubmit()
  if (cur.type === 'multi') {
    if (!Array.isArray(sel) || sel.length < 1) {
      emit('notify', { type: 'warn', text: t('quizPage.errPickAtLeast') })
      return
    }
  } else if (cur.type === 'judge') {
    if (sel !== '0' && sel !== '1') {
      emit('notify', { type: 'warn', text: t('quizPage.errPickOne') })
      return
    }
  } else if (!sel) {
    emit('notify', { type: 'warn', text: t('quizPage.errPickOne') })
    return
  }
  try {
    const g = await api.quizGrade(redo.value.quiz.quiz_id, cur.id, sel)
    redo.value.judged = g
    redo.value.results.push({ id: cur.id, correct: g.correct, knowledge_point: g.knowledge_point })
  } catch (e) {
    emit('notify', { type: 'error', text: `${t('quizPage.errGrade')}：${e.message}` })
  }
}
function redoIsCorrectKey(key) {
  const j = redo.value.judged
  if (!j) return false
  const a = j.answer
  if (Array.isArray(a)) return a.includes(key)
  return String(a) === String(key)
}
function redoFmtAnswer(ans, type) {
  if (type === 'judge') return ans === 1 ? t('quizPage.judgeWrong') : t('quizPage.judgeRight')
  if (Array.isArray(ans)) return ans.join('')
  return ans
}
async function redoNext() {
  redo.value.judged = null
  redo.value.picked = null
  const q = redo.value.quiz
  if (!q) return
  if (redo.value.index + 1 >= q.questions.length) {
    if (redo.value.awarded) {
      redo.value.finished = true
      return
    }
    redo.value.finished = true
    // 经验梯度 + 关联强化：重做错题按正确率巩固，正确率够高则强化「答题闯关」
    const totalQ = redo.value.results.length
    const correctQ = redo.value.results.filter((r) => r.correct).length
    const acc = totalQ > 0 ? correctQ / totalQ : 0
    // 错题巩固：复习每答对 1 题的巩固经验（高于新题）
    logExp('错题巩固', Math.round(correctQ * XP_WRONGBOOK_CONSOLIDATE))
    // 关联强化：重做错题直接强化「答题闯关」
    if (acc >= 0.6) {
      logExp('关联强化·答题闯关', Math.round(correctQ * XP_REINFORCE_QUIZ_PER * quizAccMult(acc)))
    }
    redo.value.awarded = true
    try {
      redo.value.report = await api.quizReport(q.quiz_id)
    } catch (e) {
      redo.value.report = null
      emit('notify', { type: 'error', text: `${t('quizPage.errReport')}：${e.message}` })
    }
    return
  }
  redo.value.index += 1
}
function exitRedo() {
  redo.value = {
    active: false, loading: false, error: '', quiz: null,
    index: 0, picked: null, judged: null, results: [], finished: false, report: null, awarded: false,
  }
  load()
}
</script>

<template>
  <!-- 错题重做：取当前筛选出的错题，为每道生成同知识点新题并复用答题 / 判分 / 复盘 -->
  <section v-if="redo.active" class="wb">
    <header class="wb-head">
      <div>
        <p class="kicker">Redo</p>
        <h1>{{ t('wrongBookRedo.title') }}</h1>
        <p class="sub">{{ t('wrongBookRedo.countHint', { n: redoTotal }) }}</p>
      </div>
      <div class="head-actions">
        <button type="button" class="btn btn-ghost" @click="exitRedo">{{ t('wrongBookRedo.back') }}</button>
      </div>
    </header>

    <div v-if="redo.loading" class="empty">{{ t('wrongBookRedo.loading') }}</div>

    <div v-else-if="redo.error" class="empty">
      <p class="e-ico">⚠️</p>
      <p class="e-title">{{ redo.error }}</p>
      <button type="button" class="btn btn-primary" @click="exitRedo">{{ t('wrongBookRedo.back') }}</button>
    </div>

    <!-- 答题中 -->
    <div v-else-if="redo.quiz && !redo.finished" class="quiz-redo">
      <div class="q-meta">
        <span>{{ redo.index + 1 }} / {{ redoTotal }}</span>
        <span>{{ t('quizPage.diff.' + redo.quiz.difficulty) }}</span>
        <span v-if="redoCurrent" class="q-type">{{ redoTypeLabel(redoCurrent.type) }}</span>
      </div>
      <p class="q-stem">{{ redoCurrent && redoCurrent.stem }}</p>

      <template v-if="redoCurrent && redoCurrent.type !== 'multi'">
        <button
          v-for="o in redoCurrent.options"
          :key="o.key"
          type="button"
          class="opt"
          :class="{
            picked: redoIsPicked(o.key) && !redo.judged,
            right: redo.judged && redoIsCorrectKey(o.key),
            wrong: redo.judged && !redo.judged.correct && redoIsPicked(o.key),
          }"
          :disabled="!!redo.judged"
          @click="redoSelect(o.key)"
        >
          <b>{{ o.key }}</b> {{ o.text }}
        </button>
      </template>
      <template v-else>
        <button
          v-for="o in redoCurrent.options"
          :key="o.key"
          type="button"
          class="opt"
          :class="{
            picked: redoIsPicked(o.key) && !redo.judged,
            right: redo.judged && redoIsCorrectKey(o.key),
            wrong: redo.judged && !redo.judged.correct && redoIsPicked(o.key),
          }"
          :disabled="!!redo.judged"
          @click="redoToggleMulti(o.key)"
        >
          <b>{{ o.key }}</b> {{ o.text }}
          <span v-if="redoIsPicked(o.key)" class="chk">✓</span>
        </button>
      </template>

      <div v-if="redoCurrent && !redo.judged" class="q-actions">
        <button type="button" class="btn btn-accent" @click="redoSubmit">{{ t('quizPage.submit') }}</button>
      </div>
      <div v-else-if="redo.judged" class="verdict" :class="redo.judged.correct ? 'good' : 'bad'">
        <p class="v-line">
          <b>{{ redo.judged.correct ? t('quizPage.right') : t('quizPage.wrong') }}</b>
          <span v-if="!redo.judged.correct"> · {{ t('quizPage.answerIs') }} {{ redoFmtAnswer(redo.judged.answer, redo.judged.type) }}</span>
        </p>
        <p class="v-exp">{{ redo.judged.explanation }}</p>
        <p class="v-kp">{{ t('quizPage.kp') }}：{{ redo.judged.knowledge_point }}</p>
        <button type="button" class="btn btn-accent" @click="redoNext">
          {{ redo.index + 1 >= redoTotal ? t('quizPage.finish') : t('quizPage.next') }}
        </button>
      </div>
    </div>

    <!-- 复盘 -->
    <div v-else-if="redo.finished" class="summary">
      <p v-if="!redo.report" class="muted">{{ t('quizPage.reportGenerating') }}</p>
      <template v-else>
        <div class="report-card">
          <p class="s-score">{{ t('wrongBookRedo.scoreLine', { score: redo.report.score, total: redo.report.total }) }}</p>
          <p class="s-sub">{{ t('quizPage.reportAccuracy') }}：{{ Math.round(redo.report.accuracy * 100) }}%</p>
        </div>

        <div class="replay">
          <p class="s-label">{{ t('quizPage.reportReplay') }}</p>
          <div
            v-for="(it, i) in redo.report.questions"
            :key="it.id"
            class="replay-item"
            :class="it.correct ? 'good' : 'bad'"
          >
            <p class="r-stem">{{ i + 1 }}. {{ it.stem }}</p>
            <p class="r-line">
              <span :class="it.correct ? 'good' : 'bad'">{{ it.correct ? t('quizPage.right') : t('quizPage.wrong') }}</span>
              · {{ t('quizPage.reportUser') }}：{{ redoFmtAnswer(it.user_answer, it.type) }}
              · {{ t('quizPage.reportAnswer') }}：{{ redoFmtAnswer(it.correct_answer, it.type) }}
            </p>
            <p class="r-exp">{{ it.explanation }}</p>
            <p class="r-kp">{{ t('quizPage.kp') }}：{{ it.knowledge_point }}</p>
          </div>
        </div>

        <div class="weak" v-if="redo.report.weak_points && redo.report.weak_points.length">
          <p class="s-label">{{ t('quizPage.reportWeak') }}</p>
          <ul>
            <li v-for="w in redo.report.weak_points" :key="w.knowledge_point">
              {{ w.knowledge_point }}（错 {{ w.wrong }} 次）
            </li>
          </ul>
        </div>

        <div class="q-actions">
          <button type="button" class="btn btn-accent" @click="exitRedo">{{ t('wrongBookRedo.back') }}</button>
        </div>
        <p class="muted centered">{{ t('wrongBookRedo.done') }}</p>
      </template>
    </div>
  </section>

  <section v-if="!redo.active" class="wb">
    <header v-if="!embedded" class="wb-head">
      <div>
        <p class="kicker">Wrong book</p>
        <h1>{{ t('page.wrongbookTitle') }}</h1>
        <p class="sub">{{ t('wrongBookPage.9') }}</p>
      </div>
      <div class="head-actions">
        <button type="button" class="btn btn-primary" @click="openAdd">{{ t('wrongBookPage.10') }}</button>
        <template v-if="!embedded && items.length">
          <select v-model="redoDiff" class="f-select" :title="t('wrongBookRedo.diffLabel')">
            <option v-for="d in RE_DO_DIFFS" :key="d.key" :value="d.key">{{ t('quizPage.diff.' + d.key) }}</option>
          </select>
          <button type="button" class="btn btn-secondary" @click="startRedo">{{ t('wrongBookRedo.title') }}</button>
        </template>
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

/* ---------- 错题重做（复用答题 / 判分 / 复盘） ---------- */
.btn-secondary {
  border: 1px solid var(--primary);
  background: var(--primary-soft);
  color: var(--primary-dark);
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 13px;
  cursor: pointer;
}

.btn-secondary:hover {
  background: var(--primary);
  color: #fff;
}

.quiz-redo {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.q-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  flex-wrap: wrap;
}

.q-type {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1px 8px;
}

.q-stem {
  font-size: 15px;
  font-weight: 500;
  line-height: 1.7;
}

.opt {
  display: block;
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-primary);
  border-radius: 10px;
  min-height: 44px;
  padding: 10px 14px;
  margin-bottom: 8px;
  font-size: 14px;
  line-height: 1.6;
}

.opt b {
  margin-right: 8px;
}

.opt.picked {
  border-color: var(--accent);
}

.opt.right {
  border-color: #2e7d32;
  background: rgba(46, 125, 50, 0.08);
}

.opt.wrong {
  border-color: #c62828;
  background: rgba(198, 40, 40, 0.06);
}

.chk {
  float: right;
  color: var(--accent);
}

.verdict {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.verdict.good b {
  color: #2e7d32;
}

.verdict.bad b {
  color: #c62828;
}

.v-exp {
  font-size: 13.5px;
  line-height: 1.7;
}

.v-kp {
  font-size: 12px;
  color: var(--text-secondary);
}

.summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.report-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  background: rgba(46, 125, 50, 0.05);
}

.s-score {
  font-size: 16px;
  font-weight: 500;
}

.s-sub {
  font-size: 13px;
  color: var(--text-secondary);
}

.replay {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.replay-item {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
}

.replay-item.good {
  border-left: 3px solid #2e7d32;
}

.replay-item.bad {
  border-left: 3px solid #c62828;
}

.r-stem {
  font-weight: 500;
  line-height: 1.6;
}

.r-line .good {
  color: #2e7d32;
}

.r-line .bad {
  color: #c62828;
}

.r-exp {
  color: var(--text-secondary);
  line-height: 1.6;
  margin-top: 4px;
}

.r-kp {
  font-size: 12px;
  color: var(--text-secondary);
}

.weak ul {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 13px;
}

.weak li {
  margin-bottom: 2px;
}

.muted.centered {
  text-align: center;
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
