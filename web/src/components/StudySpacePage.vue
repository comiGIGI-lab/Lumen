<script setup>
/**
 * StudySpacePage —— 自习空间主页
 * 场景视频是页面本体，计时 / 待办 / 日期倒数日是固定模块。
 * 复用 StudyDock、TodoDock、DateDock，状态走 useStudyTimer / useSpace。
 */
import StudyDock from './StudyDock.vue'
import TodoDock from './TodoDock.vue'
import DateDock from './DateDock.vue'
import SceneBackdrop from './SceneBackdrop.vue'
import { useStudyTimer } from '@/composables/useStudyTimer'

const { scene } = useStudyTimer()
</script>

<template>
  <div class="study-space">
    <div class="stage" aria-hidden="true">
      <SceneBackdrop :scene="scene" />
    </div>
    <div class="mods">
      <section class="mod">
        <h2>自习计时</h2>
        <StudyDock />
      </section>
      <section class="mod">
        <h2>待办事项</h2>
        <TodoDock />
      </section>
      <section class="mod">
        <h2>日期与倒数日</h2>
        <DateDock />
      </section>
    </div>
  </div>
</template>

<style scoped>
.study-space {
  position: relative;
  min-height: calc(100vh - 120px);
  isolation: isolate;
}
.stage {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}
.mods {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
  grid-template-areas:
    'timer todo'
    'timer date';
  gap: 14px;
  align-items: start;
  max-width: 980px;
}
.mod {
  background: rgba(251, 249, 246, 0.92);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 12px 14px 14px;
  box-shadow: var(--shadow-btn);
  backdrop-filter: blur(10px);
}
.mod:nth-child(1) { grid-area: timer; }
.mod:nth-child(2) { grid-area: todo; }
.mod:nth-child(3) { grid-area: date; }
h2 {
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 400;
  letter-spacing: 0.08em;
  margin: 0 0 10px;
  color: var(--text-primary);
}
@media (max-width: 860px) {
  .mods {
    grid-template-columns: 1fr;
    grid-template-areas: none;
  }
  .mod:nth-child(1),
  .mod:nth-child(2),
  .mod:nth-child(3) {
    grid-area: auto;
  }
}
</style>
