<script setup>
/**
 * FloatWin —— 个人空间悬浮窗壳
 * 标题栏：名称 + 减号缩小 / 收到标题栏 + 加号放大。可拖动。
 * 收起后不再占原位标题栏，改成左右缘 30px 竖签（点签即 grow 展开）。
 * 触控：标题栏拖动手势独占，不让页面跟着滚；加减号仍可点。
 */
import { computed, onBeforeUnmount } from 'vue'
import { useI18n } from '@/i18n'
import { useSpace } from '@/composables/useSpace'

const props = defineProps({
  id: { type: String, required: true },
})
const { t } = useI18n()

const { windows, zOrder, WIN_IDS, WIN_META, shrink, grow, moveTo, bringFront, barWidth, layoutMode, clampPos, viewW, viewH, dateWinTitle, nearestCountdown } = useSpace()

const win = computed(() => windows[props.id])
const meta = WIN_META[props.id]
// 标题走 i18n；WIN_META.title 仅作兜底。倒数日窗有未到期事件时不再写「日期」。
const title = computed(() => {
  if (props.id === 'date' && dateWinTitle.value) return dateWinTitle.value
  return (meta?.titleKey ? t(meta.titleKey) : meta?.title) || props.id
})
const peekLabel = computed(() => {
  if (props.id === 'date' && nearestCountdown.value) return nearestCountdown.value.title
  return title.value
})
const studyLayout = computed(() => layoutMode.value === 'study')

/** 收起成探头时露出的签宽；高度按标题走，栈位按 WIN_IDS 错开，不挡左下「空间」。 */
const PEEK_W = 36
const PEEK_H = 108
const PEEK_GAP = 10

const peekSide = computed(() => {
  const w = win.value
  if (!w?.collapsed) return null
  const compact = viewW.value <= 430
  const width = barWidth(true, w.size, compact, layoutMode.value, props.id)
  const shown = clampPos(props.id, w.x, w.y)
  return shown.x + width / 2 < viewW.value / 2 ? 'left' : 'right'
})

const boxStyle = computed(() => {
  const w = win.value
  const compact = viewW.value <= 430
  if (w.collapsed) {
    const stack = Math.max(0, WIN_IDS.indexOf(props.id))
    const topSafe = compact ? 168 : viewW.value <= 860 ? 168 : 64
    const top = Math.min(
      topSafe + stack * (PEEK_H + PEEK_GAP),
      Math.max(topSafe, viewH.value - PEEK_H - 56),
    )
    const side = peekSide.value
    return {
      left: side === 'left' ? '0px' : 'auto',
      right: side === 'right' ? '0px' : 'auto',
      top: `${Math.round(top)}px`,
      width: `${PEEK_W}px`,
      height: `${PEEK_H}px`,
      zIndex: zOrder[props.id] || 129,
    }
  }
  const width = barWidth(false, w.size, compact, layoutMode.value, props.id)
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

function onPeekClick() {
  grow(props.id)
}

function onPointerDown(e) {
  if (win.value?.collapsed) return
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
    :class="[
      's-' + win.size,
      {
        collapsed: win.collapsed,
        'layout-study': studyLayout,
        'peek-left': peekSide === 'left',
        'peek-right': peekSide === 'right',
      },
    ]"
    :style="boxStyle"
  >
    <button
      v-if="win.collapsed"
      type="button"
      class="win-peek"
      :title="title"
      :aria-label="title"
      @click="onPeekClick"
    >
      <span class="win-peek-name">{{ peekLabel }}</span>
    </button>
    <template v-else>
      <header class="win-bar" @pointerdown="onPointerDown">
        <span class="win-name">{{ title }}</span>
        <span class="win-extra"><slot name="title-extra" /></span>
        <div class="win-btns">
          <button type="button" class="sq" :title="t('floatWin.1')" :aria-label="t('floatWin.2')" @click="shrink(id)">−</button>
          <button type="button" class="sq" :title="t('floatWin.3')" :aria-label="t('floatWin.4')" @click="grow(id)">+</button>
        </div>
      </header>
      <div class="win-body">
        <slot />
      </div>
    </template>
  </section>
</template>

<style scoped>
.win {
  position: fixed;
  display: flex;
  flex-direction: column;
  background: rgba(var(--bg-app-rgb), 0.94);
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

/* 收起：贴左右缘的窄签。米底、1px 描边、内侧一根红线。点签展开。 */
.win.collapsed {
  overflow: hidden;
  max-width: 36px;
  box-shadow: none;
  background: rgba(var(--bg-app-rgb), 0.92);
}
.win.collapsed.peek-left {
  border-radius: 0 10px 10px 0;
  border-left: none;
  border-right: 2px solid #e51520;
}
.win.collapsed.peek-right {
  border-radius: 10px 0 0 10px;
  border-right: none;
  border-left: 2px solid #e51520;
}
.win-peek {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 10px 0;
  border: none;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
}
.win-peek-name {
  writing-mode: vertical-rl;
  letter-spacing: 0.18em;
  font-family: var(--font-serif);
  font-size: 12px;
  line-height: 1;
  color: var(--text-primary);
}
.win-peek:hover .win-peek-name {
  color: #e51520;
}
.win-peek:focus-visible {
  outline: 2px solid #e51520;
  outline-offset: -2px;
}

.win-name {
  font-family: var(--font-serif);
  font-size: 14px;
  letter-spacing: 0.06em;
  color: var(--text-primary);
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
