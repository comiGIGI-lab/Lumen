<script setup>
/**
 * StudySpacePage —— 自习空间主页
 * 场景视频 / 海报是页面本体。计时、待办、日期走 SpaceLayer 的 FloatWin，
 * 窗标题用 FloatWin 自己的，这里不再套 h2。
 */
import SceneBackdrop from './SceneBackdrop.vue'
import { useStudyTimer } from '@/composables/useStudyTimer'

const { scene } = useStudyTimer()
</script>

<template>
  <div class="study-space">
    <div class="stage" aria-hidden="true">
      <SceneBackdrop :scene="scene" />
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
</style>
