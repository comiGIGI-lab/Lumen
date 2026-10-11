<script setup>
/**
 * LoginDialog —— 账号登录 / 注册（视觉参照用户给的设计稿）
 *
 * 结构：大标题 + 副标题 + 图标输入框 + 全宽主按钮 + 底部切换链接。
 * 参考稿用的是蓝色，这里沿用本站品牌红保持一致；要完全照搬蓝色改一个变量即可。
 *
 * 三态：
 *   signin    账号 + 密码 → 登录
 *   signup    账号 + 密码 + 确认密码 → 注册（后端只建普通账号）
 *   changepw  已登录：原密码 + 新密码 → 自助改密（POST /api/password）
 *
 * 已登录卡片还有「账号管理」入口（仅管理员），打开 AccountAdminDialog。
 *
 * ⚠️ 前端只负责显示，接口的权限校验在服务端。
 */
import { computed, ref, watch } from 'vue'
import ModalDialog from './ModalDialog.vue'
import AccountAdminDialog from './AccountAdminDialog.vue'
import { useI18n } from '@/i18n'
import { useAuth } from '@/composables/useAuth'
import { api } from '@/api/client'

const props = defineProps({
  open: { type: Boolean, default: false },
  /** 打开时的初始模式：'signin' | 'signup' */
  initialMode: { type: String, default: 'signin' },
})
const emit = defineEmits(['close', 'changed'])

const { t } = useI18n()
const { user, isLoggedIn, isAdmin, login, register, logout } = useAuth()

// 初始模式直接取值，不能只放在 watch 里 —— SSR 首渲染时 open 已经是 true，
// watch 不会触发，mode 会停在默认值（注册态渲染成登录态）
const mode = ref(props.initialMode === 'signup' ? 'signup' : 'signin')
const username = ref('')
const password = ref('')
const confirm = ref('')
const showPw = ref(false)
const busy = ref(false)
const err = ref('')
const okMsg = ref('')

// 管理员「账号管理」子弹窗
const showAdmin = ref(false)

const isSignup = computed(() => mode.value === 'signup')
const isChangePw = computed(() => mode.value === 'changepw')

watch(
  () => props.open,
  (v) => {
    if (v) {
      mode.value = props.initialMode === 'signup' ? 'signup' : 'signin'
      err.value = ''
      okMsg.value = ''
      password.value = ''
      confirm.value = ''
      showPw.value = false
    }
  },
)

function switchMode() {
  mode.value = isSignup.value ? 'signin' : 'signup'
  err.value = ''
  confirm.value = ''
}

function gotoChangePw() {
  mode.value = 'changepw'
  err.value = ''
  okMsg.value = ''
  password.value = ''
  confirm.value = ''
}

function backToCard() {
  mode.value = 'signin'
  err.value = ''
  okMsg.value = ''
  password.value = ''
  confirm.value = ''
}

async function submitChangePw() {
  if (busy.value) return
  err.value = ''
  okMsg.value = ''
  if (!password.value || !confirm.value) {
    err.value = t('auth.needBoth')
    return
  }
  if (confirm.value.length < 6) {
    err.value = t('auth.changePwShort')
    return
  }
  busy.value = true
  const r = await api.changePassword(password.value, confirm.value)
  busy.value = false
  if (!r || !r.ok) {
    err.value = (r && r.error) || t('auth.failed')
    return
  }
  okMsg.value = t('auth.changePwOk')
  password.value = ''
  confirm.value = ''
}

async function submit() {
  if (busy.value) return
  err.value = ''
  const name = username.value.trim()
  if (!name || !password.value) {
    err.value = t('auth.needBoth')
    return
  }
  if (isSignup.value && password.value !== confirm.value) {
    err.value = t('auth.mismatch')
    return
  }
  busy.value = true
  const r = isSignup.value ? await register(name, password.value) : await login(name, password.value)
  busy.value = false
  if (!r.ok) {
    err.value = r.error || (isSignup.value ? t('auth.signupFailed') : t('auth.failed'))
    return
  }
  password.value = ''
  confirm.value = ''
  emit('changed', r.role)
  emit('close')
}

function doLogout() {
  logout()
  username.value = ''
  password.value = ''
  emit('changed', '')
  emit('close')
}
</script>

<template>
  <ModalDialog :open="props.open" :title="''" width="420px" @close="emit('close')">
    <div class="acc">
      <!-- 已登录：改密表单 -->
      <template v-if="isLoggedIn && isChangePw">
        <h2 class="h1">{{ t('auth.changePw') }}</h2>
        <p class="sub">{{ t('auth.changePwSub') }}</p>
        <form class="fields" @submit.prevent="submitChangePw">
          <div class="field">
            <span class="ico" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                <rect x="4.5" y="10.5" width="15" height="9.5" rx="2.2" />
                <path d="M8.2 10.5V8a3.8 3.8 0 0 1 7.6 0v2.5" stroke-linecap="round" />
              </svg>
            </span>
            <input v-model="password" class="ctl" type="password" autocomplete="current-password"
                   :placeholder="t('auth.oldPwPlaceholder')" />
          </div>
          <div class="field">
            <span class="ico" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                <rect x="4.5" y="10.5" width="15" height="9.5" rx="2.2" />
                <path d="M8.2 10.5V8a3.8 3.8 0 0 1 7.6 0v2.5" stroke-linecap="round" />
              </svg>
            </span>
            <input v-model="confirm" class="ctl" type="password" autocomplete="new-password"
                   :placeholder="t('auth.newPwPlaceholder')" />
          </div>
          <p v-if="err" class="err">{{ err }}</p>
          <p v-if="okMsg" class="okmsg">{{ okMsg }}</p>
          <button type="submit" class="primary" :disabled="busy">
            {{ busy ? t('auth.changing') : t('auth.changePw') }}
          </button>
          <button type="button" class="primary ghost" @click="backToCard">{{ t('auth.back') }}</button>
        </form>
      </template>

      <!-- 已登录：身份卡片 -->
      <template v-else-if="isLoggedIn">
        <h2 class="h1">{{ t('auth.title') }}</h2>
        <p class="sub">{{ t('auth.signedInAs') }}</p>
        <div class="who">
          <span class="who-name">{{ user.username }}</span>
          <span class="who-role" :class="{ admin: isAdmin }">
            {{ isAdmin ? t('auth.roleAdmin') : t('auth.roleUser') }}
          </span>
        </div>
        <p class="hint">{{ isAdmin ? t('auth.adminHint') : t('auth.userHint') }}</p>
        <div class="ops">
          <button type="button" class="primary ghost" @click="gotoChangePw">
            {{ t('auth.changePw') }}
          </button>
          <button v-if="isAdmin" type="button" class="primary ghost" @click="showAdmin = true">
            {{ t('auth.manage') }}
          </button>
        </div>
        <button type="button" class="primary ghost logout" @click="doLogout">{{ t('auth.logout') }}</button>
      </template>

      <!-- 未登录：登录 / 注册 -->
      <template v-else>
        <h2 class="h1">{{ isSignup ? t('auth.signupTitle') : t('auth.title') }}</h2>
        <p class="sub">{{ isSignup ? t('auth.signupSub') : t('auth.signinSub') }}</p>

        <form class="fields" @submit.prevent="submit">
          <!-- 账号 -->
          <div class="field">
            <span class="ico" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                <circle cx="12" cy="8" r="3.6" />
                <path d="M4.8 20c.7-3.7 3.7-5.6 7.2-5.6s6.5 1.9 7.2 5.6" stroke-linecap="round" />
              </svg>
            </span>
            <input
              v-model="username"
              class="ctl"
              type="text"
              autocomplete="username"
              :placeholder="t('auth.usernamePlaceholder')"
            />
          </div>

          <!-- 密码 -->
          <div class="field">
            <span class="ico" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                <rect x="4.5" y="10.5" width="15" height="9.5" rx="2.2" />
                <path d="M8.2 10.5V8a3.8 3.8 0 0 1 7.6 0v2.5" stroke-linecap="round" />
              </svg>
            </span>
            <input
              v-model="password"
              class="ctl"
              :type="showPw ? 'text' : 'password'"
              :autocomplete="isSignup ? 'new-password' : 'current-password'"
              :placeholder="t('auth.passwordPlaceholder')"
            />
            <button type="button" class="eye" :aria-label="t('auth.togglePw')" @click="showPw = !showPw">
              <svg v-if="!showPw" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                <path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12Z" />
                <circle cx="12" cy="12" r="2.8" />
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                <path d="M4 5.5 20 19" stroke-linecap="round" />
                <path d="M9.6 9.7A2.8 2.8 0 0 0 12 14.8c.7 0 1.4-.3 1.9-.8" stroke-linecap="round" />
                <path d="M6.4 7.6C3.9 9.3 2.5 12 2.5 12s3.5 5.5 9.5 5.5c1.5 0 2.8-.4 3.9-1M17.9 15C20 13.4 21.5 12 21.5 12S18 6.5 12 6.5c-.6 0-1.2.1-1.7.2" stroke-linecap="round" />
              </svg>
            </button>
          </div>

          <!-- 注册：确认密码 -->
          <div v-if="isSignup" class="field">
            <span class="ico" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                <rect x="4.5" y="10.5" width="15" height="9.5" rx="2.2" />
                <path d="M8.2 10.5V8a3.8 3.8 0 0 1 7.6 0v2.5" stroke-linecap="round" />
              </svg>
            </span>
            <input
              v-model="confirm"
              class="ctl"
              :type="showPw ? 'text' : 'password'"
              autocomplete="new-password"
              :placeholder="t('auth.confirmPlaceholder')"
            />
          </div>

          <p v-if="err" class="err">{{ err }}</p>

          <button type="submit" class="primary" :disabled="busy">
            {{ busy ? (isSignup ? t('auth.signingUp') : t('auth.loggingIn')) : (isSignup ? t('auth.signup') : t('auth.login')) }}
          </button>
        </form>

        <p class="foot">
          {{ isSignup ? t('auth.haveAccount') : t('auth.noAccount') }}
          <button type="button" class="link" @click="switchMode">
            {{ isSignup ? t('auth.goSignin') : t('auth.goSignup') }}
          </button>
        </p>

        <p class="note">{{ isSignup ? t('auth.signupNote') : t('auth.signinNote') }}</p>
      </template>
    </div>
  </ModalDialog>

  <!-- 管理员账号管理（子弹窗，放在外层弹窗之外避免遮罩叠加错乱） -->
  <AccountAdminDialog :open="showAdmin" @close="showAdmin = false" />
</template>

<style scoped>
.acc {
  padding: 4px 8px 2px;
  text-align: center;
}

/* ---- 标题区 ---- */
.h1 {
  margin: 6px 0 8px;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.3px;
  color: var(--text, #191919);
}
.sub {
  margin: 0 0 22px;
  font-size: 14px;
  color: var(--text-3, #8b8378);
  line-height: 1.6;
}

/* ---- 输入框：左图标 + 输入 +（密码）右眼睛 ---- */
.fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.field {
  position: relative;
  display: flex;
  align-items: center;
  height: 52px;
  border: 1px solid var(--border, #e4ded5);
  border-radius: 10px;
  background: var(--bg-elev, #fff);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.field:focus-within {
  border-color: var(--brand, #e51520);
  box-shadow: 0 0 0 3px rgba(229, 21, 32, 0.1);
}
.ico {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 100%;
  flex: 0 0 46px;
  color: #a49c92;
}
.ico svg {
  width: 19px;
  height: 19px;
}
.ctl {
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
  border: 0;
  outline: none;
  background: transparent;
  font-size: 15px;
  color: var(--text, #191919);
  padding-right: 12px;
}
.ctl::placeholder {
  color: #b6ada2;
}
.eye {
  flex: 0 0 44px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  color: #a49c92;
  cursor: pointer;
}
.eye:hover {
  color: var(--text-2, #6b645c);
}
.eye svg {
  width: 19px;
  height: 19px;
}

/* ---- 错误提示 ---- */
.err {
  margin: 0;
  text-align: left;
  font-size: 13px;
  color: var(--danger, #c4101a);
}
.okmsg {
  margin: 0;
  text-align: left;
  font-size: 13px;
  color: #1a7f37;
}

/* ---- 已登录卡片按钮组 ---- */
.ops {
  display: flex;
  gap: 10px;
  margin-top: 14px;
}
.ops .primary.ghost {
  margin-top: 0;
  flex: 1 1 0;
}
.primary.logout {
  margin-top: 10px;
}

/* ---- 主按钮：全宽 ---- */
.primary {
  width: 100%;
  height: 48px;
  margin-top: 4px;
  border: 0;
  border-radius: 10px;
  background: var(--brand, #e51520);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.15s;
}
.primary:hover:not(:disabled) {
  filter: brightness(1.08);
}
.primary:disabled {
  opacity: 0.6;
  cursor: default;
}
.primary.ghost {
  margin-top: 18px;
  background: transparent;
  border: 1px solid var(--border, #e4ded5);
  color: var(--text-2, #6b645c);
}
.primary.ghost:hover {
  filter: none;
  border-color: var(--border-strong, #c8c0b5);
}

/* ---- 底部切换 ---- */
.foot {
  margin: 18px 0 0;
  font-size: 14px;
  color: var(--text-2, #6b645c);
}
.link {
  border: 0;
  background: transparent;
  padding: 0 2px;
  font-size: 14px;
  font-weight: 600;
  color: var(--brand, #e51520);
  cursor: pointer;
}
.link:hover {
  text-decoration: underline;
}
.note {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-3, #8b8378);
}

/* ---- 已登录身份卡 ---- */
.who {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin: 4px 0 14px;
}
.who-name {
  font-size: 18px;
  font-weight: 600;
}
.who-role {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--bg-soft, #f2ede6);
  color: var(--text-2, #6b645c);
}
.who-role.admin {
  background: rgba(229, 21, 32, 0.1);
  color: #c4101a;
}
.hint {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-3, #8b8378);
}
</style>
