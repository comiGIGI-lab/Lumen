<script setup>
/**
 * ChatPage —— 课程问答独立页
 * 同一份 ChatPanel 全页展示；课程页底部那块问答保留不动。
 * Day5：顶栏加「闯关答题」切换，同一课程上下文喂 QuizPanel（选择题闯关）。
 */
import { onMounted, ref } from 'vue'
import { useI18n } from '@/i18n'
import ChatPanel from './ChatPanel.vue'
import QuizPanel from './QuizPanel.vue'
import { usePet } from '@/composables/usePet'

defineProps({
  courseContext: { type: String, default: '' },
  mode: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['notify', 'go-course'])
const { t } = useI18n()

const { logExp } = usePet()
// 首次进入问答页留一条成长记录（amount=0，遵循 P62 既有规则「问答不加分」）
onMounted(() => {
  logExp('课程问答', 0)
})

/** ask | quiz：问答 / 闯关两种模式共用课程上下文 */
const tab = ref('ask')
</script>

<template>
  <div class="chat-page">
    <div class="bar">
      <div>
        <p class="eyebrow">Ask</p>
        <h2>{{ t('chatPage.1') }}</h2>
        <p class="lead">{{ t('chatPage.2') }}</p>
      </div>
      <div class="bar-right">
        <div class="tabs">
          <button
            type="button"
            class="tab"
            :class="{ on: tab === 'ask' }"
            @click="tab = 'ask'"
          >{{ t('quizPage.tabAsk') }}</button>
          <button
            type="button"
            class="tab"
            :class="{ on: tab === 'quiz' }"
            @click="tab = 'quiz'"
          >{{ t('quizPage.tabQuiz') }}</button>
        </div>
        <button type="button" class="ghost" @click="emit('go-course')">{{ t('chatPage.3') }}</button>
      </div>
    </div>
    <ChatPanel
      v-if="tab === 'ask'"
      :course-context="courseContext"
      :mode="mode"
      @notify="emit('notify', $event)"
    />
    <QuizPanel
      v-else
      :course-context="courseContext"
      @notify="emit('notify', $event)"
    />
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
.bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.bar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.tabs {
  display: flex;
  border: 1px solid var(--border);
  border-radius: 1000px;
  overflow: hidden;
}
.tab {
  border: none;
  background: var(--bg-card);
  color: var(--text-primary);
  padding: 7px 14px;
  font-size: 12.5px;
}
.tab.on {
  background: var(--accent);
  color: #fff;
}
.eyebrow {
  font-family: var(--font-serif);
  font-style: italic;
  letter-spacing: 0.16em;
  color: var(--accent);
  font-size: 13px;
}
h2 {
  font-family: var(--font-serif);
  font-size: 28px;
  font-weight: 400;
  margin-top: 4px;
  letter-spacing: 0.06em;
}
.lead {
  max-width: 40em;
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.7;
}
.ghost {
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-primary);
  border-radius: 1000px;
  padding: 7px 14px;
  font-size: 12.5px;
}
.chat-page :deep(.chat-list) {
  max-height: min(58vh, 560px);
}
@media (max-width: 390px) {
  h2 {
    font-size: 22px;
  }
}
</style>
