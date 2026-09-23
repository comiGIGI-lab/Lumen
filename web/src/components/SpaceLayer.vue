<script setup>
/**
 * SpaceLayer —— 自习坞 / 待办 / 日期三个悬浮窗 + 个人空间入口
 * 欢迎层与工具界面都在，不进顶栏。
 */
import FloatWin from './FloatWin.vue'
import StudyDock from './StudyDock.vue'
import TodoDock from './TodoDock.vue'
import DateDock from './DateDock.vue'
import SpacePanel from './SpacePanel.vue'
import { useSpace } from '@/composables/useSpace'
import { useStudyTimer } from '@/composables/useStudyTimer'

const emit = defineEmits(['scene-change'])
const { windows, panelOpen } = useSpace()
const { clock } = useStudyTimer()

function openSpace() {
  panelOpen.value = true
}
</script>

<template>
  <div class="space-layer">
    <FloatWin v-if="windows.study.on" id="study">
      <template #title-extra>
        <span class="mini">{{ clock }}</span>
      </template>
      <StudyDock @scene-change="emit('scene-change', $event)" />
    </FloatWin>

    <FloatWin v-if="windows.todo.on" id="todo">
      <TodoDock />
    </FloatWin>

    <FloatWin v-if="windows.date.on" id="date">
      <DateDock />
    </FloatWin>

    <button
      type="button"
      class="space-fab"
      title="个人空间"
      aria-label="个人空间"
      @click="openSpace"
    >
      空间
    </button>

    <SpacePanel v-if="panelOpen" />
  </div>
</template>

<style scoped>
.space-layer {
  pointer-events: none;
}
.space-layer :deep(.win),
.space-fab {
  pointer-events: auto;
}

.mini {
  font-variant-numeric: tabular-nums;
}

.space-fab {
  position: fixed;
  left: 12px;
  bottom: 56px;
  z-index: 140;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 1000px;
  background: rgba(251, 249, 246, 0.92);
  color: var(--text-primary);
  font-size: 12px;
  letter-spacing: 0.08em;
  box-shadow: var(--shadow-btn);
}

@media (max-width: 390px) {
  .space-fab {
    left: 8px;
    bottom: 48px;
  }
}
</style>
