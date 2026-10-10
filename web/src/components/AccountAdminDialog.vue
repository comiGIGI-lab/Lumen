<script setup>
/**
 * AccountAdminDialog —— 管理员账号管理
 *
 * 后端能力早就有了（GET/POST /api/accounts，仅管理员），这里补的是界面：
 * 用户列表 / 创建账号 / 提拔降级 / 重置密码 / 删除。
 *
 * ⚠️ 前端只负责显示，接口的权限校验在服务端（_require_admin）。
 * 重置密码 / 删除用浏览器原生 prompt / confirm —— 管员工具求快求直给，
 * 不为低频操作堆一套弹窗表单。
 */
import { onMounted, ref } from 'vue'
import ModalDialog from './ModalDialog.vue'
import { useI18n } from '@/i18n'
import { api } from '@/api/client'

const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])

const { t } = useI18n()

const users = ref([])
const loading = ref(false)
const err = ref('')
const okMsg = ref('')

// 创建账号的小表单
const newName = ref('')
const newPw = ref('')
const newRole = ref('user')
const busy = ref(false)

async function refresh() {
  loading.value = true
  err.value = ''
  const r = await api.accountsList()
  loading.value = false
  if (!r || !r.ok) {
    err.value = (r && r.error) || '读取失败'
    return
  }
  users.value = r.users || []
}

onMounted(refresh)

function flash(msg) {
  okMsg.value = msg
  err.value = ''
  setTimeout(() => { okMsg.value = '' }, 2500)
}

async function act(payload, doneMsg) {
  busy.value = true
  const r = await api.accountAction(payload)
  busy.value = false
  if (!r || !r.ok) {
    err.value = (r && r.error) || '操作失败'
    return false
  }
  users.value = (r.users && r.users.length ? r.users : users.value)
  await refresh()
  if (doneMsg) flash(doneMsg)
  return true
}

async function create() {
  if (busy.value) return
  err.value = ''
  const name = newName.value.trim()
  if (!name || !newPw.value) {
    err.value = t('auth.needBoth')
    return
  }
  const okDone = await act(
    { action: 'create', username: name, password: newPw.value, role: newRole.value },
    t('auth.createAccount'))
  if (okDone) {
    newName.value = ''
    newPw.value = ''
    newRole.value = 'user'
  }
}

async function toggleRole(u) {
  const target = u.role === 'admin' ? 'user' : 'admin'
  await act(
    { action: 'role', username: u.username, role: target },
    target === 'admin' ? t('auth.toAdmin') : t('auth.toUser'))
}

async function resetPw(u) {
  const pw = window.prompt(t('auth.resetPwPrompt').replace('{name}', u.username) || '')
  if (!pw) return
  await act({ action: 'password', username: u.username, password: pw }, t('auth.resetPw'))
}

async function del(u) {
  if (!window.confirm((t('auth.confirmDel') || '').replace('{name}', u.username))) return
  await act({ action: 'delete', username: u.username }, t('auth.del'))
}
</script>

<template>
  <ModalDialog :open="props.open" :title="''" width="560px" @close="emit('close')">
    <div class="adm">
      <h2 class="h1">{{ t('auth.manage') }}</h2>
      <p class="sub">{{ t('auth.manageSub') }}</p>

      <!-- 创建账号 -->
      <form class="create" @submit.prevent="create">
        <input v-model="newName" class="ctl" type="text" :placeholder="t('auth.newUsernamePlaceholder')" />
        <input v-model="newPw" class="ctl" type="password" autocomplete="new-password"
               :placeholder="t('auth.newPasswordPlaceholder')" />
        <select v-model="newRole" class="ctl sel">
          <option value="user">{{ t('auth.roleUser') }}</option>
          <option value="admin">{{ t('auth.roleAdmin') }}</option>
        </select>
        <button type="submit" class="go" :disabled="busy">{{ t('auth.createAccount') }}</button>
      </form>

      <p v-if="err" class="err">{{ err }}</p>
      <p v-if="okMsg" class="ok">{{ okMsg }}</p>

      <!-- 用户列表 -->
      <div class="list">
        <p v-if="!loading && !users.length" class="empty">{{ t('auth.empty') }}</p>
        <div v-for="u in users" :key="u.username" class="row">
          <span class="name">{{ u.username }}</span>
          <span class="badge" :class="{ admin: u.role === 'admin' }">
            {{ u.role === 'admin' ? t('auth.roleAdmin') : t('auth.roleUser') }}
          </span>
          <span class="ops">
            <button type="button" class="mini" :disabled="busy" @click="toggleRole(u)">
              {{ u.role === 'admin' ? t('auth.toUser') : t('auth.toAdmin') }}
            </button>
            <button type="button" class="mini" :disabled="busy" @click="resetPw(u)">
              {{ t('auth.resetPw') }}
            </button>
            <button type="button" class="mini danger" :disabled="busy" @click="del(u)">
              {{ t('auth.del') }}
            </button>
          </span>
        </div>
      </div>
    </div>
  </ModalDialog>
</template>

<style scoped>
.adm {
  padding: 4px 8px 2px;
}
.h1 {
  margin: 6px 0 8px;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.3px;
  color: var(--text, #191919);
  text-align: center;
}
.sub {
  margin: 0 0 18px;
  font-size: 13px;
  color: var(--text-3, #8b8378);
  text-align: center;
  line-height: 1.6;
}

/* ---- 创建表单：一行放下 ---- */
.create {
  display: flex;
  gap: 8px;
}
.ctl {
  flex: 1 1 auto;
  min-width: 0;
  height: 42px;
  border: 1px solid var(--border, #e4ded5);
  border-radius: 10px;
  background: var(--bg-elev, #fff);
  padding: 0 12px;
  font-size: 14px;
  color: var(--text, #191919);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.ctl:focus {
  border-color: var(--brand, #e51520);
  box-shadow: 0 0 0 3px rgba(229, 21, 32, 0.1);
}
.sel {
  flex: 0 0 110px;
}
.go {
  flex: 0 0 auto;
  height: 42px;
  padding: 0 16px;
  border: 0;
  border-radius: 10px;
  background: var(--brand, #e51520);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
.go:disabled {
  opacity: 0.6;
  cursor: default;
}

.err {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--danger, #c4101a);
}
.ok {
  margin: 10px 0 0;
  font-size: 13px;
  color: #1a7f37;
}

/* ---- 列表 ---- */
.list {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
}
.empty {
  text-align: center;
  font-size: 13px;
  color: var(--text-3, #8b8378);
  padding: 18px 0;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 4px;
  border-bottom: 1px solid var(--border, #e4ded5);
}
.row:last-child {
  border-bottom: 0;
}
.name {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text, #191919);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.badge {
  flex: 0 0 auto;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--bg-soft, #f2ede6);
  color: var(--text-2, #6b645c);
}
.badge.admin {
  background: rgba(229, 21, 32, 0.1);
  color: #c4101a;
}
.ops {
  flex: 0 0 auto;
  display: flex;
  gap: 6px;
}
.mini {
  border: 1px solid var(--border, #e4ded5);
  background: transparent;
  border-radius: 8px;
  padding: 5px 10px;
  font-size: 12px;
  color: var(--text-2, #6b645c);
  cursor: pointer;
}
.mini:hover {
  border-color: var(--border-strong, #c8c0b5);
}
.mini.danger:hover {
  border-color: var(--danger, #c4101a);
  color: var(--danger, #c4101a);
}
.mini:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
