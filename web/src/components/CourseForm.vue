<script setup>
/**
 * CourseForm —— 【课程名】输入 + 用户画像 + 生成按钮
 * 这是整条链路的起点。
 */
import { computed, ref, watch } from 'vue'

const props = defineProps({
  options: {
    type: Object,
    default: () => ({ levels: [], daily_hours: [], goals: [] }),
  },
  busy: { type: Boolean, default: false },
  suggestedDays: { type: Number, default: 7 },
})

const emit = defineEmits(['generate', 'profile-change'])

const course = defineModel('course', { type: String, default: '' })
const profile = defineModel('profile', {
  type: Object,
  default: () => ({ level: '入门', daily_hours: '2h', goal: '兴趣', deadline: '' }),
})

const showProfile = ref(true)

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
    { value: '', label: '不限（按每日时长推荐）' },
    { value: fmt(7), label: `${fmt(7)}（剩 7 天 · 冲刺）` },
    { value: fmt(14), label: `${fmt(14)}（剩 14 天）` },
    { value: fmt(30), label: `${fmt(30)}（剩 30 天）` },
    { value: fmt(90), label: `${fmt(90)}（剩 90 天 · 长期）` },
  ]
})

/** 常见课程快捷入口，点一下直接填入并生成 */
const presets = ['机器学习', 'Python', '计算机网络', '线性代数', '操作系统', '数据结构']

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
  return `剩 ${days} 天 · 将生成 ${n} 天计划`
})
</script>

<template>
  <section class="card card-pad form-card">
    <!-- 课程名 -->
    <div class="row-main">
      <label class="lead">📖 想学什么课程？</label>
      <div class="input-wrap">
        <input
          v-model="course"
          class="input course-input"
          placeholder="例如：机器学习、计算机网络、线性代数…"
          :disabled="busy"
          @keyup.enter="submit"
        />
      </div>
      <button class="btn btn-primary generate" :disabled="busy" @click="submit">
        <span v-if="busy" class="spinner"></span>
        <span v-else>✨</span>
        {{ busy ? '生成中…' : '生成方案' }}
      </button>
    </div>

    <div class="row-hint">
      <span class="muted">💡 回车键也能直接生成</span>
      <span class="presets">
        试试：
        <button
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
      <span class="lead">🎯 你是哪类学习者？</span>
      <span class="muted">画像会注入 Prompt，影响章节深度、资源推荐与计划天数</span>
      <button class="btn-link toggle" @click="showProfile = !showProfile">
        {{ showProfile ? '收起 ▲' : '展开 ▼' }}
      </button>
    </div>

    <div v-show="showProfile" class="profile-grid">
      <div class="field">
        <label class="field-label">水平</label>
        <select v-model="profile.level" class="select" :disabled="busy">
          <option v-for="v in options.levels" :key="v" :value="v">{{ v }}</option>
        </select>
      </div>

      <div class="field">
        <label class="field-label">每日时长</label>
        <select v-model="profile.daily_hours" class="select" :disabled="busy">
          <option v-for="v in options.daily_hours" :key="v" :value="v">{{ v }}</option>
        </select>
      </div>

      <div class="field">
        <label class="field-label">学习目标</label>
        <select v-model="profile.goal" class="select" :disabled="busy">
          <option v-for="v in options.goals" :key="v" :value="v">{{ v }}</option>
        </select>
      </div>

      <div class="field">
        <label class="field-label">截止日期</label>
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
  font-size: 13.5px;
  font-weight: 700;
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
  border: 2px solid rgba(255, 255, 255, 0.5);
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
  padding: 2px 10px;
  font-size: 11.5px;
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
