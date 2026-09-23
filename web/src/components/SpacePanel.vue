<script setup>
/**
 * SpacePanel —— 个人空间设置：开关三个悬浮窗，大小已随窗口操作写入 localStorage。
 */
import { useSpace } from '@/composables/useSpace'

const { WIN_IDS, WIN_META, windows, panelOpen, setOn, resetLayout } = useSpace()

function close() {
  panelOpen.value = false
}
</script>

<template>
  <Teleport to="body">
  <div class="mask" @click.self="close">
    <div class="card" role="dialog" aria-label="个人空间">
      <header>
        <h3>个人空间</h3>
        <button type="button" class="x" aria-label="关闭" @click="close">×</button>
      </header>
      <p class="lead">开关三个组件。大小、折叠和位置会记在这台浏览器里，没有账号。</p>
      <ul>
        <li v-for="id in WIN_IDS" :key="id">
          <label>
            <input type="checkbox" :checked="windows[id].on" @change="setOn(id, $event.target.checked)" />
            <span>{{ WIN_META[id].title }}</span>
          </label>
          <em>{{ windows[id].collapsed ? '已收起' : '大小 ' + windows[id].size }}</em>
        </li>
      </ul>
      <div class="foot">
        <button type="button" class="ghost" @click="resetLayout">恢复默认位置</button>
        <button type="button" class="ok" @click="close">完成</button>
      </div>
    </div>
  </div>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 160;
  background: rgba(25, 25, 25, 0.28);
  display: grid;
  place-items: center;
  padding: 16px;
}

.card {
  width: min(380px, 100%);
  background: #fbf9f6;
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 16px 18px 14px;
  box-shadow: var(--shadow);
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

h3 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 400;
}

.x {
  border: none;
  background: transparent;
  font-size: 20px;
  color: var(--text-muted);
}

.lead {
  margin: 8px 0 14px;
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.6;
}

ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-top: 1px solid var(--border);
}

label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

em {
  font-style: normal;
  font-size: 12px;
  color: var(--text-muted);
}

.foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 12px;
}

.ghost,
.ok {
  border-radius: 1000px;
  padding: 7px 14px;
  font-size: 13px;
}

.ghost {
  border: 1px solid var(--border);
  background: #fff;
}

.ok {
  border: 1px solid var(--primary);
  background: var(--primary);
  color: #fff;
}
</style>
