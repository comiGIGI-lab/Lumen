<script setup>
import { useI18n } from '@/i18n'
import { useAuth } from '@/composables/useAuth'
/**
 * AppHeader —— 工具界面顶栏
 * 左：LUMEN + 智识有方；右：常驻横排导航。
 */
import TopNav from './TopNav.vue'

defineProps({
  mode: { type: Object, default: () => ({}) },
  hasResult: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  needsKey: { type: Boolean, default: false },
  current: { type: String, default: 'course' },
})

const emit = defineEmits([
  'export',
  'open-trace',
  'open-login',
  'open-settings',
  'open-history',
  'open-knowledge',
  'open-import',
  'open-transcribe',
  'open-chat',
  'open-wrongbook',
  'open-mindmap',
  'open-study',
  'open-progress',
  'open-manual',
  'go-course',
  'go-home',
])
const { t } = useI18n()
const { user, isLoggedIn, isAdmin } = useAuth()
</script>

<template>
  <header class="hero">
    <div class="hero-inner">
      <div class="hero-left">
        <div class="wordmark" aria-hidden="true">LUMEN</div>
        <div>
          <h1 class="hero-title">{{ t('appHeader.1') }}</h1>
        </div>
      </div>

      <TopNav
        :current="current"
        :needs-key="needsKey"
        @go-course="emit('go-course')"
        @go-home="emit('go-home')"
        @open-knowledge="emit('open-knowledge')"
        @open-import="emit('open-import')"
        @open-transcribe="emit('open-transcribe')"
        @open-chat="emit('open-chat')"
        @open-wrongbook="emit('open-wrongbook')"
        @open-mindmap="emit('open-mindmap')"
        @open-study="emit('open-study')"
        @open-progress="emit('open-progress')"
        @open-manual="emit('open-manual')"
        @open-settings="emit('open-settings')"
        @open-history="emit('open-history')"
        @open-trace="emit('open-trace')"
      />

      <button type="button" class="login-entry" :class="{ admin: isAdmin }" @click="emit('open-login')">
        <span class="le-name">{{ isLoggedIn ? user.username : t('auth.login') }}</span>
        <span v-if="isAdmin" class="le-role">{{ t('auth.roleAdmin') }}</span>
      </button>
    </div>
  </header>
</template>

<style scoped>
/* 登录入口：靠右，不挤压左边的导航 */
.login-entry {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border: 1px solid var(--border, #e4ded5);
  background: transparent;
  border-radius: 999px;
  font-size: 13px;
  color: var(--text-2, #6b645c);
  cursor: pointer;
  white-space: nowrap;
}
.login-entry:hover {
  border-color: var(--border-strong, #c8c0b5);
  color: var(--text, #191919);
}
.login-entry.admin {
  border-color: rgba(229, 21, 32, 0.35);
  color: #c4101a;
}
.le-role {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(229, 21, 32, 0.1);
}

.hero {
  position: relative;
  z-index: 128;
  overflow: visible;
  background: rgba(var(--bg-app-rgb), 0.92);
  color: var(--text-primary);
  border-bottom: 1px solid var(--border);
}

.hero-inner {
  position: relative;
  max-width: 1360px;
  margin: 0 auto;
  padding: 16px 26px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.hero-left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.wordmark {
  font-family: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  font-size: 13px;
  letter-spacing: 0.28em;
  color: #e51520;
  border: 1px solid var(--border);
  padding: 10px 10px 8px;
  line-height: 1;
}

.hero-title {
  font-family: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  font-size: 22px;
  font-weight: 400;
  letter-spacing: 0.08em;
  line-height: 1.2;
}

@media (max-width: 860px) {
  .hero-inner {
    padding: 14px 16px;
  }
  .hero-title {
    font-size: 18px;
  }
}

@media (max-width: 430px) {
  .hero-inner {
    padding: 12px;
    align-items: flex-start;
  }
  .hero-title {
    font-size: 16px;
  }
  .wordmark {
    font-size: 11px;
    padding: 8px 8px 6px;
  }
  .hero-left {
    width: 100%;
  }
}
</style>
