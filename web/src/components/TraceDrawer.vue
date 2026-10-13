<script setup>
/**
 * TraceDrawer —— 日志回放抽屉
 * 直接展示后端 data/trace.log 的内容（与桌面版「📜 历史 / trace 回放」同源）。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from '@/i18n'

const props = defineProps({
  open: { type: Boolean, default: false },
  lines: { type: Array, default: () => [] },
  traceFile: { type: String, default: '' },
  error: { type: String, default: '' },
})
const { t } = useI18n()

const emit = defineEmits(['close', 'refresh'])

const filter = ref('all')

/** 事件名 → 颜色标签 */
function tone(event) {
  if (event.startsWith('pipeline')) return 'ev-pipe'
  if (event.includes('degraded') || event.includes('failed')) return 'ev-warn'
  if (event === 'cache_hit') return 'ev-cache'
  if (event === 'reviewer_retry') return 'ev-warn'
  return 'ev-agent'
}

const visible = computed(() => {
  const list = props.lines || []
  if (filter.value === 'all') return list.slice(-220)
  if (filter.value === 'trace-only') return list.filter((l) => l.event.startsWith('pipeline'))
  return list.filter((l) => !l.event.startsWith('pipeline'))
})

function dataText(d) {
  if (!d) return ''
  try {
    return JSON.stringify(d, null, 0).replace(/^{|}$/g, '')
  } catch (_) {
    return String(d)
  }
}

const fileBase = computed(() => (props.traceFile || '').split(/[\\/]/).pop() || 'trace.log')

/**
 * Esc 关闭：给「关闭」多一条不依赖鼠标命中的出口。
 * 起因：抽屉头部原来被固定顶栏（z-index 150 > 抽屉 60）盖住，关闭按钮点不到。
 */
function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
}
watch(
  () => props.open,
  (v) => {
    if (typeof window === 'undefined') return
    if (v) window.addEventListener('keydown', onKeydown)
    else window.removeEventListener('keydown', onKeydown)
  },
)
onBeforeUnmount(() => {
  if (typeof window !== 'undefined') window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <transition name="drawer">
    <aside v-if="open" class="drawer">
      <div class="drawer-head">
        <div>
          <div class="drawer-title">{{ t('traceDrawer.1') }}</div>
          <div class="drawer-sub">{{ fileBase }} · {{ lines.length }} 行</div>
        </div>
        <div class="drawer-actions">
          <button class="btn btn-ghost tiny" @click="emit('refresh')">{{ t('traceDrawer.2') }}</button>
          <button class="btn btn-ghost tiny" @click="emit('close')">{{ t('traceDrawer.3') }}</button>
        </div>
      </div>

      <div class="filters">
        <button
          v-for="f in [
            { k: 'all', t: t('traceDrawerX.1') },
            { k: 'trace-only', t: t('traceDrawerX.2') },
            { k: 'agents', t: 'Agent' },
          ]"
          :key="f.k"
          class="filter"
          :class="{ on: filter === f.k }"
          @click="filter = f.k"
        >
          {{ f.t }}
        </button>
      </div>

      <div class="drawer-body">
        <!-- 后端不可用时给出明确提示，而不是静默显示 0 行 -->
        <div v-if="error && !visible.length" class="drawer-empty drawer-err">
          <span>⚠️</span>
          <p><b>{{ t('traceDrawer.4') }}</b></p>
          <p class="err-msg">{{ error }}</p>
          <p class="err-hint">{{ t('traceDrawer.5') }}</p>
        </div>

        <div v-else-if="!visible.length" class="drawer-empty">
          <span>📭</span>
          <p>{{ t('traceDrawer.6') }}</p>
        </div>

        <div v-for="(l, i) in visible" :key="i" class="trace-line">
          <span class="ts">{{ l.ts }}</span>
          <span class="ev" :class="tone(l.event)">{{ l.event }}</span>
          <span v-if="l.data" class="payload">{{ dataText(l.data) }}</span>
        </div>
      </div>
    </aside>
  </transition>
</template>

<style scoped>
.drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 44px;
  width: min(560px, 92vw);
  background: #191919;
  color: #e4ded5;
  /* ⚠️ 必须高于固定顶栏 .hero（z-index 150）。以前是 60 ⇒ 顶栏盖住抽屉头部，
     「刷新 / 关闭」看得见却点不到（.hero 没有 pointer-events:none，会吃掉点击）。
     取 180：高于顶栏 150 / 悬浮窗与总览 160 / 宠物档案 155 / 引导 175，
     低于真·模态（ModalDialog 200、ExportPreview 220）。 */
  z-index: 180;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
}

.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid #2c2c2c;
}

.drawer-title {
  font-family: var(--font-serif);
  font-size: 15px;
  font-weight: 400;
  color: #f7f2ea;
}

.drawer-sub {
  font-size: 11px;
  color: #808080;
  font-family: var(--font-mono);
}

.drawer-actions {
  display: flex;
  gap: 6px;
}

.tiny {
  padding: 5px 10px;
  font-size: 11.5px;
}

.filters {
  display: flex;
  gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid #2c2c2c;
}

.filter {
  border: 1px solid #3a3a3a;
  background: transparent;
  color: #a39b92;
  border-radius: 999px;
  padding: 3px 12px;
  font-size: 11.5px;
}

.filter.on {
  background: #e51520;
  border-color: #e51520;
  color: #fff;
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 10px 12px 18px;
  font-family: var(--font-mono);
  font-size: 11.5px;
}

.drawer-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #808080;
  padding: 60px 20px;
  text-align: center;
  font-family: var(--font);
  font-size: 12.5px;
}

.drawer-empty span {
  font-size: 28px;
}

.drawer-err {
  color: #fcd34d;
}

.err-msg {
  color: #fca5a5;
  font-family: var(--font-mono);
  font-size: 11.5px;
  word-break: break-all;
  max-width: 420px;
}

.err-hint {
  color: #94a3b8;
  max-width: 420px;
}

.trace-line {
  padding: 5px 8px;
  border-radius: 6px;
  line-height: 1.65;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
}

.trace-line:nth-child(odd) {
  background: rgba(255, 255, 255, 0.025);
}

.ts {
  color: #6b6560;
  flex: none;
}

.ev {
  font-weight: 700;
  flex: none;
}

.ev-pipe {
  color: #f08a8f;
}

.ev-agent {
  color: #f3d2a8;
}

.ev-warn {
  color: #fcd34d;
}

.ev-cache {
  color: #6ee7b7;
}

.payload {
  color: #a39b92;
  word-break: break-all;
}

.drawer-enter-active,
.drawer-leave-active {
  transition: transform 0.24s ease;
}

.drawer-enter-from,
.drawer-leave-to {
  transform: translateX(100%);
}
</style>
