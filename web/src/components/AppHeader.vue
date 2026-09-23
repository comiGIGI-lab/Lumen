<script setup>
/**
 * AppHeader —— 工具界面顶栏
 * 左：只留 LUMEN + 智识有方；模式 / 导出 / 历史 / 日志 / 个人空间收入「更多」。
 */
import { onBeforeUnmount, ref } from 'vue'
import { useSpace } from '@/composables/useSpace'

const props = defineProps({
  mode: { type: Object, default: () => ({}) },
  hasResult: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  needsKey: { type: Boolean, default: false },
})

const emit = defineEmits(['export', 'open-trace', 'open-settings', 'open-history'])
const openMore = ref(false)
const { panelOpen } = useSpace()

const isMock = () => props.mode?.mode === 'mock'

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
  <header class="hero">
    <div class="hero-inner">
      <div class="hero-left">
        <div class="wordmark" aria-hidden="true">LUMEN</div>
        <div>
          <h1 class="hero-title">智识有方</h1>
        </div>
      </div>

      <div class="hero-right">
        <div class="more-wrap">
          <button
            class="more-btn"
            :class="{ 'needs-key': needsKey }"
            type="button"
            :title="needsKey ? '填入 API Key' : '更多'"
            aria-haspopup="true"
            :aria-expanded="openMore"
            @click.stop="openMore = !openMore"
          >
            更多
          </button>
          <div v-if="openMore" class="more-menu" role="menu">
            <button type="button" role="menuitem" @click="pick('open-settings')">
              {{ isMock() ? '运行模式 · 内置' : '运行模式 · 模型' }}
              <em v-if="needsKey">填入 API Key</em>
            </button>
            <button type="button" role="menuitem" :disabled="!hasResult" @click="pick('export')">
              导出方案
            </button>
            <button type="button" role="menuitem" @click="pick('open-history')">历史</button>
            <button type="button" role="menuitem" @click="pick('open-trace')">日志</button>
            <button type="button" role="menuitem" @click="openSpace">个人空间</button>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.hero {
  position: relative;
  z-index: 128;
  overflow: visible;
  background: rgba(251, 249, 246, 0.92);
  color: #191919;
  border-bottom: 1px solid #e4ded5;
}

.hero-inner {
  position: relative;
  max-width: 1360px;
  margin: 0 auto;
  padding: 16px 26px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.hero-left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.wordmark {
  font-family: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  font-size: 13px;
  letter-spacing: 0.28em;
  color: #e51520;
  border: 1px solid #e4ded5;
  padding: 10px 10px 8px;
  line-height: 1;
}

.hero-title {
  font-family: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  font-size: 22px;
  font-weight: 400;
  letter-spacing: 0.08em;
  line-height: 1.2;
}

.hero-right {
  display: flex;
  align-items: center;
  flex: none;
}

.more-wrap {
  position: relative;
}

.more-btn {
  border: 1px solid #e4ded5;
  background: #fff;
  color: #191919;
  border-radius: 1000px;
  padding: 7px 14px;
  font-size: 12.5px;
}

.more-btn.needs-key {
  border-color: #e51520;
  color: #b45309;
}

.more-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 196px;
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

.more-menu button:hover:not(:disabled) {
  background: #f8f3ec;
}

.more-menu button:disabled {
  opacity: 0.4;
}

.more-menu em {
  font-style: normal;
  margin-left: 6px;
  color: #e51520;
  font-size: 11px;
}

@media (max-width: 860px) {
  .hero-inner {
    padding: 14px 16px;
  }
  .hero-title {
    font-size: 18px;
  }
}

@media (max-width: 390px) {
  .hero-inner {
    padding: 12px;
  }
  .hero-title {
    font-size: 16px;
  }
  .wordmark {
    font-size: 11px;
    padding: 8px 8px 6px;
  }
}
</style>
