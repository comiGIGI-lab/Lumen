<script setup>
/**
 * AppHeader —— 顶部 Hero 区（沿用桌面版的紫蓝渐变 + 模式角标）
 */
const props = defineProps({
  mode: { type: Object, default: () => ({}) },
  hasResult: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  /** LLM 模式但没填 Key —— 角标会高亮并显示「填入 API Key」 */
  needsKey: { type: Boolean, default: false },
})

const emit = defineEmits(['export', 'open-trace', 'open-settings', 'open-history'])

const isMock = () => props.mode?.mode === 'mock'
</script>

<template>
  <header class="hero">
    <div class="hero-bg" aria-hidden="true"></div>

    <div class="hero-inner">
      <div class="hero-left">
        <div class="logo">📘</div>
        <div>
          <h1 class="hero-title">study-liu</h1>
          <p class="hero-sub">
            输入课程名 · 一键生成 <b>大纲</b> + <b>资源</b> + <b>个性化计划</b>
          </p>
        </div>
      </div>

      <div class="hero-right">
        <button
          class="mode-pill"
          :class="[isMock() ? 'is-mock' : 'is-llm', { 'needs-key': needsKey }]"
          type="button"
          :title="`${mode.reason || ''}　点这里切换运行模式 / 填入 API Key`"
          @click="emit('open-settings')"
        >
          {{ isMock() ? '📦' : '🤖' }}
          {{ mode.label || '读取中…' }}
          <em>{{ isMock() ? '内置数据，无需 API' : '调用在线大模型' }}</em>
          <span class="pill-cta">{{ needsKey ? '填入 API Key' : '设置 ›' }}</span>
        </button>

        <div class="hero-actions">
          <button class="hero-btn" :disabled="!hasResult" @click="emit('export')">
            📥 导出方案
          </button>
          <button class="hero-btn" @click="emit('open-history')">🕘 历史</button>
          <button class="hero-btn" @click="emit('open-trace')">📜 日志</button>
        </div>
        <!-- 设置入口只保留左侧模式角标（点击即打开设置），不再重复放一个「⚙ 设置」按钮 -->

        <!-- 明确说明「为什么不是 LLM 模式」，不用让用户去猜 -->
        <div v-if="mode.reason" class="mode-reason">ⓘ {{ mode.reason }}</div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.hero {
  position: relative;
  overflow: hidden;
  background: linear-gradient(120deg, #6366f1 0%, #7c5cf6 50%, #8b5cf6 100%);
  color: #fff;
}

/* 背景光晕，纯装饰 */
.hero-bg {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(
      circle at 12% 20%,
      rgba(255, 255, 255, 0.24),
      transparent 42%
    ),
    radial-gradient(circle at 88% 90%, rgba(6, 182, 212, 0.34), transparent 46%);
}

.hero-inner {
  position: relative;
  max-width: 1360px;
  margin: 0 auto;
  padding: 22px 26px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}

.hero-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.logo {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.3);
  display: grid;
  place-items: center;
  font-size: 24px;
  backdrop-filter: blur(6px);
}

.hero-title {
  font-size: 25px;
  font-weight: 800;
  letter-spacing: 0.4px;
  line-height: 1.2;
}

.hero-sub {
  font-size: 12.5px;
  opacity: 0.9;
  margin-top: 3px;
}

.hero-sub b {
  font-weight: 700;
}

.hero-right {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.mode-reason {
  flex-basis: 100%;
  text-align: right;
  font-size: 11.5px;
  line-height: 1.55;
  color: rgba(255, 255, 255, 0.82);
}

.mode-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 13px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.3);
  cursor: pointer;
  transition: all 0.15s;
}

.mode-pill:hover {
  background: rgba(255, 255, 255, 0.28);
  border-color: rgba(255, 255, 255, 0.55);
}

/* LLM 模式但没 Key：高亮提示，别让用户以为一切正常 */
.mode-pill.needs-key {
  background: rgba(255, 255, 255, 0.95);
  border-color: #fff;
  color: #b45309;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.22);
  animation: pill-pulse 2s ease-in-out infinite;
}

@keyframes pill-pulse {
  0%, 100% { box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.22); }
  50%      { box-shadow: 0 0 0 6px rgba(255, 255, 255, 0.08); }
}

.pill-cta {
  font-weight: 700;
  font-size: 11px;
  padding-left: 6px;
  margin-left: 2px;
  border-left: 1px solid currentColor;
  opacity: 0.9;
}

.mode-pill em {
  font-style: normal;
  font-weight: 500;
  font-size: 11px;
  opacity: 0.78;
}

.hero-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.hero-btn {
  border: 1px solid rgba(255, 255, 255, 0.32);
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border-radius: 8px;
  padding: 7px 13px;
  font-size: 12.5px;
  font-weight: 600;
  transition: all 0.15s;
}

.hero-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.24);
}

.hero-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.hero-btn.solid {
  background: #fff;
  color: var(--primary-dark);
  border-color: #fff;
}

.hero-btn.solid:hover {
  filter: brightness(0.96);
}

@media (max-width: 860px) {
  .hero-inner {
    padding: 18px 16px;
  }
  .hero-title {
    font-size: 21px;
  }
}
</style>
