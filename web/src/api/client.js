/**
 * study-liu Web · API 客户端
 *
 * 所有请求都走 /api 前缀，由 vite.config.js 的代理转发到 Python 后端
 * （server/api_server.py）。后端复用的是 study-liu 桌面版真实的
 * core / agents / tools 模块，前端不重复实现任何业务逻辑。
 */

const BASE = import.meta.env.VITE_API_BASE || '/api'

/**
 * 浏览器身份标识 —— 历史记录按浏览器隔离。
 * 首次访问生成并写入 localStorage，之后每次请求通过
 * X-Client-Id 头（SSE 走 client_id 查询参数）告诉后端"我是谁"，
 * 避免所有人共享同一个 progress.json 里的历史。
 */
export function clientId() {
  let id = localStorage.getItem('study-liu-client-id')
  if (!id) {
    id = 'c-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
    localStorage.setItem('study-liu-client-id', id)
  }
  return id
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Id': clientId(),
      ...(options.headers || {}),
    },
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

  // ---------------- 知识库 ----------------

  /**
   * 知识库条目列表。
   * 带 q 时后端走「分词 + 字段加权 + 覆盖率」打分检索，
   * 返回的条目会多出 _score（分数）与 _match（命中明细），按分数降序。
   */
  knowledgeList(q = '', topK = 50) {
    const qs = new URLSearchParams()
    if (q) qs.set('q', q)
    if (topK) qs.set('top_k', String(topK))
    const tail = qs.toString()
    return request(`/knowledge${tail ? '?' + tail : ''}`)
  },

  /** 知识库能力：支持哪些扩展名、PDF 能否解析、图片识图是否可用 */
  knowledgeCapabilities() {
    return request('/knowledge/capabilities')
  },

  /**
   * 新建一条知识库笔记（正文可留空，作为待导入材料的容器）。
   * tags 可传数组或逗号分隔的字符串。
   */
  knowledgeCreate({ title = '', content = '', tags = [] } = {}) {
    return request('/knowledge', {
      method: 'POST',
      body: JSON.stringify({ title, content, tags }),
    })
  },

  /** 删除一条知识库笔记 */
  knowledgeDelete(id) {
    return request(`/knowledge/${id}`, { method: 'DELETE' })
  },

  /**
   * 上传文件导入知识库（multipart）。
   *
   * ⚠️ 这里刻意**不复用 request()**，两个原因：
   *   1. request() 会强制带 `Content-Type: application/json`，
   *      而 multipart 必须让浏览器自己写 boundary —— 写死了后端就解析不出文件；
   *   2. 要用 XMLHttpRequest 才能拿到**真实的**上传进度（fetch 不支持）。
   *
   * @param {File[]} files 选中的文件
   * @param {object} opts
   *   tags       —— 附加标签数组
   *   title      —— 归入的笔记名；传了就把这批文件归到同一个笔记下
   *   onProgress —— (0~1) 上传进度回调
   * @returns {Promise<object>} 后端返回 {ok, imported, failed, results, total}
   */
  knowledgeImport(files, { tags = [], title = '', onProgress } = {}) {
    return new Promise((resolve, reject) => {
      const list = Array.from(files || [])
      if (!list.length) {
        reject(new Error('没有选择文件'))
        return
      }
      const form = new FormData()
      list.forEach((f) => form.append('file', f, f.name))
      if (tags.length) form.append('tags', tags.join(','))
      if (title) form.append('title', title)

      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${BASE}/knowledge/import`)
      xhr.setRequestHeader('X-Client-Id', clientId()) // 不设 Content-Type，交给浏览器
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total)
      }
      xhr.onload = () => {
        let data = {}
        try {
          data = JSON.parse(xhr.responseText)
        } catch (_) {
          /* 后端异常时可能不是 JSON */
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data)
        } else {
          reject(new Error(data.error || `导入失败（HTTP ${xhr.status}）`))
        }
      }
      xhr.onerror = () => reject(new Error('网络错误，上传失败'))
      xhr.ontimeout = () => reject(new Error('上传超时'))
      xhr.timeout = 300000 // 大文件 + 模型识图可能较慢
      xhr.send(form)
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
    client_id: clientId(), // EventSource 无法自定义请求头，走查询参数
  })
  return `${BASE}/plan/stream?${qs.toString()}`
}
