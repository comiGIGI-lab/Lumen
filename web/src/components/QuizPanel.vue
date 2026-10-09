<script setup>
/**
 * QuizPanel —— 选择题闯关（复刻 yu-ai-learn 官网可行范围）
 *
 * 链路：选难度/题数 → api.quizGenerate（知识库 RAG 出题，弱命中拒绝）
 * → 逐题作答 api.quizGrade（服务端判分，答案不下发前端）→ 即时对错讲解
 * → 答错写错题本（source: 'quiz'）→ 通关 logExp 结算经验。
 * 全程 {{ }} 插值，不用 v-html。
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
const busy = ref(false)
const errorText = ref('')

/** 一局的完整状态。questions 是 generate 响应（无 answer） */
const run = ref(null) // { quiz_id, questions, retrieved }
const index = ref(0)
const picked = ref('')
const judged = ref(null) // grade 响应：{ correct, answer, explanation, knowledge_point }
const results = ref([]) // [{id, correct, knowledge_point}]
const finished = ref(false)

const current = computed(() => (run.value ? run.value.questions[index.value] : null))
const score = computed(() => results.value.filter((r) => r.correct).length)

const DIFFS = [
  { key: 'easy' },
  { key: 'medium' },
  { key: 'hard' },
]

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
  try {
    const res = await api.quizGenerate(course, difficulty.value, count.value)
    if (!res.ok) {
      errorText.value = res.error || t('quizPage.errGenerate')
      emit('notify', { type: 'warn', text: errorText.value })
      return
    }
    run.value = res
    index.value = 0
    picked.value = ''
    judged.value = null
    emit('notify', { type: 'success', text: t('quizPage.started') })
  } catch (e) {
    errorText.value = `${t('quizPage.errGenerate')}：${e.message}`
  } finally {
    busy.value = false
  }
}

async function submit() {
  if (!current.value || !picked.value || busy.value) return
  busy.value = true
  try {
    const g = await api.quizGrade(run.value.quiz_id, current.value.id, picked.value)
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
          my_answer: `${picked.value}. ${
            (current.value.options.find((o) => o.key === picked.value) || {}).text || ''
          }`,
          answer: `正确答案 ${g.answer}。${g.explanation}`,
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

function next() {
  judged.value = null
  picked.value = ''
  if (index.value + 1 >= run.value.questions.length) {
    finished.value = true
    // 结算经验：每题 2 点（答对才有意义感，答错也学了讲解），走既有 logExp 规则
    logExp('答题闯关', results.value.length * 2)
    emit('notify', { type: 'success', text: t('quizPage.done') })
    return
  }
  index.value += 1
}

function reset() {
  run.value = null
  finished.value = false
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
      </div>
      <p class="q-stem">{{ current.stem }}</p>
      <button
        v-for="o in current.options"
        :key="o.key"
        type="button"
        class="opt"
        :class="{
          picked: picked === o.key && !judged,
          right: judged && judged.answer && judged.answer.includes(o.key),
          wrong: judged && !judged.correct && picked === o.key,
        }"
        :disabled="!!judged || busy"
        @click="picked = o.key"
      >
        <b>{{ o.key }}</b> {{ o.text }}
      </button>

      <div v-if="!judged" class="q-actions">
        <button type="button" class="btn btn-accent" :disabled="!picked || busy" @click="submit">
          {{ t('quizPage.submit') }}
        </button>
      </div>

      <div v-else class="verdict" :class="judged.correct ? 'good' : 'bad'">
        <p class="v-line">
          <b>{{ judged.correct ? t('quizPage.right') : t('quizPage.wrong') }}</b>
          <span v-if="!judged.correct"> · {{ t('quizPage.answerIs') }} {{ judged.answer.join('') }}</span>
        </p>
        <p class="v-exp">{{ judged.explanation }}</p>
        <p class="v-kp">{{ t('quizPage.kp') }}：{{ judged.knowledge_point }}</p>
        <button type="button" class="btn btn-accent" @click="next">
          {{ index + 1 >= run.questions.length ? t('quizPage.finish') : t('quizPage.next') }}
        </button>
      </div>
    </div>

    <!-- 结算 -->
    <div v-else class="summary">
      <p class="s-score">{{ t('quizPage.score') }}：{{ score }} / {{ run.questions.length }}</p>
      <ul class="s-list">
        <li v-for="(r, i) in results" :key="r.id" :class="r.correct ? 'good' : 'bad'">
          {{ i + 1 }}. {{ r.knowledge_point }} — {{ r.correct ? t('quizPage.right') : t('quizPage.wrong') }}
        </li>
      </ul>
      <div v-if="run.retrieved && run.retrieved.length" class="s-cites">
        <p class="s-label">{{ t('quizPage.cites') }}</p>
        <p v-for="c in run.retrieved" :key="c.id">{{ c.title }}（{{ c.score }}）</p>
      </div>
      <div class="q-actions">
        <button type="button" class="btn btn-accent" @click="reset">{{ t('quizPage.again') }}</button>
      </div>
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
  font-size: 12px;
  color: var(--text-secondary);
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
.s-score {
  font-size: 16px;
  font-weight: 500;
}
.s-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.s-list .good {
  color: #2e7d32;
}
.s-list .bad {
  color: #c62828;
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
</style>
