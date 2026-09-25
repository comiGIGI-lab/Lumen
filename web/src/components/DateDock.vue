<script setup>
/**
 * DateDock —— 月历 + 当日备忘，存 localStorage zjxt.dates。
 */
import { computed, ref } from 'vue'
import { useSpace } from '@/composables/useSpace'
import CountdownTimer from './CountdownTimer.vue'

const { dateNotes } = useSpace()

const now = new Date()
const year = ref(now.getFullYear())
const month = ref(now.getMonth())
const selected = ref(fmt(now))

const WEEK = ['日', '一', '二', '三', '四', '五', '六']

function fmt(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const monthLabel = computed(() => `${year.value}年${month.value + 1}月`)

const cells = computed(() => {
  const first = new Date(year.value, month.value, 1)
  const start = first.getDay()
  const days = new Date(year.value, month.value + 1, 0).getDate()
  const list = []
  for (let i = 0; i < start; i++) list.push(null)
  for (let d = 1; d <= days; d++) {
    const key = `${year.value}-${String(month.value + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    list.push({ d, key })
  }
  return list
})

const todayKey = fmt(now)

function prevMonth() {
  if (month.value === 0) {
    month.value = 11
    year.value -= 1
  } else month.value -= 1
}

function nextMonth() {
  if (month.value === 11) {
    month.value = 0
    year.value += 1
  } else month.value += 1
}

function onNote(e) {
  const v = e.target.value
  if (!v.trim()) delete dateNotes[selected.value]
  else dateNotes[selected.value] = v
}
</script>

<template>
  <div class="cal">
    <CountdownTimer />
    <div class="nav">
      <button type="button" class="nav-btn" @click="prevMonth">‹</button>
      <span>{{ monthLabel }}</span>
      <button type="button" class="nav-btn" @click="nextMonth">›</button>
    </div>
    <div class="week">
      <span v-for="w in WEEK" :key="w">{{ w }}</span>
    </div>
    <div class="grid">
      <button
        v-for="(c, i) in cells"
        :key="i"
        type="button"
        class="day"
        :class="{
          empty: !c,
          on: c && c.key === selected,
          today: c && c.key === todayKey,
          marked: c && dateNotes[c.key],
        }"
        :disabled="!c"
        @click="c && (selected = c.key)"
      >
        {{ c ? c.d : '' }}
      </button>
    </div>
    <p class="picked">{{ selected }}</p>
    <textarea
      :value="dateNotes[selected] || ''"
      rows="3"
      maxlength="400"
      placeholder="这一天的备忘"
      @input="onNote"
    />
  </div>
</template>

<style scoped>
.nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-family: var(--font-serif);
  font-size: 14px;
}

.nav-btn {
  width: 24px;
  height: 24px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  border-radius: 6px;
}

.week,
.grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.week span {
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
  padding: 2px 0;
}

.day {
  height: 26px;
  border: none;
  background: transparent;
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-primary);
}

.day.empty {
  visibility: hidden;
}

.day.today {
  box-shadow: inset 0 0 0 1px var(--accent);
}

.day.on {
  background: var(--primary);
  color: #fff;
}

.day.marked:not(.on)::after {
  content: '';
  display: block;
  width: 3px;
  height: 3px;
  margin: 0 auto;
  border-radius: 50%;
  background: var(--accent);
}

.picked {
  margin: 8px 0 4px;
  font-size: 11px;
  color: var(--text-muted);
}

textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 8px;
  resize: vertical;
  min-height: 64px;
  font-size: 12.5px;
  background: var(--bg-card);
  color: var(--text-primary);
}
</style>
