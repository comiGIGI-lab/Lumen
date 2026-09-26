<script setup>
/**
 * TopNav —— 右上常驻横排：学习方案生成 / 知识库 / 文档导入 / 课程问答 / 自习空间 / 更多
 * 欢迎层与工具页共用。更多：个人空间、AI 模型设置、历史、日志。
 * 不恢复「原型」。
 */
import { onBeforeUnmount, ref } from 'vue'
import { useSpace } from '@/composables/useSpace'
import { useTheme } from '@/composables/useTheme'
import { useI18n } from '@/i18n'

const props = defineProps({
  current: { type: String, default: 'course' },
  needsKey: { type: Boolean, default: false },
})

const emit = defineEmits([
  'go-course',
  'open-knowledge',
  'open-import',
  'open-chat',
  'open-wrongbook',
  'open-mindmap',
  'open-study',
  'open-progress',
  'open-settings',
  'open-history',
  'open-trace',
])

const openMore = ref(false)
const { panelOpen } = useSpace()
const { isDark, toggle: toggleTheme } = useTheme()
const { t, isEn, toggle: toggleLang } = useI18n()

function pick(action) {
  openMore.value = false
  emit(action)
}

function openSpace() {
  openMore.value = false
  panelOpen.value = true
}

function onDoc(e) {
  if (!openMore.value) return
  if (e.target && !e.target.closest?.('.more-wrap')) openMore.value = false
}

if (typeof window !== 'undefined') {
  window.addEventListener('click', onDoc)
}
onBeforeUnmount(() => {
  if (typeof window !== 'undefined') window.removeEventListener('click', onDoc)
})
</script>

<template>
  <nav class="top-nav" :aria-label="t('topNav.1')">
    <button
      type="button"
      class="nav-link"
      :class="{ on: current === 'course' }"
      @click="emit('go-course')"
    >{{ t('nav.course') }}</button>
    <button
      type="button"
      class="nav-link"
      :class="{ on: current === 'knowledge' }"
      @click="emit('open-knowledge')"
    >{{ t('nav.knowledge') }}</button>
    <button
      type="button"
      class="nav-link"
      :class="{ on: current === 'import' }"
      @click="emit('open-import')"
    >{{ t('nav.import') }}</button>
    <button
      type="button"
      class="nav-link"
      :class="{ on: current === 'chat' }"
      @click="emit('open-chat')"
    >{{ t('nav.chat') }}</button>
    <button
      type="button"
      class="nav-link"
      :class="{ on: current === 'wrongbook' }"
      @click="emit('open-wrongbook')"
    >{{ t('nav.wrongbook') }}</button>
    <button
      type="button"
      class="nav-link"
      :class="{ on: current === 'study' }"
      @click="emit('open-study')"
    >{{ t('nav.study') }}</button>
    <div class="more-wrap">
      <button
        type="button"
        class="nav-link more-btn"
        :class="{ on: openMore, 'needs-key': needsKey }"
        :title="t('topNav.2')"
        aria-haspopup="true"
        :aria-expanded="openMore"
        @click.stop="openMore = !openMore"
      >{{ t('topNav.3') }}</button>
      <div v-if="openMore" class="more-menu" role="menu">
        <button type="button" role="menuitem" @click="openSpace">{{ t('nav.space') }}</button>
        <button type="button" role="menuitem" @click="toggleTheme">
          {{ isDark ? t('nav.toLight') : t('nav.toDark') }}
          <em>{{ isDark ? '☀' : '☾' }}</em>
        </button>
        <button type="button" role="menuitem" @click="toggleLang">
          {{ isEn ? t('nav.toZh') : t('nav.toEn') }}
          <em>⇄</em>
        </button>
        <button type="button" role="menuitem" @click="pick('open-settings')">
          {{ t('nav.settings') }}
          <em v-if="needsKey">{{ t('nav.needKey') }}</em>
        </button>
        <button type="button" role="menuitem" @click="pick('open-mindmap')">{{ t('nav.mindmap') }}</button>
        <button type="button" role="menuitem" @click="pick('open-progress')">{{ t('nav.progress') }}</button>
        <button type="button" role="menuitem" @click="pick('open-history')">{{ t('nav.history') }}</button>
        <button type="button" role="menuitem" @click="pick('open-trace')">{{ t('topNav.4') }}</button>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.top-nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  min-width: 0;
}

.nav-link {
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-primary);
  border-radius: 1000px;
  padding: 7px 14px;
  font-size: 12.5px;
  white-space: nowrap;
}

.nav-link.on {
  border-color: #e51520;
  color: #e51520;
}

.nav-link.needs-key {
  border-color: #e51520;
  color: #b45309;
}

.more-wrap {
  position: relative;
}

.more-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 176px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 6px;
  z-index: 150;
}

.more-menu button {
  display: flex;
  width: 100%;
  text-align: left;
  border: none;
  background: transparent;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-primary);
}

.more-menu button:hover {
  background: var(--bg-soft);
}

.more-menu em {
  font-style: normal;
  margin-left: 6px;
  color: #e51520;
  font-size: 11px;
}

@media (max-width: 430px) {
  .top-nav {
    width: 100%;
  }
  .nav-link {
    padding: 6px 10px;
    font-size: 12px;
  }
}
</style>
