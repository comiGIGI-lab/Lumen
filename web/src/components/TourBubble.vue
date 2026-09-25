<script setup>
/**
 * TourBubble —— 单界面点位气泡（点状提示，非模态）
 *
 * 与 TourDialog 总览的区别：
 *   - 总览弹窗：首访主应用，遮罩覆盖，z-index 160；
 *   - 气泡：进入对应功能界面时延迟 800ms 浮起，无遮罩，z-index 150。
 *
 * props:
 *   open: boolean —— 控制显示；父组件负责 storage_key 判定 + 一次性闸门
 *   title: string
 *   body: string
 *   storage_key: string ——「不再提示」写 true 的 localStorage 键
 *   position: 'bottom-right' | 'top-right' | 'bottom-left' | 'top-left' —— 默认 bottom-right
 *
 * emits:
 *   close: 点了「知道了」或 X
 *   dismiss: 点了「不再提示」，写 storage_key=true 后再触发
 */
const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '小提示' },
  body: { type: String, default: '' },
  storageKey: { type: String, required: true },
  position: {
    type: String,
    default: 'bottom-right',
    validator: (v) =>
      ['bottom-right', 'top-right', 'bottom-left', 'top-left'].includes(v),
  },
})

const emit = defineEmits(['close', 'dismiss'])

function onDismiss() {
  try {
    localStorage.setItem(props.storageKey, 'true')
  } catch (_) {
    /* 存不上也不阻塞 */
  }
  emit('dismiss')
}
</script>

<template>
  <transition name="bubble">
    <div
      v-if="open"
      class="bubble"
      :class="`pos-${position}`"
      role="note"
      aria-live="polite"
    >
      <div class="card">
        <div class="head">
          <span class="dot" aria-hidden="true" />
          <b class="title">{{ title }}</b>
          <button
            class="x"
            type="button"
            aria-label="关闭"
            @click="emit('close')"
          >✕</button>
        </div>
        <p class="body">{{ body }}</p>
        <div class="foot">
          <button class="ghost" type="button" @click="emit('close')">
            知道了
          </button>
          <button class="ok" type="button" @click="onDismiss">
            不再提示
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.bubble {
  position: fixed;
  z-index: 150;
  /* 比悬浮窗 140 高一档；从浮窗上方浮起，不抢总览（160） */
  pointer-events: none;
}

.bubble.pos-bottom-right {
  right: 18px;
  bottom: 96px;
}

.bubble.pos-top-right {
  right: 18px;
  top: 18px;
}

.bubble.pos-bottom-left {
  left: 18px;
  bottom: 96px;
}

.bubble.pos-top-left {
  left: 18px;
  top: 18px;
}

.card {
  pointer-events: auto;
  width: 280px;
  max-width: calc(100vw - 32px);
  background: var(--bg-app);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 14px 10px;
  box-shadow: 0 8px 22px rgba(25, 25, 25, 0.12);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e51520;
  flex: none;
}

.title {
  flex: 1;
  font-family: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  font-weight: 400;
  font-size: 14px;
  color: var(--text-primary);
}

.x {
  border: none;
  background: transparent;
  color: #808080;
  font-size: 13px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
}

.x:hover {
  background: #f1ece4;
  color: var(--text-primary);
}

.body {
  margin: 0 0 10px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.foot {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.ghost,
.ok {
  border-radius: 1000px;
  padding: 5px 12px;
  font-size: 12.5px;
  cursor: pointer;
}

.ghost {
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
}

.ok {
  border: 1px solid #e51520;
  background: #e51520;
  color: #fff;
}

.ghost:focus-visible,
.ok:focus-visible,
.x:focus-visible {
  outline: 2px solid #e51520;
  outline-offset: 2px;
}

.bubble-enter-active,
.bubble-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.bubble-enter-from,
.bubble-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

@media (max-width: 430px) {
  .bubble.pos-bottom-right {
    right: 8px;
    bottom: 132px;
  }
  .bubble.pos-top-right {
    right: 8px;
    top: 8px;
  }
  .bubble.pos-bottom-left {
    left: 8px;
    bottom: 132px;
  }
  .bubble.pos-top-left {
    left: 8px;
    top: 8px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .bubble-enter-active,
  .bubble-leave-active {
    transition: none;
  }
}
</style>