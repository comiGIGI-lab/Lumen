<script setup>
/**
 * CourseForm —— 【课程名】输入 + 用户画像 + 生成按钮
 * 这是整条链路的起点。
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import PlanPanel from './PlanPanel.vue'
import { minutesFromProfile } from '@/composables/usePlanHistory'

const props = defineProps({
  options: {
    type: Object,
    default: () => ({ levels: [], daily_hours: [], goals: [] }),
  },
  busy: { type: Boolean, default: false },
  suggestedDays: { type: Number, default: 7 },
})
const { t } = useI18n()

const emit = defineEmits(['generate', 'profile-change', 'replay'])

const course = defineModel('course', { type: String, default: '' })
const profile = defineModel('profile', {
  type: Object,
  default: () => ({ level: '入门', daily_minutes: 60, daily_hours: '1h', goal: '兴趣', goal_other: '', deadline: '' }),
})

const showProfile = ref(true)
const LEVEL_OPTIONS = ['入门', '进阶', '熟练']
const DAILY_CHIPS = [15, 30, 45, 60, 90, 120]
const isCustomTime = ref(!DAILY_CHIPS.includes(Number(profile.value?.daily_minutes)))
const GOAL_OPTIONS = ['考试', '项目', '兴趣', '考研', '考证', '其他']
const showGoalOther = computed(() => profile.value?.goal === '其他')

function selectDailyPreset(m) {
  isCustomTime.value = false
  profile.value.daily_minutes = m
  syncDailyHours(m)
}
function enableCustomTime() {
  isCustomTime.value = true
  const current = Number(profile.value?.daily_minutes)
  if (!current || DAILY_CHIPS.includes(current)) profile.value.daily_minutes = 75
  syncDailyHours(profile.value.daily_minutes)
}
function onCustomMinutesChange(e) {
  let v = parseInt(e.target.value, 10)
  if (isNaN(v)) return
  if (v < 5) v = 5
  if (v > 240) v = 240
  profile.value.daily_minutes = v
  syncDailyHours(v)
}
function syncDailyHours(m) {
  const min = Number(m) || 60
  profile.value.daily_hours = min >= 60 ? `${Math.round((min / 60) * 10) / 10}h` : `${min}min`
}
function onReplay(entry) {
  const name = String(entry?.name || '').trim()
  if (!name) return
  const src = entry.profile || {}
  const minutes = minutesFromProfile(src)
  course.value = name
  profile.value.level = src.level || profile.value.level
  profile.value.daily_minutes = minutes
  profile.value.daily_hours = src.daily_hours || profile.value.daily_hours
  profile.value.goal = src.goal || profile.value.goal
  profile.value.goal_other = src.goal_other || ''
  profile.value.deadline = src.deadline || ''
  isCustomTime.value = !DAILY_CHIPS.includes(Number(minutes))
  emit('replay', { name, profile: { ...profile.value } })
}

/** 截止日候选：与桌面版一致，按今天动态生成 */
const deadlineOptions = computed(() => {
  const fmt = (d) => {
    const dt = new Date()
    dt.setDate(dt.getDate() + d)
    return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(
      dt.getDate(),
    ).padStart(2, '0')}`
  }
  return [
    { value: '', label: t('days.auto') || '不填（按总课时数均摊）' },
    { value: fmt(7), label: t('days.7', { d: fmt(7) }) },
    { value: fmt(14), label: t('days.14', { d: fmt(14) }) },
    { value: fmt(30), label: t('days.30', { d: fmt(30) }) },
    { value: fmt(90), label: t('days.90', { d: fmt(90) }) },
  ]
})

/** 常见课程快捷入口，点一下直接填入并生成 */
const presetKeys = ['preset.ml', 'preset.python', 'preset.network', 'preset.linalg', 'preset.os', 'preset.ds']
const presets = presetKeys.map((k) => t(k))

watch(
  profile,
  () => {
    emit('profile-change', { ...profile.value })
  },
  { deep: true },
)

function submit() {
  const name = (course.value || '').trim()
  if (!name) {
    emit('generate', '')
    return
  }
  emit('generate', name)
}

function pick(name) {
  course.value = name
  emit('generate', name)
}

/** 截止日 → 计划天数 的即时反馈（与后端 tools.user_profile.suggest_plan_length 同规则） */
const deadlineHint = computed(() => {
  const dl = profile.value?.deadline
  if (!dl) return ''
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(`${dl}T00:00:00`)
  if (Number.isNaN(target.getTime())) return '日期格式应为 YYYY-MM-DD'
  const days = Math.round((target - today) / 86400000)
  if (days <= 0) return `已到期 · 生成 5 天冲刺计划`
  const n = Math.min(30, Math.max(5, days))
  return t('days.plan', { days, n })
})
</script>

<template>
  <section class="card card-pad form-card">
    <PlanPanel :busy="busy" @replay="onReplay" />
    <!-- 课程名 -->
    <div class="row-main">
      <label class="lead">{{ t('courseForm.2') }}</label>
      <div class="input-wrap">
        <input
          v-model="course"
          class="input course-input"
          :placeholder="t('courseForm.1')"
          :disabled="busy"
          @keyup.enter="submit"
        />
      </div>
      <button class="btn btn-primary generate" :disabled="busy" @click="submit">
        <span v-if="busy" class="spinner"></span>
        <span v-else>✨</span>
        {{ busy ? t('courseFormX.1') : t('courseFormX.2') }}
      </button>
    </div>

    <div class="row-hint">
      <span class="muted">{{ t('courseForm.3') }}</span>
      <span class="presets">{{ t('courseForm.4') }}<button
          v-for="p in presets"
          :key="p"
          class="preset"
          :disabled="busy"
          @click="pick(p)"
        >
          {{ p }}
        </button>
      </span>
    </div>

    <!-- 用户画像 -->
    <div class="profile-head">
      <span class="lead">{{ t('courseForm.5') }}</span>
      <span class="muted">{{ t('courseForm.6') }}</span>
      <button class="btn-link toggle" @click="showProfile = !showProfile">
        {{ showProfile ? t('courseFormX.3') : t('courseFormX.4') }}
      </button>
    </div>

    <div v-show="showProfile" class="profile-grid">
      <div class="field">
        <label class="field-label">{{ t('courseForm.7') }}</label>
        <div class="chip-row">
          <button
            v-for="v in LEVEL_OPTIONS"
            :key="v"
            type="button"
            class="chip-btn"
            :class="{ on: profile.level === v }"
            :disabled="busy"
            @click="profile.level = v"
          >{{ v }}</button>
        </div>
      </div>

      <div class="field">
        <label class="field-label">{{ t('courseForm.8') }}</label>
        <div class="chip-row">
          <button
            v-for="m in DAILY_CHIPS"
            :key="m"
            type="button"
            class="chip-btn chip-time"
            :class="{ on: Number(profile.daily_minutes) === m }"
            :disabled="busy"
            @click="selectDailyPreset(m)"
          >{{ m < 60 ? m + ' 分' : (m / 60) + ' 小时' }}</button>
          <button
            type="button"
            class="chip-btn chip-time"
            :class="{ on: isCustomTime }"
            :disabled="busy"
            @click="enableCustomTime"
          >自定义</button>
        </div>
        <input
          v-if="isCustomTime"
          :value="profile.daily_minutes"
          class="input custom-min"
          type="number"
          min="5"
          max="240"
          step="5"
          :disabled="busy"
          @input="onCustomMinutesChange"
        />
      </div>

      <div class="field">
        <label class="field-label">{{ t('courseForm.9') }}</label>
        <select v-model="profile.goal" class="select" :disabled="busy">
          <option v-for="v in GOAL_OPTIONS" :key="v" :value="v">{{ v }}</option>
        </select>
        <input
          v-if="showGoalOther"
          v-model="profile.goal_other"
          class="input goal-other"
          maxlength="20"
          placeholder="填具体目标"
          :disabled="busy"
        />
      </div>

      <div class="field">
        <label class="field-label">{{ t('courseForm.10') }}</label>
        <select v-model="profile.deadline" class="select" :disabled="busy">
          <option v-for="o in deadlineOptions" :key="o.value" :value="o.value">
            {{ o.label }}
          </option>
        </select>
      </div>
    </div>

    <div v-if="deadlineHint" class="deadline-hint">
      📅 {{ deadlineHint }}
    </div>
  </section>
</template>

<style scoped>
.form-card {
  padding: 16px 18px;
}

.lead {
  font-family: var(--font-serif);
  font-size: 15px;
  font-weight: 400;
  color: var(--text-primary);
  white-space: nowrap;
}

.muted {
  font-size: 12px;
  color: var(--text-muted);
}

.row-main {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
}

.input-wrap {
  min-width: 0;
}

.course-input {
  padding: 11px 14px;
  font-size: 14px;
}

.generate {
  padding: 11px 22px;
  font-size: 13.5px;
}

.spinner {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 2px solid rgba(var(--bg-card-rgb), 0.5);
  border-top-color: #fff;
  animation: spin 0.7s linear infinite;
}

.row-hint {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 8px;
  padding-left: 168px;
}

.presets {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
  flex-wrap: wrap;
}

.preset {
  border: 1px solid var(--border);
  background: var(--bg-soft);
  color: var(--text-secondary);
  border-radius: 999px;
  min-height: 44px;
  padding: 10px 12px;
  font-size: 12px;
  transition: all 0.15s;
}

.preset:hover:not(:disabled) {
  border-color: var(--primary-light);
  background: var(--primary-soft);
  color: var(--primary-dark);
}

.profile-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding-top: 13px;
  border-top: 1px dashed var(--border);
}

.toggle {
  margin-left: auto;
}

.profile-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-top: 10px;
}

.field {
  min-width: 0;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip-btn {
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  border-radius: 999px;
  min-height: 44px;
  padding: 10px 14px;
  font-size: 13px;
}
.chip-btn.on {
  border-color: var(--primary);
  background: var(--primary-soft);
  color: var(--primary-dark);
}
.chip-time {
  font-variant-numeric: tabular-nums;
}
.custom-min {
  margin-top: 6px;
  width: 110px;
}
.goal-other {
  margin-top: 6px;
}

.deadline-hint {
  margin-top: 10px;
  font-size: 12px;
  color: #b45309;
  background: var(--warning-soft);
  border: 1px solid #fde68a;
  border-radius: var(--radius-sm);
  padding: 7px 12px;
  display: inline-block;
}

@media (max-width: 900px) {
  .row-main {
    grid-template-columns: 1fr;
  }
  .row-hint {
    padding-left: 0;
  }
  .profile-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
