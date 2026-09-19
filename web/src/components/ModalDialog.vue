<script setup>
/**
 * ModalDialog —— 通用弹窗外壳
 */
defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  icon: { type: String, default: '' },
  width: { type: String, default: '560px' },
})

const emit = defineEmits(['close'])
</script>

<template>
  <transition name="modal">
    <div v-if="open" class="mask" @click.self="emit('close')">
      <div class="dialog card" :style="{ width }">
        <div class="dlg-head">
          <div class="dlg-title">
            <span v-if="icon">{{ icon }}</span>
            {{ title }}
          </div>
          <button class="close" @click="emit('close')">✕</button>
        </div>

        <div class="dlg-body">
          <slot />
        </div>

        <div v-if="$slots.footer" class="dlg-foot">
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
  z-index: 80;
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
  background: linear-gradient(180deg, #fbfcfe, #fff);
}

.dlg-title {
  font-size: 15px;
  font-weight: 700;
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
</style>
