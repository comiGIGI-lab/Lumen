<script setup>
/**
 * HistoryDialog —— 历史方案（读取后端 data/progress.json）
 * 对应桌面版的「📜 历史」弹窗，点一条即可把方案回填到三栏。
 */
import { ref, watch } from 'vue'
import ModalDialog from './ModalDialog.vue'
import { api } from '@/api/client'

const props = defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'load', 'notify'])

const courses = ref([])
const loading = ref(false)

watch(
  () => props.open,
  async (v) => {
    if (!v) return
    loading.value = true
    try {
      const res = await api.history()
      courses.value = res.courses || []
    } catch (e) {
      emit('notify', { type: 'error', text: `读取历史失败：${e.message}` })
    } finally {
      loading.value = false
    }
  },
)

async function pick(course) {
  try {
    const item = courses.value.find((c) => c.course === course) || {}
    const res = await api.historyDetail(course)
    emit('load', {
      ...res,
      generated_at: item.created_at || item.last_seen_at || '',
    })
  } catch (e) {
    emit('notify', { type: 'error', text: `加载失败：${e.message}` })
  }
}
</script>

<template>
  <ModalDialog :open="open" title="历史学习方案" icon="🕘" width="600px" @close="emit('close')">
    <div v-if="loading" class="empty">读取中…</div>

    <div v-else-if="!courses.length" class="empty">
      <span>🗂</span>
      <p>还没有历史记录。生成一次方案后，这里会按时间倒序列出。</p>
    </div>

    <div v-else class="list">
      <button v-for="c in courses" :key="c.course" class="item" @click="pick(c.course)">
        <div class="item-main">
          <span class="name">{{ c.course }}</span>
          <span class="time">最近：{{ c.last_seen_at || '—' }}</span>
        </div>
        <span class="go">打开预览 →</span>
      </button>
    </div>
  </ModalDialog>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 10px;
  color: var(--text-faint);
  font-size: 12.5px;
  text-align: center;
}

.empty span {
  font-size: 28px;
  opacity: 0.5;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  background: var(--bg-soft);
  border-radius: var(--radius-sm);
  padding: 10px 13px;
  transition: all 0.15s;
}

.item:hover {
  border-color: var(--primary-light);
  background: var(--primary-soft);
}

.name {
  font-family: var(--font-serif);
  font-size: 14.5px;
  font-weight: 400;
  color: var(--text-primary);
}

.time {
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.go {
  font-size: 12px;
  font-weight: 700;
  color: var(--primary);
  white-space: nowrap;
}
</style>
