<script setup>
import { useI18n } from '@/i18n'
/**
 * StatusBar —— 固定底部状态栏（与桌面版一致，不参与滚动）
 */
defineProps({
  text: { type: String, default: '就绪' },
  tone: { type: String, default: 'normal' }, // normal | warn | error | success
  stats: { type: Object, default: null },
  duration: { type: Number, default: 0 },
  fromCache: { type: Boolean, default: false },
})
const { t } = useI18n()

</script>

<template>
  <footer class="status" :class="`t-${tone}`">
    <div class="left">
      <span class="bullet"></span>
      <span class="msg">{{ text }}</span>
      <span class="motto" title="LUMEN, Latin for light. ZhiShiYouFang: where the light reaches, learning finds its way.">{{ t('statusBar.1') }}</span>
    </div>

    <div class="right">
      <span class="motto-en">LUMEN, Latin for light.</span>
      <span v-if="fromCache" class="pill cache">{{ t('statusBar.2') }}</span>
      <span v-if="stats" class="pill">
        大纲 {{ stats.outline }} 章 · 资源 {{ stats.resources }} 项 · 计划 {{ stats.plan }} 天
      </span>
      <span v-if="duration" class="pill mono">{{ duration }} ms</span>
    </div>
  </footer>
</template>

<style scoped>
.status {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  min-height: 32px;
  height: auto;
  background: #191919;
  color: #d2c9bc;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 6px 16px;
  font-size: 11.5px;
  z-index: 70;
  flex-wrap: wrap;
}

.left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.bullet {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #808080;
}

.t-warn .bullet {
  background: #fcd34d;
  animation: pulse-soft 1s ease-in-out infinite;
}

.t-error .bullet {
  background: #f87171;
}

.t-success .bullet {
  background: #34d399;
}

.msg {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.motto,
.motto-en {
  font-family: var(--font-serif);
  font-size: 11px;
  letter-spacing: 0.02em;
  color: #a39b92;
}

.motto {
  margin-left: 10px;
  padding-left: 10px;
  border-left: 1px solid #3a3a3a;
}

.motto-en {
  font-style: italic;
  opacity: 0.85;
  white-space: nowrap;
}

.t-warn .msg {
  color: #fcd34d;
}

.t-error .msg {
  color: #fca5a5;
}

.right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.pill {
  background: rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  padding: 1px 10px;
  white-space: nowrap;
}

.pill.cache {
  background: rgba(52, 211, 153, 0.18);
  color: #6ee7b7;
  font-weight: 700;
}

.mono {
  font-family: var(--font-mono);
}

@media (max-width: 860px) {
  .motto-en {
    display: none;
  }
  .left {
    flex-wrap: wrap;
  }
  .motto {
    margin-left: 0;
    padding-left: 0;
    border-left: none;
    flex-basis: 100%;
  }
}

@media (max-width: 760px) {
  .right .pill:not(.cache) {
    display: none;
  }
}
</style>
