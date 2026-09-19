<script setup>
/**
 * ResultPanel —— 三栏结果的通用外壳（标题 / 计数 / 空状态 / 滚动区）
 */
defineProps({
  title: { type: String, required: true },
  icon: { type: String, default: '📄' },
  count: { type: Number, default: 0 },
  unit: { type: String, default: '' },
  emptyText: { type: String, default: '暂无内容' },
  loading: { type: Boolean, default: false },
  accent: { type: String, default: '#6366f1' },
})
</script>

<template>
  <div class="panel card">
    <div class="panel-head" :style="{ borderTopColor: accent }">
      <div class="panel-title">
        <span class="ico">{{ icon }}</span>
        {{ title }}
      </div>
      <span v-if="count > 0" class="chip chip-indigo count">
        {{ count }} {{ unit }}
      </span>
    </div>

    <div class="panel-body">
      <div v-if="loading" class="panel-empty">
        <div class="dots"><i></i><i></i><i></i></div>
        <p>正在生成…</p>
      </div>

      <div v-else-if="count === 0" class="panel-empty">
        <div class="empty-ico">{{ icon }}</div>
        <p>{{ emptyText }}</p>
      </div>

      <div v-else class="panel-list fade-up">
        <slot />
      </div>
    </div>

    <div v-if="$slots.footer" class="panel-foot">
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  min-height: 380px;
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 13px 16px;
  border-bottom: 1px solid var(--border);
  border-top: 3px solid var(--primary);
  background: linear-gradient(180deg, #fbfcfe, #fff);
}

.panel-title {
  font-size: 14px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 7px;
}

.ico {
  font-size: 15px;
}

.count {
  flex: none;
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  max-height: 560px;
  padding: 12px 14px;
}

.panel-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.panel-empty {
  height: 100%;
  min-height: 280px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-faint);
  font-size: 12.5px;
}

.empty-ico {
  font-size: 30px;
  opacity: 0.35;
}

.dots {
  display: flex;
  gap: 5px;
}

.dots i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--primary-light);
  animation: pulse-soft 1.1s ease-in-out infinite;
}

.dots i:nth-child(2) {
  animation-delay: 0.18s;
}

.dots i:nth-child(3) {
  animation-delay: 0.36s;
}

.panel-foot {
  border-top: 1px solid var(--border);
  padding: 9px 14px;
  background: var(--bg-soft);
  font-size: 12px;
  color: var(--text-muted);
}
</style>
