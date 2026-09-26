<script setup>
/**
 * SpaceLayer —— 自习坞 / 待办 / 日期三个悬浮窗 + 个人空间入口
 * 欢迎层、工具页、自习空间都挂同一套 FloatWin；坐标走 useSpace 三套 layout。
 * 浮窗收起后由 FloatWin 收成左右缘探头（点一下展开）。
 * 左下「空间」钮旁有 ‹，点一下收到左边竖签；点签拉回。
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
const { windows, panelOpen, todos, dateWinTitle, fabDocked, setFabDocked } = useSpace()
const { clock } = useStudyTimer()
const pinnedTodo = computed(() => todos.value.find((t) => t.pinned) || null)

function openSpace() {
  setFabDocked(false)
  panelOpen.value = true
}

function onFabClick() {
  if (fabDocked.value) {
    setFabDocked(false)
    return
  }
  openSpace()
}

function tuckFab() {
  panelOpen.value = false
  setFabDocked(true)
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
      <template v-if="!dateWinTitle" #title-extra>
        <CountdownTimer compact />
      </template>
      <DateDock />
    </FloatWin>

    <div class="space-entry" :class="{ docked: fabDocked }">
      <button
        type="button"
        class="space-fab"
        :class="{ docked: fabDocked }"
        :title="fabDocked ? t('spaceLayer.3') : t('spaceLayer.1')"
        :aria-label="t('spaceLayer.2')"
        @click="onFabClick"
      ><span class="space-fab-name">{{ t('spaceLayer.3') }}</span></button>
      <button
        v-if="!fabDocked"
        type="button"
        class="space-tuck"
        title="收到边签"
        aria-label="把空间钮收到左边"
        @click="tuckFab"
      >‹</button>
    </div>

    <SpacePanel v-if="panelOpen" />
  </div>
</template>

<style scoped>
.space-layer {
  pointer-events: none;
}
.space-layer :deep(.win),
.space-entry {
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

.space-entry {
  position: fixed;
  left: 12px;
  bottom: 56px;
  z-index: 140;
  display: flex;
  align-items: center;
  gap: 4px;
}

.space-fab {
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

.space-tuck {
  width: 22px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 1000px;
  background: rgba(var(--bg-app-rgb), 0.92);
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1;
}

.space-entry.docked {
  left: 0;
  bottom: 96px;
  gap: 0;
}

.space-fab.docked {
  width: 36px;
  height: 96px;
  padding: 10px 0;
  border-radius: 0 10px 10px 0;
  border-left: none;
  border-right: 2px solid #e51520;
  box-shadow: none;
  display: grid;
  place-items: center;
}

.space-fab.docked .space-fab-name {
  writing-mode: vertical-rl;
  letter-spacing: 0.18em;
  font-family: var(--font-serif);
}

@media (max-width: 430px) {
  .space-entry {
    left: 8px;
    bottom: 16px;
  }
  .space-entry.docked {
    left: 0;
    bottom: 88px;
  }
}
</style>
