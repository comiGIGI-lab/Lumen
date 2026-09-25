<script setup>
import { useI18n } from '@/i18n'
/**
 * TourDialog —— 首访新手指引弹窗
 *
 * 学伴宠物第一人称口吻，带用户认一遍六个入口。只在两种情形出现：
 *   - 首访进主应用（zjxt.pet 有、zjxt.tour_done 没有或为 false），每次加载只自动弹一次；
 *   - 设置里手动点「查看新手指引」重新打开（不写 zjxt.tour_done）。
 * 「知道了」只关弹窗；「不再提示」关弹窗并写 zjxt.tour_done='true'。
 */
const props = defineProps({
  open: { type: Boolean, default: false },
  /** 当前学伴宠物的名字（usePet.displayName，例如「灯灯」）。
   *  默认留空，由模板回退到 i18n 文案 —— 写死中文会在英文界面里露出来。 */
  petName: { type: String, default: '' },
})
const { t } = useI18n()

const emit = defineEmits(['close', 'dismiss'])

// 引导文案放在 i18n 的 tour.greeting（见 src/i18n/auto-*.json）。
// 不在这里写成常量 —— 常量不会随语言切换更新。
</script>

<template>
  <transition name="modal">
    <div v-if="open" class="mask" @click.self="emit('close')">
      <div class="dialog card" role="dialog" aria-modal="true" :aria-label="t('tourDialog.1')">
        <div class="dlg-head">
          <div class="dlg-title">{{ t('tour.title', { name: petName || t('tour.buddy') }) }}</div>
          <button class="close" type="button" :aria-label="t('tourDialog.2')" @click="emit('close')">✕</button>
        </div>

        <div class="dlg-body">
          <p class="tour-copy">{{ t('tour.greeting') }}</p>
        </div>

        <div class="dlg-foot">
          <button class="btn btn-ghost" type="button" @click="emit('close')">{{ t('tourDialog.3') }}</button>
          <button class="btn btn-primary" type="button" @click="emit('dismiss')">{{ t('tourDialog.4') }}</button>
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
  /* 高于悬浮窗(140) 与 设置弹窗(120)：从设置内手动触发时须盖在设置之上才看得见 */
  z-index: 160;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.dialog {
  max-width: 100%;
  width: 520px;
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
  background: linear-gradient(180deg, var(--bg-soft), var(--bg-card));
}

.dlg-title {
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 400;
}

.close {
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 15px;
  padding: 4px 8px;
  border-radius: 6px;
  cursor: pointer;
}

.close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.dlg-body {
  padding: 18px 20px;
}

.tour-copy {
  margin: 0;
  font-size: 14px;
  line-height: 1.95;
  color: var(--text-secondary);
  letter-spacing: 0.01em;
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
