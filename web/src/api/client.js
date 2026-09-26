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

/**
 * 登录 token —— 管理员身份靠它带到后端（X-Auth-Token 头）。
 * 存在 localStorage，刷新不掉线；校验由后端做，前端只负责携带。
 */
export function authToken() {
  try {
    return localStorage.getItem('zjxt.auth.token') || ''
  } catch (_) {
    return ''
  }
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Id': clientId(),
      'X-Auth-Token': authToken(),
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
  /** 登录。成功返回 {ok, token, username, role}；失败返回 {ok:false, error}。 */
  login(username, password) {
    return request('/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },

  /** 注册。只创建普通账号，成功后直接返回 token（注册即登录）。 */
  register(username, password) {
    return request('/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },

  /** 当前登录用户（未登录时 ok=false）。用来在刷新后校验本地 token 是否还有效。 */
  me() {
    return request('/me')
  },

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

  /**
   * 导出 Word（.docx）。
   * 后端直接回二进制流（不是 JSON），所以这里不走 request()，单独用 fetch 取 blob。
   * 文件名优先用后端 Content-Disposition 里的 filename*（RFC 5987，中文安全）。
   */
  async exportDocx(course, result) {
    const res = await fetch(`${BASE}/export`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Client-Id': clientId(),
      },
      body: JSON.stringify({ course, result, format: 'docx' }),
    })
    if (!res.ok) {
      let msg = `导出失败（${res.status}）`
      try {
        const data = await res.json()
        if (data && data.error) msg = data.error
      } catch (_) {
        /* 后端异常时可能不是 JSON，保留默认文案 */
      }
      throw new Error(msg)
    }
    let filename = `${course || '学习方案'} 学习方案.docx`
    const cd = res.headers.get('Content-Disposition') || ''
    const m = /filename\*=UTF-8''([^;]+)/i.exec(cd)
    if (m) {
      try {
        filename = decodeURIComponent(m[1])
      } catch (_) {
        /* 解码失败就用默认名 */
      }
    }
    return { blob: await res.blob(), filename }
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

  // ---------------- 学习进度 / 学情 ----------------

  /**
   * 勾选或取消大纲 / 计划里的某一项。
   * 索引与方案里 outline / plan 的顺序一一对应（后端按同一顺序生成进度清单）。
   */
  progressDone(course, kind, index, done) {
    return request('/progress/done', {
      method: 'POST',
      body: JSON.stringify({ course, kind, index, done }),
    })
  },

  /** 学情概览：本浏览器名下所有课程的完成度汇总 */
  progressOverview() {
    return request('/progress/overview')
  },

  // ---------------- 错题本 ----------------

  /** 错题列表。course / q / status 都可选（status: unmastered | mastered） */
  wrongBookList({ course = '', q = '', status = '' } = {}) {
    const qs = new URLSearchParams()
    if (course) qs.set('course', course)
    if (q) qs.set('q', q)
    if (status) qs.set('status', status)
    const tail = qs.toString()
    return request(`/wrongbook${tail ? '?' + tail : ''}`)
  },

  /** 新增一道错题 */
  wrongBookAdd(payload) {
    return request('/wrongbook', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  /** 修改一道错题（传哪些字段就改哪些） */
  wrongBookUpdate(id, fields) {
    return request(`/wrongbook/${id}`, {
      method: 'POST',
      body: JSON.stringify(fields),
    })
  },

  /** 记一次复习；mastered 传 true/false 时顺带更新掌握状态 */
  wrongBookReview(id, mastered = null) {
    const body = { review: true }
    if (mastered !== null) body.mastered = mastered
    return request(`/wrongbook/${id}`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  /** 删除一道错题 */
  wrongBookDelete(id) {
    return request(`/wrongbook/${id}`, { method: 'DELETE' })
  },

  // ---------------- 思维导图 ----------------

  /** 已保存的导图列表（只给课程 / 更新时间 / 节点数） */
  mindmapList() {
    return request('/mindmap')
  },

  /** 取某门课的导图 */
  mindmapGet(course) {
    return request(`/mindmap/${encodeURIComponent(course)}`)
  },

  /** 覆盖保存某门课的导图；nodes 是扁平数组 [{id, parent, text}] */
  mindmapSave(course, nodes) {
    return request('/mindmap', {
      method: 'POST',
      body: JSON.stringify({ course, nodes }),
    })
  },

  /** 删除某门课的导图 */
  mindmapDelete(course) {
    return request(`/mindmap/${encodeURIComponent(course)}`, { method: 'DELETE' })
  },

  // ---------------- 语音转写 ----------------

  /**
   * 语音转写能力探测。
   * 引擎/模型没装好时（例如换服务器忘了搬模型），这里就能拿到原因，
   * 界面可以提前置灰并说明怎么修，而不是让用户白录一遍再失败。
   */
  asrStatus() {
    return request('/asr')
  },

  /**
   * 上传 16k 单声道 16bit PCM（Int16Array 或其 ArrayBuffer）做**离线**转写。
   *
   * ⚠️ 刻意不复用 request()，两个原因：
   *   1. request() 强制 `Content-Type: application/json`，而这里发的是原始二进制；
   *   2. 8 分钟音频约 15MB，要用 XHR 才能拿到真实上传进度。
   *
   * 采样率转换在调用方完成（见 utils/audio.js 的 decodeToPcm16k）——
   * 服务器没装 ffmpeg，也不打算装。
   *
   * @returns {Promise<{ok:boolean, text:string, duration:number, elapsed:number, rtf:number}>}
   */
  asrTranscribe(pcm, { onProgress } = {}) {
    return new Promise((resolve, reject) => {
      const buf = pcm instanceof ArrayBuffer ? pcm : pcm.buffer
      if (!buf || !buf.byteLength) {
        reject(new Error('没有音频数据'))
        return
      }
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${BASE}/asr`)
      xhr.setRequestHeader('Content-Type', 'application/octet-stream')
      xhr.setRequestHeader('X-Client-Id', clientId())
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
        if (xhr.status >= 200 && xhr.status < 300 && data.ok !== false) {
          resolve(data)
        } else {
          reject(new Error(data.error || `转写失败（HTTP ${xhr.status}）`))
        }
      }
      xhr.onerror = () => reject(new Error('网络错误，音频没传上去'))
      xhr.ontimeout = () => reject(new Error('转写超时，请换一段更短的音频'))
      // 服务器实测约 10 倍实时（8 分钟音频 ≈ 50 秒），给足余量
      xhr.timeout = 420000
      xhr.send(buf)
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
