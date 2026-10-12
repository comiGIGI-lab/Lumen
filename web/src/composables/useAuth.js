/**
 * useAuth —— 登录态与角色
 *
 * ## 为什么要有
 *
 * 知识库里的材料多人共用，删除不可逆。加一层账号：
 *   - 普通账号：看 / 导入 / 提问
 *   - 管理员账号：**额外**能删知识库内容
 *
 * ## 状态放哪
 *
 * token 存 localStorage（`zjxt.auth.token`），刷新不掉线。
 * 首次加载时用 `/api/me` 校验一次：token 可能已过期、账号可能已被删，
 * 不能只看本地有没有值就当成已登录。
 *
 * ## 角色判断只在前端做「显示与否」
 *
 * 前端隐藏删除按钮只是体验，真正的拦截在服务端（`DELETE /api/knowledge/<id>`
 * 会校验 token 的角色）。**不要**因为前端藏了按钮就以为安全了。
 */
import { computed, ref } from 'vue'
import { api } from '@/api/client'

const TOKEN_KEY = 'zjxt.auth.token'
const user = ref({ username: '', role: '' })
/** 每次写入或清除 token 加一。学伴据此换成当前身份的存档。 */
const authEpoch = ref(0)
const authEnabled = ref(false)
const ready = ref(false)
let inited = false

function readToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch (_) {
    return ''
  }
}

function writeToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
    authEpoch.value += 1
  } catch (_) {
    /* 隐私模式下写不了，本次会话仍然可用 */
  }
}

export function useAuth() {
  const isLoggedIn = computed(() => !!user.value.username)
  const isAdmin = computed(() => user.value.role === 'admin')

  /** 用本地 token 问一次后端「我是谁」。token 失效就清掉。 */
  async function refresh() {
    const token = readToken()
    if (!token) {
      user.value = { username: '', role: '' }
      ready.value = true
      return
    }
    try {
      const r = await api.me()
      if (r && r.ok) {
        user.value = { username: r.username, role: r.role }
        authEnabled.value = !!r.auth_enabled
      } else {
        writeToken('')
        user.value = { username: '', role: '' }
        authEnabled.value = !!(r && r.auth_enabled)
      }
    } catch (_) {
      // 后端没起来时不阻塞界面，保留 token 等下次
      user.value = { username: '', role: '' }
    }
    ready.value = true
  }

  async function login(username, password) {
    const r = await api.login(username, password)
    if (!r || !r.ok) {
      return { ok: false, error: (r && r.error) || '登录失败' }
    }
    writeToken(r.token)
    user.value = { username: r.username, role: r.role }
    authEnabled.value = true
    return { ok: true, role: r.role }
  }

  /** 自助注册。只建普通账号（后端限制），成功后等同于登录。 */
  async function register(username, password) {
    const r = await api.register(username, password)
    if (!r || !r.ok) {
      return { ok: false, error: (r && r.error) || '注册失败' }
    }
    writeToken(r.token)
    user.value = { username: r.username, role: r.role }
    authEnabled.value = true
    return { ok: true, role: r.role }
  }

  function logout() {
    writeToken('')
    user.value = { username: '', role: '' }
  }

  if (!inited && typeof window !== 'undefined') {
    inited = true
    refresh()
  }

  return { user, isLoggedIn, isAdmin, authEnabled, ready, authEpoch, login, register, logout, refresh }
}
