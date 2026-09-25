<script setup>
/**
 * CountdownTimer —— 距离某天还有多少天
 * 事件列表，存 localStorage zjxt.countdowns，不接后端。
 * compact：标题栏只显示最近一条未来事件。没有未来事件不渲染。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useSpace } from '@/composables/useSpace'

const props = defineProps({
  compact: { type: Boolean, default: false },
})

const { countdowns, parseYmd } = useSpace()
const titleDraft = ref('')
const dateDraft = ref('')
const nowTick = ref(Date.now())
let tick = 0

onMounted(() => {
  tick = setInterval(() => {
    nowTick.value = Date.now()
  }, 60 * 1000)
})

onBeforeUnmount(() => {
  if (tick) clearInterval(tick)
})

function startOfDay(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

function daysUntil(ymd) {
  const date = parseYmd(ymd)
  if (!date) return null
  const [y, mo, d] = date.split('-').map(Number)
  const target = new Date(y, mo - 1, d)
  const today = new Date(nowTick.value)
  return Math.round((startOfDay(target) - startOfDay(today)) / 86400000)
}

function remainText(n) {
  if (n == null) return ''
  if (n > 0) return `还有 ${n} 天`
  if (n === 0) return '就是今天'
  return `已过 ${-n} 天`
}

function itemPhrase(item) {
  if (!item || item.days == null) return ''
  return `距离 ${item.title} ${remainText(item.days)}`
}

function compactPhrase(item) {
  if (!item || item.days == null) return ''
  if (item.days > 0) return `距离 ${item.title} 还剩 ${item.days} 天`
  return ''
}

const sorted = computed(() => {
  return countdowns.value
    .map((item) => ({ ...item, days: daysUntil(item.date) }))
    .filter((item) => item.days != null)
    .sort((a, b) => {
      const aUp = a.days >= 0
      const bUp = b.days >= 0
      if (aUp !== bUp) return aUp ? -1 : 1
      return aUp ? a.days - b.days : a.days - b.days
    })
})

const nearestFuture = computed(() => sorted.value.find((item) => item.days > 0) || null)
const compactLabel = computed(() => compactPhrase(nearestFuture.value))

function addItem() {
  const title = titleDraft.value.trim().slice(0, 20)
  const date = parseYmd(dateDraft.value)
  if (!title || !date) return
  countdowns.value = [
    { id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, title, date },
    ...countdowns.value,
  ]
  titleDraft.value = ''
  dateDraft.value = ''
}

function removeItem(id) {
  countdowns.value = countdowns.value.filter((item) => item.id !== id)
}
</script>

<template>
  <span
    v-if="compact && nearestFuture"
    class="cd-mini"
    :title="compactLabel"
  >{{ compactLabel }}</span>
  <div v-else-if="!compact" class="cd">
    <h3>倒数日</h3>
    <form class="add" @submit.prevent="addItem">
      <input v-model="titleDraft" type="text" maxlength="20" placeholder="事件，如期末考试" />
      <input v-model="dateDraft" type="date" aria-label="目标日期" />
      <button type="submit">添加</button>
    </form>
    <ul v-if="sorted.length" class="list">
      <li
        v-for="item in sorted"
        :key="item.id"
        :class="{ due: item.days === 0, past: item.days < 0 }"
      >
        <div>
          <b>{{ item.title }}</b>
          <span>{{ itemPhrase(item) }}</span>
        </div>
        <button type="button" class="del" aria-label="删除" @click="removeItem(item.id)">×</button>
      </li>
    </ul>
    <p v-else class="empty">写下事件和目标日，这里会显示距离某件事还有几天。</p>
  </div>
</template>

<style scoped>
.cd {
  margin: 0 0 12px;
  padding: 0 0 10px;
  border-bottom: 1px solid var(--border);
}

.cd-mini {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

h3 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 400;
  color: var(--text-secondary);
}

.add {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 7.6em auto;
  gap: 6px;
  margin-bottom: 8px;
}

.add input,
.add button {
  border: 1px solid var(--border);
  border-radius: 1000px;
  padding: 5px 10px;
  font-size: 12px;
  background: var(--bg-card);
  min-width: 0;
  color: var(--text-primary);
}

.add button {
  border-color: var(--primary);
  background: var(--primary);
  color: #fff;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.list li {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.list b {
  display: block;
  font-weight: 400;
  font-size: 13px;
  color: var(--text-primary);
}

.list span,
.empty {
  font-size: 12px;
  color: var(--text-muted);
}

.list li.due b {
  color: var(--accent);
}

.list li.past b,
.list li.past span {
  color: var(--text-muted);
}

.del {
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 16px;
  line-height: 1;
  padding: 0 2px;
}

.empty {
  margin: 0;
}
</style>
