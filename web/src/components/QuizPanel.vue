<script setup>
/**
 * QuizPanel —— 选择题闯关（复刻 yu-ai-learn 官网可行范围）
 *
 * 链路：选难度/题数/题型 → api.quizGenerate（知识库 RAG 出题，弱命中走 Tavily 兜底）
 * → 逐题作答 api.quizGrade（服务端判分，答案不下发前端）→ 即时对错讲解
 * → 答错写错题本（source: 'quiz'）→ 通关后 api.quizReport 复盘
 * → logExp 结算经验。全程 {{ }} 插值，不用 v-html。
 */
import { computed, ref } from 'vue'
import { useI18n } from '@/i18n'
import { api } from '@/api/client'
import { usePet } from '@/composables/usePet'

const props = defineProps({
  courseContext: { type: String, default: '' },
})
const emit = defineEmits(['notify'])
const { t } = useI18n()
const { logExp } = usePet()

const difficulty = ref('medium')
const count = ref(5)
const qtype = ref('mixed') // single | multi | judge | mixed
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

const current = computed(() => (run.value ? run.value.questions[index.value] : null))
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

async function start() {
  const course = (props.courseContext || '').trim()
  if (!course) {
    errorText.value = t('quizPage.errCourse')
    return
  }
  busy.value = true
  errorText.value = ''
  run.value = null
  results.value = []
  finished.value = false
  report.value = null
  try {
    const res = await api.quizGenerate(course, difficulty.value, count.value, qtype.value)
    if (!res.ok) {
      errorText.value = res.error || t('quizPage.errGenerate')
      emit('notify', { type: 'warn', text: errorText.value })
      return
    }
    run.value = res
    index.value = 0
    picked.value = null
    judged.value = null
    emit('notify', { type: 'success', text: t('quizPage.started') })
  } catch (e) {
    errorText.value = `${t('quizPage.errGenerate')}：${e.message}`
  } finally {
    busy.value = false
  }
}

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
    // 答错入错题本：题干 + 我的答案 + 正解讲解，复用现有 /api/wrongbook
    if (!g.correct) {
      try {
        await api.wrongBookAdd({
          course: props.courseContext || '',
          question: `[${current.value.stem}] 选项：${current.value.options
            .map((o) => `${o.key}. ${o.text}`)
            .join('　')}`,
          my_answer: `${Array.isArray(sel) ? sel.join('') : sel}. ${
            (current.value.options.find((o) => o.key === (Array.isArray(sel) ? sel[0] : sel)) || {}).text || ''
          }`,
          answer: `正确答案 ${fmtAnswer(g.answer, g.type)}。${g.explanation}`,
          reason: `知识点：${g.knowledge_point}`,
          tags: [g.knowledge_point, '闯关'],
          source: 'quiz',
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
    finished.value = true
    // 结算经验：每题 2 点，走既有 logExp 规则
    logExp('答题闯关', results.value.length * 2)
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
  run.value = null
  finished.value = false
  report.value = null
  results.value = []
  errorText.value = ''
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
      <button type="button" class="btn btn-accent" :disabled="busy" @click="start">
        {{ busy ? t('quizPage.generating') : t('quizPage.start') }}
      </button>
      <p v-if="errorText" class="err">{{ errorText }}</p>
    </div>

    <!-- 答题 -->
    <div v-else-if="!finished" class="q">
      <div class="q-meta">
        <span>{{ index + 1 }} / {{ run.questions.length }}</span>
        <span>{{ t('quizPage.diff.' + run.difficulty) }}</span>
        <span class="q-type">{{ tpLabel(run.questions[index].type) }}</span>
        <span v-if="run.questions[index].source === 'web'" class="badge-web">
          {{ t('quizPage.webSource') }}
        </span>
      </div>
      <p class="q-stem">{{ current.stem }}</p>

      <!-- 单选 / 判断：单选按钮式 -->
      <template v-if="current.type !== 'multi'">
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

      <div v-if="!judged" class="q-actions">
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
          {{ index + 1 >= run.questions.length ? t('quizPage.finish') : t('quizPage.next') }}
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
