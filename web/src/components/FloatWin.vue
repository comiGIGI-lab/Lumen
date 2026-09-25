<script setup>
/**
 * FloatWin —— 个人空间悬浮窗壳
 * 标题栏：名称 + 减号缩小 / 收到标题栏 + 加号放大。可拖动。
 * 触控：标题栏拖动手势独占，不让页面跟着滚；加减号仍可点。
 */
import { computed, onBeforeUnmount } from 'vue'
import { useSpace } from '@/composables/useSpace'

const props = defineProps({
  id: { type: String, required: true },
})

const { windows, zOrder, WIN_META, shrink, grow, moveTo, bringFront, barWidth, layoutMode, clampPos, viewW } = useSpace()

const win = computed(() => windows[props.id])
const title = WIN_META[props.id]?.title || props.id
const studyLayout = computed(() => layoutMode.value === 'study')

const boxStyle = computed(() => {
  const w = win.value
  const compact = viewW.value <= 430
  const width = barWidth(w.collapsed, w.size, compact, layoutMode.value, props.id)
  const shown = clampPos(props.id, w.x, w.y)
  return {
    left: `${Math.round(shown.x)}px`,
    top: `${Math.round(shown.y)}px`,
    width: `${width}px`,
    zIndex: zOrder[props.id] || 129,
  }
})

let drag = null

function isControl(el) {
  return !!(el && el.closest && el.closest('.win-btns'))
}

function onPointerDown(e) {
  if (e.button != null && e.button !== 0) return
  if (isControl(e.target)) return
  bringFront(props.id)
  const shown = clampPos(props.id, win.value.x, win.value.y)
  drag = {
    pid: e.pointerId,
    ox: e.clientX - shown.x,
    oy: e.clientY - shown.y,
    moved: false,
    sx: e.clientX,
    sy: e.clientY,
  }
  try {
    e.currentTarget.setPointerCapture(e.pointerId)
  } catch (_) {
    /* 部分浏览器不支持 capture，退回 window 监听 */
  }
  window.addEventListener('pointermove', onPointerMove, { passive: false })
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}

function onPointerMove(e) {
  if (!drag || (drag.pid != null && e.pointerId !== drag.pid)) return
  const dx = e.clientX - drag.sx
  const dy = e.clientY - drag.sy
  if (!drag.moved && dx * dx + dy * dy < 9) return
  drag.moved = true
  if (e.cancelable) e.preventDefault()
  moveTo(props.id, e.clientX - drag.ox, e.clientY - drag.oy)
}

function onPointerUp() {
  drag = null
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
}

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
})
</script>

<template>
  <section
    class="win"
    :class="['s-' + win.size, { collapsed: win.collapsed, 'layout-study': studyLayout }]"
    :style="boxStyle"
  >
    <header class="win-bar" @pointerdown="onPointerDown">
      <span class="win-name">{{ title }}</span>
      <span class="win-extra"><slot name="title-extra" /></span>
      <div class="win-btns">
        <button type="button" class="sq" title="缩小" aria-label="缩小" @click="shrink(id)">−</button>
        <button type="button" class="sq" title="放大" aria-label="放大" @click="grow(id)">+</button>
      </div>
    </header>
    <div v-show="!win.collapsed" class="win-body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.win {
  position: fixed;
  display: flex;
  flex-direction: column;
  background: rgba(251, 249, 246, 0.94);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: var(--shadow-btn);
  backdrop-filter: blur(12px);
  overflow: hidden;
  max-width: calc(100vw - 16px);
}

.win-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 6px 8px 6px 12px;
  cursor: grab;
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
  border-bottom: 1px solid transparent;
}

.win:not(.collapsed) .win-bar {
  border-bottom-color: var(--border);
}

.win-name {
  font-family: var(--font-serif);
  font-size: 14px;
  letter-spacing: 0.06em;
  color: var(--text-primary);
  flex: none;
}

.win-extra {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  color: var(--text-muted);
  pointer-events: none;
}

.win-btns {
  display: flex;
  gap: 4px;
  flex: none;
  touch-action: manipulation;
}

.sq {
  width: 28px;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 16px;
  line-height: 1;
  touch-action: manipulation;
}

.sq:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.win-body {
  padding: 10px 12px 12px;
  overflow: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-y;
}

.win-body :deep(input[type='range']) {
  touch-action: none;
}

.s-1 .win-body {
  max-height: 240px;
}
.s-2 .win-body {
  max-height: 340px;
}
.s-3 .win-body {
  max-height: 460px;
}

.layout-study.s-1 .win-body {
  max-height: min(48vh, 420px);
}
.layout-study.s-2 .win-body {
  max-height: min(52vh, 520px);
}
.layout-study.s-3 .win-body {
  max-height: min(72vh, 720px);
}

@media (max-width: 430px) {
  .win-bar {
    min-height: 44px;
    padding: 8px 8px 8px 12px;
  }
  .win-name {
    font-size: 13px;
  }
  .win-body {
    padding: 8px 10px 10px;
  }
  .layout-study.s-1 .win-body,
  .layout-study.s-2 .win-body,
  .layout-study.s-3 .win-body {
    max-height: min(58vh, 520px);
  }
}
</style>
