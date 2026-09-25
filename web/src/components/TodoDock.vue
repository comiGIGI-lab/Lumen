<script setup>
/**
 * TodoDock —— 待办事项，存 localStorage zjxt.todos，无账号。
 * 可指定某一条置顶（同时只一条）。
 */
import { computed, ref } from 'vue'
import { useSpace } from '@/composables/useSpace'

const { todos } = useSpace()
const draft = ref('')

const sorted = computed(() => {
  const list = todos.value.slice()
  list.sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned))
  return list
})

function addTodo() {
  const text = draft.value.trim()
  if (!text) return
  todos.value = [
    { id: Date.now(), text, done: false, pinned: false },
    ...todos.value,
  ]
  draft.value = ''
}

function toggle(item) {
  item.done = !item.done
}

function pin(id) {
  todos.value = todos.value.map((t) => ({
    ...t,
    pinned: t.id === id ? !t.pinned : false,
  }))
}

function remove(id) {
  todos.value = todos.value.filter((t) => t.id !== id)
}
</script>

<template>
  <div class="todo">
    <form class="add" @submit.prevent="addTodo">
      <input v-model="draft" type="text" maxlength="80" placeholder="写下一项" />
      <button type="submit">添加</button>
    </form>
    <ul v-if="sorted.length" class="list">
      <li v-for="item in sorted" :key="item.id" :class="{ done: item.done, pinned: item.pinned }">
        <label>
          <input type="checkbox" :checked="item.done" @change="toggle(item)" />
          <span>{{ item.text }}</span>
        </label>
        <button
          type="button"
          class="pin"
          :class="{ on: item.pinned }"
          :aria-label="item.pinned ? '取消置顶' : '置顶'"
          :title="item.pinned ? '取消置顶' : '置顶'"
          @click="pin(item.id)"
        >置顶</button>
        <button type="button" class="del" aria-label="删除" @click="remove(item.id)">×</button>
      </li>
    </ul>
    <p v-else class="empty">还没有待办</p>
  </div>
</template>

<style scoped>
.add {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.add input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 1000px;
  padding: 6px 12px;
  background: var(--bg-card);
  font-size: 13px;
}

.add button {
  border: 1px solid var(--primary);
  background: var(--primary);
  color: #fff;
  border-radius: 1000px;
  padding: 6px 12px;
  font-size: 12px;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.list li {
  display: flex;
  align-items: center;
  gap: 6px;
}

.list li.pinned {
  background: rgba(229, 21, 32, 0.06);
  border-radius: 8px;
  padding: 2px 4px;
}

.list label {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--text-primary);
}

.list span {
  word-break: break-word;
}

.done span {
  color: var(--text-muted);
  text-decoration: line-through;
}

.pin {
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-muted);
  border-radius: 1000px;
  padding: 2px 8px;
  font-size: 11px;
  flex: none;
}

.pin.on {
  border-color: var(--accent);
  color: var(--accent);
}

.del {
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 16px;
  width: 24px;
  flex: none;
}

.empty {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
