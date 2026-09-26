<script setup>
/**
 * SpaceLayer —— 自习坞 / 待办 / 日期三个悬浮窗 + 个人空间入口
 * 欢迎层、工具页、自习空间都挂同一套 FloatWin；坐标走 useSpace 三套 layout。
 */
import FloatWin from './FloatWin.vue'
import StudyDock from './StudyDock.vue'
import TodoDock from './TodoDock.vue'
import DateDock from './DateDock.vue'
import SpacePanel from './SpacePanel.vue'
import CountdownTimer from './CountdownTimer.vue'
import { computed } from 'vue'
import { useI18n } from '@/i18n'
import { useSpace } from '@/composables/useSpace'
import { useStudyTimer } from '@/composables/useStudyTimer'

defineProps({
  floats: { type: Boolean, default: true },
})

const emit = defineEmits(['scene-change'])
const { t } = useI18n()
const { windows, panelOpen, todos } = useSpace()
const { clock } = useStudyTimer()
const pinnedTodo = computed(() => todos.value.find((t) => t.pinned) || null)

function openSpace() {
  panelOpen.value = true
}
</script>

<template>
  <div class="space-layer">
    <FloatWin v-if="floats && windows.study.on" id="study">
      <template #title-extra>
        <span class="mini">{{ clock }}</span>
      </template>
      <StudyDock @scene-change="emit('scene-change', $event)" />
    </FloatWin>

    <FloatWin v-if="floats && windows.todo.on" id="todo">
      <template #title-extra>
        <span v-if="pinnedTodo" class="mini" :title="pinnedTodo.text">{{ pinnedTodo.text }}</span>
      </template>
      <TodoDock />
    </FloatWin>

    <FloatWin v-if="floats && windows.date.on" id="date">
      <template #title-extra>
        <CountdownTimer compact />
      </template>
      <DateDock />
    </FloatWin>

    <button
      type="button"
      class="space-fab"
      :title="t('spaceLayer.1')"
      :aria-label="t('spaceLayer.2')"
      @click="openSpace"
    >{{ t('spaceLayer.3') }}</button>

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
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  background: rgba(var(--bg-app-rgb), 0.92);
  color: var(--text-primary);
  font-size: 12px;
  letter-spacing: 0.08em;
  box-shadow: var(--shadow-btn);
}

@media (max-width: 430px) {
  .space-fab {
    left: 8px;
    bottom: 16px;
  }
}
</style>
