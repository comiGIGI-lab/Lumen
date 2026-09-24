<script setup>
/**
 * TopNav —— 右上常驻横排：学习方案生成 / 知识库 / 文档导入 / 课程问答 / 自习空间 / 更多
 * 欢迎层与工具页共用。更多：个人空间、AI 模型设置、历史、日志。
 * 不恢复「原型」。
 */
import { onBeforeUnmount, ref } from 'vue'
import { useSpace } from '@/composables/useSpace'

const props = defineProps({
  current: { type: String, default: 'course' },
  needsKey: { type: Boolean, default: false },
})

const emit = defineEmits([
  'go-course',
  'open-knowledge',
  'open-import',
  'open-chat',
  'open-study',
  'open-settings',
  'open-history',
  'open-trace',
])

const openMore = ref(false)
const { panelOpen } = useSpace()

function pick(action) {
  openMore.value = false
  emit(action)
}

function openSpace() {
  openMore.value = false
  panelOpen.value = true
}

function onDoc(e) {
  if (!openMore.value) return
  if (e.target && !e.target.closest?.('.more-wrap')) openMore.value = false
}

if (typeof window !== 'undefined') {
  window.addEventListener('click', onDoc)
}
onBeforeUnmount(() => {
  if (typeof window !== 'undefined') window.removeEventListener('click', onDoc)
})
</script>

<template>
  <nav class="top-nav" aria-label="功能导航">
    <button
      type="button"
      class="nav-link"
      :class="{ on: current === 'course' }"
      @click="emit('go-course')"
    >学习方案生成</button>
    <button
      type="button"
      class="nav-link"
      :class="{ on: current === 'knowledge' }"
      @click="emit('open-knowledge')"
    >知识库</button>
    <button
      type="button"
      class="nav-link"
      :class="{ on: current === 'import' }"
      @click="emit('open-import')"
    >文档导入</button>
    <button
      type="button"
      class="nav-link"
      :class="{ on: current === 'chat' }"
      @click="emit('open-chat')"
    >课程问答</button>
    <button
      type="button"
      class="nav-link"
      :class="{ on: current === 'study' }"
      @click="emit('open-study')"
    >自习空间</button>
    <div class="more-wrap">
      <button
        type="button"
        class="nav-link more-btn"
        :class="{ on: openMore, 'needs-key': needsKey }"
        title="更多"
        aria-haspopup="true"
        :aria-expanded="openMore"
        @click.stop="openMore = !openMore"
      >更多</button>
      <div v-if="openMore" class="more-menu" role="menu">
        <button type="button" role="menuitem" @click="openSpace">个人空间</button>
        <button type="button" role="menuitem" @click="pick('open-settings')">
          AI 模型设置
          <em v-if="needsKey">填入 API Key</em>
        </button>
        <button type="button" role="menuitem" @click="pick('open-history')">历史</button>
        <button type="button" role="menuitem" @click="pick('open-trace')">日志</button>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.top-nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  min-width: 0;
}

.nav-link {
  border: 1px solid #e4ded5;
  background: #fff;
  color: #191919;
  border-radius: 1000px;
  padding: 7px 14px;
  font-size: 12.5px;
  white-space: nowrap;
}

.nav-link.on {
  border-color: #e51520;
  color: #e51520;
}

.nav-link.needs-key {
  border-color: #e51520;
  color: #b45309;
}

.more-wrap {
  position: relative;
}

.more-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 176px;
  background: #fff;
  border: 1px solid #e4ded5;
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 6px;
  z-index: 150;
}

.more-menu button {
  display: flex;
  width: 100%;
  text-align: left;
  border: none;
  background: transparent;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
  color: #191919;
}

.more-menu button:hover {
  background: #f8f3ec;
}

.more-menu em {
  font-style: normal;
  margin-left: 6px;
  color: #e51520;
  font-size: 11px;
}

@media (max-width: 430px) {
  .top-nav {
    width: 100%;
  }
  .nav-link {
    padding: 6px 10px;
    font-size: 12px;
  }
}
</style>
