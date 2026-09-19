/**
 * study-liu Web · API 客户端
 *
 * 所有请求都走 /api 前缀，由 vite.config.js 的代理转发到 Python 后端
 * （server/api_server.py）。后端复用的是 study-liu 桌面版真实的
 * core / agents / tools 模块，前端不重复实现任何业务逻辑。
 */

const BASE = import.meta.env.VITE_API_BASE || '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let msg = `请求失败（${res.status}）`
    try {
      const data = await res.json()
      if (data && data.error) msg = data.error
    } catch (_) {
      /* 忽略解析失败 */
    }
    throw new Error(msg)
  }
  return res.json()
}

export const api = {
  /** 启动元信息：运行模式 / 用户画像 / 可选项 / 历史 */
  bootstrap() {
    return request('/bootstrap')
  },

  /** 当前运行模式 */
  mode() {
    return request('/mode')
  },

  /** 保存用户画像 */
  saveProfile(profile) {
    return request('/profile', {
      method: 'POST',
      body: JSON.stringify(profile),
    })
  },

  /** 生成方案（非流式，SSE 不可用时的兜底） */
  generatePlan(course, profile, useCache = true) {
    return request('/plan', {
      method: 'POST',
      body: JSON.stringify({ course, profile, use_cache: useCache }),
    })
  },

  /** 课程问答（先查知识库，未命中再调大模型） */
  chat(question, history = [], courseContext = '') {
    return request('/chat', {
      method: 'POST',
      body: JSON.stringify({
        question,
        history,
        course_context: courseContext,
      }),
    })
  },

  /** 日志回放 */
  trace(limit = 150) {
    return request(`/trace?limit=${limit}`)
  },

  /** 历史记录列表 */
  history() {
    return request('/history')
  },

  /** 读取某课程已保存的方案 */
  historyDetail(course) {
    return request(`/history/${encodeURIComponent(course)}`)
  },

  /** 导出 Markdown 文本 */
  exportMarkdown(course, result) {
    return request('/export', {
      method: 'POST',
      body: JSON.stringify({ course, result }),
    })
  },

  /** 切换 Mock / LLM 模式 */
  saveSettings(payload) {
    return request('/settings', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  /** 测试 LLM 连接（不保存配置） */
  testSettings(payload) {
    return request('/settings/test', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  /** 清空结果缓存 */
  clearCache(course = null) {
    return request('/cache/clear', {
      method: 'POST',
      body: JSON.stringify({ course }),
    })
  },
}

/**
 * 构造「生成方案」SSE 地址。
 * 用 GET + query 是为了能用浏览器原生 EventSource（它只支持 GET）。
 */
export function planStreamUrl(course, profile = {}, useCache = true) {
  const qs = new URLSearchParams({
    course,
    level: profile.level || '入门',
    daily_hours: profile.daily_hours || '2h',
    goal: profile.goal || '兴趣',
    deadline: profile.deadline || '',
    use_cache: useCache ? '1' : '0',
  })
  return `${BASE}/plan/stream?${qs.toString()}`
}
