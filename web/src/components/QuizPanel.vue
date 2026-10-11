<script setup>
/**
 * QuizPanel —— 选择题闯关（复刻 yu-ai-learn 官网可行范围）
 *
 * 链路：选难度/题数/题型 → api.quizGenerate（知识库 RAG 出题，弱命中走 Tavily 兜底）
 * → 逐题作答 api.quizGrade（服务端判分，答案不下发前端）→ 即时对错讲解
 * → 答错写错题本（source: 'quiz'）→ 通关后 api.quizReport 复盘
 * → logExp 结算经验。全程 {{ }} 插值，不用 v-html。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from '@/i18n'
import { api, quizStreamUrl } from '@/api/client'
import { usePet } from '@/composables/usePet'

const props = defineProps({
  courseContext: { type: String, default: '' },
})
const emit = defineEmits(['notify'])
const { t } = useI18n()
const { logExp, XP_QUIZ_PER_Q } = usePet()

const difficulty = ref('medium')
const count = ref(5)
const qtype = ref('mixed') // single | multi | judge | mixed
const webSearch = ref(true) // 联网搜索开关（默认开；关/无 key/失败均降级为空上下文出题）
const lively = ref(false) // 轻松幽默：生活场景和比喻，默认关
const busy = ref(false)
const errorText = ref('')

/** 一局的完整状态。questions 是 generate 响应（无 answer） */
const run = ref(null) // { quiz_id, questions, retrieved, source }
const index = ref(0)
const picked = ref(null) // single/judge: 选项 key 字符串；multi: key 数组
const judged = ref(null) // grade 响应：{ correct, answer, explanation, knowledge_point, type }
const results = ref([]) // [{id, correct, knowledge_point}]
const finished = ref(false)
const report = ref(null) // quizReport 响应
const expected = ref(0)
const streamDone = ref(true)
let es = null

const current = computed(() => (run.value ? run.value.questions[index.value] : null))
const pastWrong = ref([])

function normStem(text) {
  return String(text || '').replace(/\s+/g, '').slice(0, 24)
}

async function loadPastWrong() {
  const course = String(props.courseContext || '').trim()
  if (!course) {
    pastWrong.value = []
    return
  }
  try {
    const data = await api.wrongBookList({ course, status: 'unmastered' })
    pastWrong.value = (data.items || []).map((item) => normStem(item.question)).filter(Boolean)
  } catch (_) {
    pastWrong.value = []
  }
}

function seenBefore(stem) {
  const key = normStem(stem)
  if (key.length < 6) return false
  return pastWrong.value.some((item) => item.includes(key) || key.includes(item))
}

onMounted(loadPastWrong)
const waitingNext = computed(() => (
  !!run.value && !finished.value && index.value >= run.value.questions.length && !streamDone.value
))
const score = computed(() => results.value.filter((r) => r.correct).length)

const DIFFS = [
  { key: 'easy' },
  { key: 'medium' },
  { key: 'hard' },
]
const TYPE_OPTIONS = [
  { key: 'single' },
  { key: 'multi' },
  { key: 'judge' },
  { key: 'mixed' },
]

function tpLabel(k) {
  const cap = k.charAt(0).toUpperCase() + k.slice(1)
  return t('quizPage.type' + cap)
}

function isPicked(key) {
  if (!current.value) return false
  if (current.value.type === 'multi') {
    return Array.isArray(picked.value) && picked.value.includes(key)
  }
  return picked.value === key
}

function choose(key) {
  if (judged.value) return
  picked.value = key
}

function toggleMulti(key) {
  if (judged.value) return
  const arr = Array.isArray(picked.value) ? picked.value.slice() : []
  const i = arr.indexOf(key)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(key)
  picked.value = arr
}

function closeStream() {
  if (es) {
    es.close()
    es = null
  }
}

function failStart(msg) {
  closeStream()
  busy.value = false
  streamDone.value = true
  if (!run.value) {
    errorText.value = msg || t('quizPage.errGenerate')
    emit('notify', { type: 'warn', text: errorText.value })
  }
}

async function start() {
  const course = (props.courseContext || '').trim()
  if (!course) {
    errorText.value = t('quizPage.errCourse')
    return
  }
  closeStream()
  busy.value = true
  errorText.value = ''
  run.value = null
  results.value = []
  finished.value = false
  report.value = null
  expected.value = Number(count.value) || 0
  streamDone.value = false
  index.value = 0
  picked.value = null
  judged.value = null

  const url = quizStreamUrl(course, {
    difficulty: difficulty.value,
    count: count.value,
    types: qtype.value,
    webSearch: webSearch.value,
    lively: lively.value,
  })
  es = new EventSource(url)
  es.addEventListener('meta', (ev) => {
    const data = JSON.parse(ev.data)
    expected.value = data.expected || expected.value
    run.value = {
      quiz_id: data.quiz_id,
      course: data.course,
      difficulty: data.difficulty,
      types: data.types,
      source: data.source,
      retrieved: data.retrieved || [],
      questions: run.value ? run.value.questions : [],
    }
    busy.value = false
  })
  es.addEventListener('question', (ev) => {
    const data = JSON.parse(ev.data)
    const q = data.question
    if (!q || !run.value) return
    if (!run.value.questions.some((x) => x.id === q.id)) {
      run.value.questions.push(q)
    }
    busy.value = false
    if (run.value.questions.length === 1) {
      emit('notify', { type: 'success', text: t('quizPage.started') })
    }
  })
  es.addEventListener('error', (ev) => {
    if (!ev.data) return
    try {
      const data = JSON.parse(ev.data)
      failStart(data.error || t('quizPage.errGenerate'))
    } catch (_) {
      /* 连接级错误走 onerror */
    }
  })
  es.addEventListener('done', (ev) => {
    let ok = true
    try {
      ok = JSON.parse(ev.data).ok !== false
    } catch (_) { /* 缺省视为结束 */ }
    streamDone.value = true
    busy.value = false
    closeStream()
    if (!ok && !run.value) failStart(t('quizPage.errGenerate'))
  })
  es.onerror = () => {
    if (streamDone.value) return
    if (!run.value) {
      // 连接没建立（反代不支持流式）时退回整卷接口，保证还能出题
      closeStream()
      api.quizGenerate(course, difficulty.value, count.value, qtype.value, webSearch.value, lively.value)
        .then((res) => {
          if (!res.ok) {
            failStart(res.error || t('quizPage.errGenerate'))
            return
          }
          run.value = res
          expected.value = (res.questions || []).length
          streamDone.value = true
          busy.value = false
          emit('notify', { type: 'success', text: t('quizPage.started') })
        })
        .catch((e) => failStart(`${t('quizPage.errGenerate')}：${e.message}`))
      return
    }
    streamDone.value = true
    busy.value = false
    closeStream()
  }
}

onBeforeUnmount(closeStream)

function _selectedForSubmit() {
  if (!current.value) return null
  if (current.value.type === 'multi') {
    return Array.isArray(picked.value) ? picked.value : []
  }
  return picked.value
}

async function submit() {
  if (!current.value || busy.value) return
  const sel = _selectedForSubmit()
  if (current.value.type === 'multi') {
    if (!Array.isArray(sel) || sel.length < 1) {
      errorText.value = t('quizPage.errPickAtLeast')
      return
    }
  } else if (current.value.type === 'judge') {
    if (sel !== '0' && sel !== '1') {
      errorText.value = t('quizPage.errPickOne')
      return
    }
  } else if (!sel) {
    errorText.value = t('quizPage.errPickOne')
    return
  }
  errorText.value = ''
  busy.value = true
  try {
    const g = await api.quizGrade(run.value.quiz_id, current.value.id, sel)
    judged.value = g
    results.value.push({ id: current.value.id, correct: g.correct, knowledge_point: g.knowledge_point })
    // 答错入错题本：回传**结构化题目**，渲染与「我的答案」格式化交给后端
    // wrongbook_quiz 统一处理——三种题型的答案编码不同（["A"] / ["A","C"] /
    // int 0-1），历史上前端自己拼字符串时多选只剩第一个选项的文字。
    if (!g.correct) {
      try {
        await api.wrongBookAddFromQuiz({
          course: props.courseContext || '',
          question: current.value,
          selected: sel,
          answer: g.answer,
          explanation: g.explanation,
          knowledge_point: g.knowledge_point,
          tags: [g.knowledge_point, '闯关'],
        })
      } catch (_) {
        /* 错题本写失败不阻塞闯关 */
      }
    }
  } catch (e) {
    errorText.value = `${t('quizPage.errGrade')}：${e.message}`
  } finally {
    busy.value = false
  }
}

function fmtAnswer(ans, type) {
  if (type === 'judge') return ans === 1 ? t('quizPage.judgeWrong') : t('quizPage.judgeRight')
  if (Array.isArray(ans)) return ans.join('')
  return ans
}

function isCorrectKey(key) {
  if (!judged.value) return false
  const a = judged.value.answer
  if (Array.isArray(a)) return a.includes(key)
  return String(a) === String(key)
}

async function next() {
  judged.value = null
  picked.value = null
  if (index.value + 1 >= run.value.questions.length) {
    if (!streamDone.value) {
      index.value += 1
      return
    }
    finished.value = true
    // 结算经验：每题 2 点，走既有 logExp 规则
    logExp('答题闯关', results.value.length * XP_QUIZ_PER_Q)
    emit('notify', { type: 'success', text: t('quizPage.done') })
    // 拉复盘
    busy.value = true
    try {
      report.value = await api.quizReport(run.value.quiz_id)
    } catch (e) {
      report.value = null
      errorText.value = `${t('quizPage.errReport')}：${e.message}`
    } finally {
      busy.value = false
    }
    return
  }
  index.value += 1
}

function reset() {
  closeStream()
  run.value = null
  finished.value = false
  report.value = null
  results.value = []
  errorText.value = ''
  streamDone.value = true
}
</script>

<template>
  <section class="card card-pad quiz">
    <div class="quiz-head">
      <div class="lead">{{ t('quizPage.lead') }}</div>
      <span v-if="courseContext" class="chip chip-brand">{{ courseContext }}</span>
      <span v-else class="muted">{{ t('quizPage.noCourse') }}</span>
    </div>

    <!-- 配置 + 开始 -->
    <div v-if="!run" class="setup">
      <div class="field">
        <span class="s-label">{{ t('quizPage.difficulty') }}</span>
        <div class="opts">
          <button
            v-for="d in DIFFS"
            :key="d.key"
            type="button"
            class="pill"
            :class="{ on: difficulty === d.key }"
            @click="difficulty = d.key"
          >
            {{ t('quizPage.diff.' + d.key) }}
          </button>
        </div>
      </div>
      <div class="field">
        <span class="s-label">{{ t('quizPage.count') }}</span>
        <div class="opts">
          <button
            v-for="n in [3, 5, 8]"
            :key="n"
            type="button"
            class="pill"
            :class="{ on: count === n }"
            @click="count = n"
          >
            {{ n }}
          </button>
        </div>
      </div>
      <div class="field">
        <span class="s-label">{{ t('quizPage.qtype') }}</span>
        <div class="opts">
          <button
            v-for="tp in TYPE_OPTIONS"
            :key="tp.key"
            type="button"
            class="pill"
            :class="{ on: qtype === tp.key }"
            @click="qtype = tp.key"
          >
            {{ tpLabel(tp.key) }}
          </button>
        </div>
      </div>
      <div class="field">
        <span class="s-label">{{ t('quizPage.webSearch') }}</span>
        <button
          type="button"
          class="pill"
          :class="{ on: webSearch }"
          @click="webSearch = !webSearch"
        >
          {{ webSearch ? t('quizPage.webSearchOn') : t('quizPage.webSearchOff') }}
        </button>
      </div>
      <div class="field">
        <span class="s-label">{{ t('quizPage.lively') }}</span>
        <button
          type="button"
          class="pill"
          :class="{ on: lively }"
          @click="lively = !lively"
        >
          {{ lively ? t('quizPage.livelyOn') : t('quizPage.livelyOff') }}
        </button>
      </div>
      <button type="button" class="btn btn-accent" :disabled="busy" @click="start">
        {{ busy ? t('quizPage.generating') : t('quizPage.start') }}
      </button>
      <p v-if="errorText" class="err">{{ errorText }}</p>
    </div>

    <!-- 答题 -->
    <div v-else-if="!finished" class="q">
      <div class="q-meta">
        <span>{{ index + 1 }} / {{ expected || run.questions.length }}</span>
        <span>{{ t('quizPage.diff.' + run.difficulty) }}</span>
        <span v-if="current" class="q-type">{{ tpLabel(current.type) }}</span>
        <span v-if="current && current.source === 'web'" class="badge-web">
          {{ t('quizPage.webSource') }}
        </span>
        <span v-if="current && seenBefore(current.stem)" class="badge-past">曾经的错题</span>
      </div>
      <p v-if="waitingNext" class="muted">{{ t('quizPage.moreComing') }}</p>
      <p v-else-if="current" class="q-stem">{{ current.stem }}</p>

      <!-- 单选 / 判断：单选按钮式 -->
      <template v-if="current && current.type !== 'multi'">
        <button
          v-for="o in current.options"
          :key="o.key"
          type="button"
          class="opt"
          :class="{
            picked: isPicked(o.key) && !judged,
            right: judged && isCorrectKey(o.key),
            wrong: judged && !judged.correct && isPicked(o.key),
          }"
          :disabled="!!judged || busy"
          @click="choose(o.key)"
        >
          <b>{{ o.key }}</b> {{ o.text }}
        </button>
      </template>

      <!-- 多选：复选框式 -->
      <template v-else>
        <button
          v-for="o in current.options"
          :key="o.key"
          type="button"
          class="opt"
          :class="{
            picked: isPicked(o.key) && !judged,
            right: judged && isCorrectKey(o.key),
            wrong: judged && !judged.correct && isPicked(o.key),
          }"
          :disabled="!!judged || busy"
          @click="toggleMulti(o.key)"
        >
          <b>{{ o.key }}</b> {{ o.text }}
          <span v-if="isPicked(o.key)" class="chk">✓</span>
        </button>
      </template>

      <div v-if="current && !judged" class="q-actions">
        <button type="button" class="btn btn-accent" :disabled="busy" @click="submit">
          {{ t('quizPage.submit') }}
        </button>
      </div>

      <div v-else class="verdict" :class="judged.correct ? 'good' : 'bad'">
        <p class="v-line">
          <b>{{ judged.correct ? t('quizPage.right') : t('quizPage.wrong') }}</b>
          <span v-if="!judged.correct"> · {{ t('quizPage.answerIs') }} {{ fmtAnswer(judged.answer, judged.type) }}</span>
        </p>
        <p class="v-exp">{{ judged.explanation }}</p>
        <p class="v-kp">{{ t('quizPage.kp') }}：{{ judged.knowledge_point }}</p>
        <button type="button" class="btn btn-accent" @click="next">
          {{ index + 1 >= (expected || run.questions.length) && streamDone ? t('quizPage.finish') : t('quizPage.next') }}
        </button>
      </div>
    </div>

    <!-- 复盘 -->
    <div v-else class="summary">
      <p v-if="!report" class="muted">{{ t('quizPage.reportGenerating') }}</p>
      <template v-else>
        <div class="report-card">
          <p class="s-score">{{ t('quizPage.reportScore') }}：{{ report.score }} / {{ report.total }}</p>
          <p class="s-sub">
            {{ t('quizPage.reportAccuracy') }}：{{ Math.round(report.accuracy * 100) }}%
            <span v-if="report.duration_s != null"> · {{ t('quizPage.reportDuration') }}：{{ report.duration_s }}s</span>
          </p>
        </div>

        <div class="s-cites" v-if="report.materials && report.materials.length">
          <p class="s-label">{{ t('quizPage.reportMaterials') }}</p>
          <p v-for="(m, i) in report.materials" :key="i">{{ m }}</p>
        </div>

        <div class="replay">
          <p class="s-label">{{ t('quizPage.reportReplay') }}</p>
          <div
            v-for="(it, i) in report.questions"
            :key="it.id"
            class="replay-item"
            :class="it.correct ? 'good' : 'bad'"
          >
            <p class="r-stem">{{ i + 1 }}. {{ it.stem }}
              <span class="badge-web" v-if="it.source === 'web'">{{ t('quizPage.webSource') }}</span>
              <span v-if="seenBefore(it.stem)" class="badge-past">曾经的错题</span>
            </p>
            <p class="r-line">
              <span :class="it.correct ? 'good' : 'bad'">{{ it.correct ? t('quizPage.right') : t('quizPage.wrong') }}</span>
              · {{ t('quizPage.reportUser') }}：{{ fmtAnswer(it.user_answer, it.type) }}
              · {{ t('quizPage.reportAnswer') }}：{{ fmtAnswer(it.correct_answer, it.type) }}
            </p>
            <p class="r-exp">{{ it.explanation }}</p>
            <p class="r-kp">{{ t('quizPage.kp') }}：{{ it.knowledge_point }}</p>
          </div>
        </div>

        <div class="weak" v-if="report.weak_points && report.weak_points.length">
          <p class="s-label">{{ t('quizPage.reportWeak') }}</p>
          <ul>
            <li v-for="w in report.weak_points" :key="w.knowledge_point">
              {{ w.knowledge_point }}（错 {{ w.wrong }} 次）
            </li>
          </ul>
        </div>

        <div class="q-actions">
          <button type="button" class="btn btn-accent" @click="reset">{{ t('quizPage.again') }}</button>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.quiz {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.quiz-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.setup {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.field {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.opts {
  display: flex;
  gap: 8px;
}
.pill {
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-primary);
  border-radius: 1000px;
  padding: 5px 14px;
  font-size: 12.5px;
}
.pill.on {
  border-color: var(--accent);
  color: var(--accent);
}
.err {
  color: var(--danger, #c0392b);
  font-size: 13px;
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
.badge-web {
  background: rgba(33, 118, 209, 0.12);
  color: #2176d1;
  border: 1px solid rgba(33, 118, 209, 0.4);
  border-radius: 6px;
  padding: 1px 8px;
  font-size: 11.5px;
}
.badge-past {
  background: rgba(198, 40, 40, 0.1);
  color: #c62828;
  border: 1px solid rgba(198, 40, 40, 0.35);
  border-radius: 6px;
  padding: 1px 8px;
  font-size: 11.5px;
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
.q-actions {
  display: flex;
  gap: 10px;
  margin-top: 6px;
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
.s-cites {
  border-top: 1px dashed var(--border);
  padding-top: 8px;
  font-size: 12.5px;
  color: var(--text-secondary);
}
.s-label {
  font-size: 12px;
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
.muted {
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
