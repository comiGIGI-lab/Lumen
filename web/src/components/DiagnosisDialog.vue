<script setup>
/**
 * DiagnosisDialog —— 摸底诊断：先答 5-8 道按章节均衡的摸底题，再看知识点掌握热力图。
 *
 * 数据来源 `/api/diagnosis`（generate / grade / get）：
 *  - 标准答案**只在服务端**（data/diagnosis.json），前端拿到的题目不含 answer；
 *  - 判分也由服务端做（前端不存答案、不算分）；
 *  - 判分结果会注入 Planner —— 下次生成方案时 prompt 里会多一段「诊断结果」，
 *    大纲据此对薄弱章节加厚（见 vendor tools/user_profile.format_profile_text）。
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import { api } from '@/api/client'
import ModalDialog from './ModalDialog.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  course: { type: String, default: '' },
  profile: { type: Object, default: null },
})
const emit = defineEmits(['close', 'notify', 'apply-plan'])

const { t } = useI18n()

const phase = ref('idle') // idle | loading | quiz | grading | result | skipped | error
const questions = ref([])
const picked = ref({})
const result = ref(null)
const errorText = ref('')
const degraded = ref(false)
/** 本次诊断 id（判分要带回去；答案仍在服务端，前端不留标准答案） */
const diagnosisId = ref('')

const total = computed(() => questions.value.length)
const answered = computed(
  () => questions.value.filter((q) => {
    const v = picked.value[q.id]
    return Array.isArray(v) ? v.length > 0 : v !== undefined && v !== null && v !== ''
  }).length,
)
const canSubmit = computed(() => phase.value === 'quiz' && answered.value > 0)

/** 掌握度 → 颜色（≥85 好 / ≥60 待巩固 / <60 薄弱）。数据可视化用固定语义色，不跟主题走。 */
const MASTERY_COLORS = (m) => (m >= 85 ? '#16a34a' : m >= 60 ? '#d97706' : '#dc2626')

function isPicked(q, key) {
  const v = picked.value[q.id]
  return Array.isArray(v) ? v.includes(key) : v === key
}

/** 单选/判断直接覆盖；多选切换数组（后端 _is_correct 认数组）。 */
function choose(q, key) {
  if (phase.value !== 'quiz') return
  if (q.type === 'multi') {
    const cur = Array.isArray(picked.value[q.id]) ? [...picked.value[q.id]] : []
    const i = cur.indexOf(key)
    if (i >= 0) cur.splice(i, 1)
    else cur.push(key)
    picked.value = { ...picked.value, [q.id]: cur }
  } else {
    picked.value = { ...picked.value, [q.id]: key }
  }
}

async function start() {
  const course = String(props.course || '').trim()
  if (!course) {
    errorText.value = t('diagnosis.needCourse')
    phase.value = 'error'
    return
  }
  phase.value = 'loading'
  result.value = null
  try {
    const res = await api.diagnosisGenerate(course, props.profile, 6)
    if (res && res.skipped) {
      errorText.value = res.error || t('diagnosis.skipped')
      phase.value = 'skipped'
      return
    }
    if (!res || !res.ok || !(res.questions || []).length) {
      errorText.value = (res && res.error) || t('diagnosis.error')
      phase.value = 'error'
      return
    }
    questions.value = res.questions
    diagnosisId.value = res.diagnosis_id || ''
    picked.value = {}
    degraded.value = !!res.degraded
    phase.value = 'quiz'
  } catch (e) {
    errorText.value = (e && e.message) || t('diagnosis.error')
    phase.value = 'error'
  }
}

async function submit() {
  if (!canSubmit.value) return
  phase.value = 'grading'
  try {
    const res = await api.diagnosisGrade(diagnosisId.value, picked.value)
    if (!res || !res.ok) {
      errorText.value = (res && res.error) || t('diagnosis.error')
      phase.value = 'error'
      return
    }
    result.value = res
    phase.value = 'result'
    emit('notify', { type: 'success', text: t('diagnosis.doneToast', { score: res.score }) })
  } catch (e) {
    errorText.value = (e && e.message) || t('diagnosis.error')
    phase.value = 'error'
  }
}

function applyPlan() {
  emit('apply-plan', String(props.course || '').trim())
}

watch(
  () => props.open,
  (v) => {
    if (v) start()
    else {
      phase.value = 'idle'
      questions.value = []
      picked.value = {}
      result.value = null
      errorText.value = ''
      diagnosisId.value = ''
      degraded.value = false
    }
  },
)
</script>

<template>
  <ModalDialog
    :open="open"
    :icon="'🩺'"
    :title="t('diagnosis.title')"
    width="680px"
    fullscreen-on-mobile
    @close="emit('close')"
  >
    <!-- 加载中 -->
    <div v-if="phase === 'loading'" class="dg-center">
      <div class="dots"><i></i><i></i><i></i></div>
      <p class="muted">{{ t('diagnosis.loading') }}</p>
    </div>

    <!-- 跳过 / 出错 -->
    <div v-else-if="phase === 'skipped' || phase === 'error'" class="dg-center">
      <div class="big-ico">{{ phase === 'skipped' ? '📭' : '⚠️' }}</div>
      <p class="muted">{{ errorText }}</p>
    </div>

    <!-- 答题 -->
    <div v-else-if="phase === 'quiz' || phase === 'grading'" class="dg-quiz">
      <p class="dg-sub">
        {{ t('diagnosis.sub') }}
        <span v-if="degraded" class="dg-tag">{{ t('diagnosis.degradedTag') }}</span>
      </p>
      <div
        v-for="(q, i) in questions"
        :key="q.id"
        class="dg-q"
      >
        <div class="dg-q-head">
          <span class="dg-no">{{ String(i + 1).padStart(2, '0') }}</span>
          <span class="dg-stem">{{ q.stem }}</span>
        </div>
        <div class="dg-chapter" v-if="q.chapter">{{ q.chapter }}</div>
        <div class="dg-opts">
          <button
            v-for="o in q.options"
            :key="o.key"
            type="button"
            class="dg-opt"
            :class="{ on: isPicked(q, o.key) }"
            @click="choose(q, o.key)"
          >
            <span class="dg-key">{{ o.key }}</span>
            <span class="dg-text">{{ o.text }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 结果：知识点掌握热力图 -->
    <div v-else-if="phase === 'result' && result" class="dg-result">
      <div class="dg-score">
        {{ t('diagnosis.score', { correct: result.correct, total: result.total, score: result.score }) }}
      </div>

      <div class="dg-block-title">{{ t('diagnosis.resultTitle') }}</div>
      <div class="dg-bars">
        <div v-for="row in result.heatmap" :key="row.chapter" class="dg-bar-row">
          <span class="dg-bar-name" :title="row.chapter">{{ row.chapter }}</span>
          <span class="dg-bar-track">
            <span
              class="dg-bar-fill"
              :style="{ width: (row.done ? row.mastery : 0) + '%', background: MASTERY_COLORS(row.mastery) }"
            ></span>
          </span>
          <span class="dg-bar-val">
            {{ row.done ? row.mastery + '%' : t('diagnosis.notAnswered') }}
          </span>
        </div>
      </div>

      <div v-if="result.weak && result.weak.length" class="dg-note dg-note-weak">
        <b>{{ t('diagnosis.weakTitle') }}</b>{{ result.weak.join(' / ') }}
      </div>
      <div class="dg-note dg-note-strong">{{ t('diagnosis.strongTitle') }}</div>
    </div>

    <!-- 空态兜底（例如被父组件直接打开） -->
    <div v-else class="dg-center">
      <div class="big-ico">🩺</div>
      <p class="muted">{{ t('diagnosis.sub') }}</p>
    </div>

    <template #footer>
      <span v-if="phase === 'quiz'" class="dg-count">
        {{ t('diagnosis.progress', { n: answered, total }) }}
      </span>
      <button
        v-if="phase === 'quiz' || phase === 'result' || phase === 'error' || phase === 'skipped'"
        class="btn btn-ghost"
        type="button"
        @click="start"
      >
        {{ t('diagnosis.regen') }}
      </button>
      <button
        v-if="phase === 'quiz'"
        class="btn btn-primary"
        type="button"
        :disabled="!canSubmit"
        @click="submit"
      >
        {{ t('diagnosis.submit') }}
      </button>
      <button v-if="phase === 'grading'" class="btn btn-primary" type="button" disabled>
        {{ t('diagnosis.grading') }}
      </button>
      <button
        v-if="phase === 'result'"
        class="btn btn-primary"
        type="button"
        @click="applyPlan"
      >
        {{ t('diagnosis.applyPlan') }}
      </button>
      <button class="btn btn-ghost" type="button" @click="emit('close')">
        {{ t('diagnosis.close') }}
      </button>
    </template>
  </ModalDialog>
</template>

<style scoped>
.dg-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 40px 16px;
  text-align: center;
}
.big-ico {
  font-size: 30px;
}
.muted {
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.7;
  margin: 0;
}
.dots {
  display: flex;
  gap: 5px;
}
.dots i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--primary-light);
  animation: pulse-soft 1.1s ease-in-out infinite;
}
.dots i:nth-child(2) { animation-delay: 0.18s; }
.dots i:nth-child(3) { animation-delay: 0.36s; }

.dg-sub {
  margin: 0 0 12px;
  font-size: 12.5px;
  color: var(--text-muted);
}
.dg-tag {
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  color: #92400e;
  background: #fef3c7;
}

.dg-q {
  padding: 12px 13px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary-light);
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
  margin-bottom: 10px;
}
.dg-q-head {
  display: flex;
  gap: 9px;
  align-items: baseline;
}
.dg-no {
  flex: none;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--primary);
}
.dg-stem {
  font-size: 13.5px;
  color: var(--text-primary);
  line-height: 1.6;
}
.dg-chapter {
  margin: 5px 0 0 26px;
  font-size: 11px;
  color: var(--text-faint);
}
.dg-opts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 9px 0 0 26px;
}
.dg-opt {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 11px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 12.5px;
  line-height: 1.4;
  text-align: left;
  transition: all 0.14s;
}
.dg-opt:hover {
  border-color: var(--border-strong);
  color: var(--text-primary);
}
.dg-opt.on {
  border-color: var(--primary);
  background: var(--primary-soft);
  color: var(--primary-dark);
}
.dg-key {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--primary);
}

.dg-score {
  font-family: var(--font-serif);
  font-size: 20px;
  color: var(--text-primary);
  margin-bottom: 14px;
}
.dg-block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.dg-bars {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.dg-bar-row {
  display: grid;
  grid-template-columns: minmax(90px, 34%) 1fr 62px;
  align-items: center;
  gap: 9px;
}
.dg-bar-name {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dg-bar-track {
  height: 10px;
  border-radius: 999px;
  background: var(--bg-soft);
  border: 1px solid var(--border);
  overflow: hidden;
}
.dg-bar-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width 0.4s ease;
}
.dg-bar-val {
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
  text-align: right;
}
.dg-note {
  margin-top: 14px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  line-height: 1.7;
}
.dg-note-weak {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
}
.dg-note-strong {
  background: var(--bg-soft);
  border: 1px solid var(--border);
  color: var(--text-muted);
}
.dg-count {
  margin-right: auto;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
