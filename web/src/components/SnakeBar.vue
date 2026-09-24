<script setup>
import { computed } from 'vue'

const props = defineProps({
  progress: { type: Number, default: 0 },
  status: { type: String, default: 'waiting' },
})

const pct = computed(() => Math.max(0, Math.min(100, Number(props.progress) || 0)))
const running = computed(() => props.status === 'uploading' || props.status === 'parsing')
const done = computed(() => props.status === 'ready')
const fill = computed(() => (done.value ? 100 : pct.value))

const PATH =
  'M 4 8 H 16 V 4 H 28 V 12 H 40 V 8 H 52 V 4 H 64 V 12 H 76 V 8 H 88 V 4 H 100 V 12 H 112 V 8 H 124 V 4 H 136 V 12 H 156 V 8'
</script>

<template>
  <div
    class="snake"
    :class="{ 'is-run': running, 'is-done': done }"
    aria-hidden="true"
  >
    <svg viewBox="0 0 160 16" preserveAspectRatio="none">
      <path class="snake-rail" :d="PATH" pathLength="100" />
      <path
        class="snake-body"
        :d="PATH"
        pathLength="100"
        :style="{ strokeDasharray: fill + ' 100' }"
      />
    </svg>
  </div>
</template>

<style scoped>
.snake {
  width: 100%;
  height: 16px;
}
.snake svg {
  width: 100%;
  height: 16px;
  display: block;
  overflow: visible;
}
.snake-rail,
.snake-body {
  fill: none;
  stroke-width: 4;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.snake-rail {
  stroke: #f1ece4;
}
.snake-body {
  stroke: #e51520;
  transition: stroke-dasharray 0.28s linear;
}
.snake.is-done .snake-body {
  stroke: #2e7d32;
  stroke-dasharray: 100 0;
}
</style>
