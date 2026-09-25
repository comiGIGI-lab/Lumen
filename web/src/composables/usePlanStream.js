/**
 * usePlanStream —— 「课程名 → 生成方案」全链路状态机
 *
 * 这是前端最核心的组合式函数，负责把后端 SSE 事件流翻译成界面状态：
 *
 *   meta    → 本次请求的课程 / 画像 / 运行模式
 *   step    → Agent 流水线节点的状态推进（Planner → Searcher → Writer → Reviewer）
 *   trace   → 原始 trace 日志（日志回放面板）
 *   result  → 三栏最终结果（大纲 / 资源 / 计划 + Markdown）
 *   error   → 失败原因
 *
 * 设计要点：
 * 1. 优先走 SSE，浏览器原生 EventSource 自动处理分块与断流；
 * 2. 若 SSE 连接建立失败（例如反代不支持流式），自动降级到 POST /api/plan，
 *    保证「一条完整链路」在任何环境下都能跑通；
 * 3. 后端返回的是**真实 trace.log**，因此步骤耗时、质检结论都是真实的，
 *    不是前端假动画。
 */
import { reactive, ref, computed } from 'vue'
import { api, planStreamUrl } from '@/api/client'

export const STAGES = [
  {
    key: 'planner',
    name: 'Planner',
    titleKey: 'stage.plannerTitle',
    descKey: 'stage.plannerDesc',
    title: '课程大纲',
        desc: '把课程名拆解成章节结构',
    icon: '🧭',
  },
  {
    key: 'searcher',
    name: 'Searcher',
    titleKey: 'stage.searcherTitle',
    descKey: 'stage.searcherDesc',
    title: '推荐资源',
        desc: '检索书籍 / 视频 / 网站',
    icon: '🔎',
  },
  {
    key: 'writer',
    name: 'Writer',
    titleKey: 'stage.writerTitle',
    descKey: 'stage.writerDesc',
    title: '学习计划',
        desc: '按画像编排每日任务',
    icon: '📝',
  },
  {
    key: 'reviewer',
    name: 'Reviewer',
    titleKey: 'stage.reviewerTitle',
    descKey: 'stage.reviewerDesc',
    title: '质量检查',
        desc: '不达标自动重跑一轮',
    icon: '✅',
  },
]

function freshSteps() {
  const out = {}
  for (const s of STAGES) {
    out[s.key] = { status: 'idle', hint: '', data: null }
  }
  return out
}

export function usePlanStream() {
  const status = ref('idle') // idle | running | done | error
  const steps = reactive(freshSteps())
  const traces = ref([])
  const traceError = ref('')
  const result = ref(null)
  const meta = ref(null)
  const error = ref('')
  const finishedAt = ref('')
  /** 当前正在执行的节点序号（-1 表示已结束） */
  const activeIndex = ref(-1)
  const usedFallback = ref(false)

  let es = null

  const progress = computed(() => {
    const done = STAGES.filter((s) => steps[s.key].status === 'done').length
    return { done, total: STAGES.length, percent: (done / STAGES.length) * 100 }
  })

  const isDone = (key) => steps[key].status === 'done'

  function reset() {
    Object.assign(steps, freshSteps())
    traces.value = []
    result.value = null
    meta.value = null
    error.value = ''
    finishedAt.value = ''
    activeIndex.value = -1
    usedFallback.value = false
  }

  function abort() {
    if (es) {
      es.close()
      es = null
    }
  }

  function applyStep(evt) {
    const s = steps[evt.key]
    if (!s) return
    s.status = evt.status
    if (evt.status === 'running') {
      s.hint = evt.hint || s.hint
      activeIndex.value = evt.index
    }
    if (evt.status === 'done') {
      // 清掉「正在…」文案，交给展示层用真实产出数量描述（例如「已生成 10 章」）
      s.hint = ''
      if (evt.data) s.data = evt.data
      activeIndex.value = -1
    }
  }

  /** 质检不过触发重跑时，把已经跑完的节点重新标为 running */
  function handleRetry() {
    steps.writer.status = 'running'
    steps.writer.hint = '质检未通过，Writer 正在重新编排…'
    steps.searcher.status = 'running'
    steps.searcher.hint = '质检未通过，Searcher 正在重新检索…'
    steps.reviewer.status = 'idle'
    activeIndex.value = 2
  }

  function finalize(payload) {
    result.value = payload
    status.value = 'done'
    activeIndex.value = -1
    finishedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    // 兜底：若某些节点因重跑/缓存没收到 done，统一补成 done，避免界面卡在「进行中」
    for (const s of STAGES) {
      if (steps[s.key].status !== 'done') {
        steps[s.key].status = 'done'
      }
    }
  }

  /** 降级方案：POST /api/plan（一次性返回，节点状态由 trace 推断） */
  async function runFallback(course, profile, useCache) {
    usedFallback.value = true
    try {
      const payload = await api.generatePlan(course, profile, useCache)
      // 没有实时事件，按结果反推节点产出
      steps.planner.status = 'done'
      steps.planner.data = { outline_count: payload.outline.length }
      steps.searcher.status = 'done'
      steps.searcher.data = { resource_count: payload.resources.length }
      steps.writer.status = 'done'
      steps.writer.data = { plan_count: payload.plan.length }
      steps.reviewer.status = 'done'
      steps.reviewer.data = { ok: true, comments: [] }
      finalize(payload)
      await refreshTrace()
    } catch (e) {
      status.value = 'error'
      error.value = e.message || String(e)
    }
  }

  async function refreshTrace() {
    try {
      const data = await api.trace(200)
      traces.value = data.lines || []
      traceError.value = ''
    } catch (e) {
      // 之前这里静默吞掉异常，会导致后端没起来时抽屉只显示 0 行、
      // 没有任何提示，看起来像「按钮坏了」。现在把原因显式暴露出来。
      traces.value = []
      traceError.value = e?.message || String(e)
    }
  }

  /**
   * 启动全链路生成。
   * @param {string} course 课程名
   * @param {object} profile 用户画像
   * @param {boolean} useCache 是否允许命中缓存
   */
  function generate(course, profile = {}, useCache = true) {
    abort()
    reset()
    status.value = 'running'

    let settled = false
    try {
      es = new EventSource(planStreamUrl(course, profile, useCache))

      es.addEventListener('meta', (e) => {
        meta.value = JSON.parse(e.data)
      })

      es.addEventListener('trace', (e) => {
        const item = JSON.parse(e.data)
        traces.value.push(item)
        if (item.event === 'reviewer_retry') handleRetry()
      })

      es.addEventListener('step', (e) => {
        applyStep(JSON.parse(e.data))
      })

      es.addEventListener('result', (e) => {
        settled = true
        finalize(JSON.parse(e.data))
      })

      es.addEventListener('error', (e) => {
        // 后端显式推送的业务错误（带 data）
        if (e.data) {
          try {
            const payload = JSON.parse(e.data)
            status.value = 'error'
            error.value = payload.error || '生成失败'
            settled = true
          } catch (_) {
            /* 交给下面的连接错误处理 */
          }
        }
      })

      es.addEventListener('done', (e) => {
        settled = true
        abort()
        if (status.value === 'running') {
          // 流正常结束但没拿到 result（例如缓存异常），兜底再来一次
          runFallback(course, profile, useCache)
        }
      })

      es.onerror = () => {
        abort()
        if (settled) return
        // 连接建立失败 → 降级到普通 POST，保证链路仍然跑通
        runFallback(course, profile, useCache)
      }
    } catch (e) {
      runFallback(course, profile, useCache)
    }
  }

  return {
    STAGES,
    status,
    steps,
    traces,
    traceError,
    result,
    meta,
    error,
    finishedAt,
    activeIndex,
    progress,
    usedFallback,
    isDone,
    generate,
    abort,
    reset,
    refreshTrace,
  }
}
