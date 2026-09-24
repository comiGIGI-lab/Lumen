<script setup>
/**
 * FloatWin —— 个人空间悬浮窗壳
 * 标题栏：名称 + 减号缩小 / 收到标题栏 + 加号放大。可拖动。
 */
import { computed, onBeforeUnmount } from 'vue'
import { useSpace } from '@/composables/useSpace'

const props = defineProps({
  id: { type: String, required: true },
})

const { windows, zOrder, WIN_META, shrink, grow, moveTo, bringFront, barWidth } = useSpace()

const win = computed(() => windows[props.id])
const title = WIN_META[props.id]?.title || props.id

const boxStyle = computed(() => {
  const w = win.value
  const compact = typeof window !== 'undefined' && window.innerWidth <= 430
  let width = barWidth(w.collapsed, w.size, compact)
  if (props.id === 'todo' && w.collapsed) width = compact ? 196 : 248
  if (props.id === 'date' && w.collapsed) width = compact ? 196 : 248
  return {
    left: `${Math.round(w.x)}px`,
    top: `${Math.round(w.y)}px`,
    width: `${width}px`,
    zIndex: zOrder[props.id] || 110,
  }
})

let drag = null

function onPointerDown(e) {
  if (e.button != null && e.button !== 0) return
  if (e.target && e.target.closest && e.target.closest('.win-btns')) return
  bringFront(props.id)
  drag = {
    ox: e.clientX - win.value.x,
    oy: e.clientY - win.value.y,
  }
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}

function onPointerMove(e) {
  if (!drag) return
  moveTo(props.id, e.clientX - drag.ox, e.clientY - drag.oy)
}

function onPointerUp() {
  drag = null
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
}

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
})
</script>

<template>
  <section
    class="win"
    :class="['s-' + win.size, { collapsed: win.collapsed }]"
    :style="boxStyle"
    @mousedown="bringFront(id)"
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
  min-height: 36px;
  padding: 4px 8px 4px 12px;
  cursor: grab;
  user-select: none;
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
}

.win-btns {
  display: flex;
  gap: 4px;
  flex: none;
}

.sq {
  width: 22px;
  height: 22px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1;
}

.sq:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.win-body {
  padding: 10px 12px 12px;
  overflow: auto;
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

@media (max-width: 390px) {
  .win-name {
    font-size: 13px;
  }
}
</style>
