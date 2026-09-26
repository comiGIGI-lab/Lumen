<script setup>
/**
 * ModalDialog —— 通用弹窗外壳
 */
defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  icon: { type: String, default: '' },
  width: { type: String, default: '560px' },
  /** 移动端（≤430px）是否全屏化。桌面端仍用 width；媒体查询里才覆盖宽高/圆角。 */
  fullscreenOnMobile: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])
</script>

<template>
  <transition name="modal">
    <div v-if="open" class="mask" :class="{ 'mask-fullscreen': fullscreenOnMobile }" @click.self="emit('close')">
      <div class="dialog card" :class="{ 'dialog-fullscreen': fullscreenOnMobile }" :style="{ width }">
        <div class="dlg-head" :class="{ 'dlg-head-sticky': fullscreenOnMobile }">
          <div class="dlg-title">
            <span v-if="icon">{{ icon }}</span>
            {{ title }}
          </div>
          <button class="close" @click="emit('close')">✕</button>
        </div>

        <div class="dlg-body" :class="{ 'dlg-body-scroll': fullscreenOnMobile }">
          <slot />
        </div>

        <div v-if="$slots.footer" class="dlg-foot" :class="{ 'dlg-foot-sticky': fullscreenOnMobile }">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.42);
  backdrop-filter: blur(2px);
  z-index: 120;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.dialog {
  max-width: 100%;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.dlg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, #fbf9f6, #fff);
}

.dlg-title {
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 400;
  display: flex;
  align-items: center;
  gap: 8px;
}

.close {
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 15px;
  padding: 4px 8px;
  border-radius: 6px;
}

.close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.dlg-body {
  min-height: 0;
  padding: 16px 18px;
  overflow-y: auto;
}

.dlg-foot {
  padding: 12px 18px;
  border-top: 1px solid var(--border);
  background: var(--bg-soft);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.18s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

/* ---------- 移动端全屏（≤430px） ---------- */
/* 桌面照旧：样式只在 max-width:430px 生效；调用方没开 fullscreenOnMobile 就不命中。 */
@media (max-width: 430px) {
  .mask-fullscreen {
    padding: 0;
    align-items: stretch;
    justify-content: stretch;
  }
  .dialog-fullscreen {
    width: 100vw !important;
    max-width: 100vw !important;
    height: 100vh;
    height: 100dvh;
    max-height: 100vh;
    max-height: 100dvh;
    border-radius: 0;
    overflow: hidden;
  }
  .dlg-head-sticky {
    flex: none;
    position: sticky;
    top: 0;
    z-index: 2;
    padding-top: calc(14px + env(safe-area-inset-top, 0px));
  }
  /* 表单区吃满剩余高度并滚动；max-height 兜底，避免旧 WebKit 不收缩 flex。 */
  .dlg-body-scroll {
    flex: 1 1 auto;
    min-height: 0;
    max-height: calc(100dvh - 148px);
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior: contain;
  }
  .dlg-foot-sticky {
    flex: none;
    position: sticky;
    bottom: 0;
    z-index: 2;
    flex-wrap: wrap;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    background: rgba(251, 249, 246, 0.86);
    padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
  }
}
</style>
