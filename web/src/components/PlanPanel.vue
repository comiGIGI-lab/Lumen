<script setup>
/**
 * PlanPanel —— 课程方案面板顶部的「最近学过」chips。
 * 数据来自 usePlanHistory（zjxt.course_history，最多 50 条）。
 * 点击某条：把当时的课程名 + 画像交回父级，父级按相同画像重新跑一次（走缓存）。
 *
 * 本仓库主表单仍由 CourseForm 承载；本组件挂在 CourseForm 顶部，对应看板里的 PlanPanel。
 */
import { computed } from 'vue'
import { useI18n } from '@/i18n'
import { usePlanHistory } from '@/composables/usePlanHistory'

defineProps({
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['replay'])
const { t } = useI18n()

const { history } = usePlanHistory()
const recent = computed(() => [...history.value].sort((a, b) => (b.ts || 0) - (a.ts || 0)).slice(0, 12))

const nameCounts = computed(() => {
  const map = {}
  for (const r of recent.value) {
    map[r.name] = (map[r.name] || 0) + 1
  }
  return map
})

function hint(profile) {
  if (!profile) return ''
  const parts = []
  if (profile.level) parts.push(profile.level)
  const min = Number(profile.daily_minutes)
  if (Number.isFinite(min) && min > 0) parts.push(`${min} 分`)
  const goal = profile.goal === '其他' ? (profile.goal_other || '其他') : profile.goal
  if (goal) parts.push(goal)
  return parts.join(' · ')
}

function chipText(r) {
  if ((nameCounts.value[r.name] || 0) > 1) {
    const extra = hint(r.profile)
    return extra ? `${r.name} · ${extra}` : r.name
  }
  return r.name
}

function onReplay(entry) {
  emit('replay', {
    name: entry.name,
    profile: { ...(entry.profile || {}) },
    ts: entry.ts,
  })
}
</script>

<template>
  <div v-if="recent.length" class="recent-strip" :aria-label="t('planPanel.2')">
    <span class="recent-label">{{ t('planPanel.1') }}</span>
    <button
      v-for="r in recent"
      :key="r.name + '::' + r.ts"
      type="button"
      class="recent-chip"
      :disabled="busy"
      :title="hint(r.profile) || r.name"
      @click="onReplay(r)"
    >{{ chipText(r) }}</button>
  </div>
</template>

<style scoped>
.recent-strip {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  background: var(--bg-soft);
  border-radius: var(--radius-sm);
}
.recent-label {
  font-size: 11.5px;
  color: var(--text-muted);
  letter-spacing: 0.04em;
  flex: none;
}
.recent-chip {
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text-secondary);
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 11.5px;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-chip:hover:not(:disabled) {
  border-color: var(--primary-light);
  background: var(--primary-soft);
  color: var(--primary-dark);
}
.recent-chip:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
</style>
