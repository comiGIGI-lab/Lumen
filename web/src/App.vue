<script setup>
/**
 * App.vue —— study-liu Web 主界面
 *
 * 页面即「一条完整链路」的可视化：
 *   ① 输入课程名 + 选画像  →  ② Agent 流水线（Planner→Searcher→Writer→Reviewer）
 *   →  ③ 三栏结果（大纲 / 资源 / 计划）  →  ④ 导出 / 问答 / 日志回放
 *
 * 所有业务逻辑都在后端（复用 study-liu 桌面版的 core / agents / tools），
 * 前端只做展示与交互。
 */
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
const { t } = useI18n()
import AppHeader from './components/AppHeader.vue'
import LoginDialog from './components/LoginDialog.vue'
import WelcomeScreen from './components/WelcomeScreen.vue'
import PipelineStepper from './components/PipelineStepper.vue'
import CourseForm from './components/CourseForm.vue'
import ResultsGrid from './components/ResultsGrid.vue'
import ChatPanel from './components/ChatPanel.vue'
import TraceDrawer from './components/TraceDrawer.vue'
import StatusBar from './components/StatusBar.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import HistoryDialog from './components/HistoryDialog.vue'
import SceneBackdrop from './components/SceneBackdrop.vue'
import SpaceLayer from './components/SpaceLayer.vue'
const KnowledgePage = defineAsyncComponent(() => import('./components/KnowledgePage.vue'))
const ImportPage = defineAsyncComponent(() => import('./components/ImportPage.vue'))
const TranscribePage = defineAsyncComponent(() => import('./components/TranscribePage.vue'))
const ChatPage = defineAsyncComponent(() => import('./components/ChatPage.vue'))
const StudySpacePage = defineAsyncComponent(() => import('./components/StudySpacePage.vue'))
const WrongBookPage = defineAsyncComponent(() => import('./components/WrongBookPage.vue'))
const LearningProgress = defineAsyncComponent(() => import('./components/LearningProgress.vue'))
const MindMapPage = defineAsyncComponent(() => import('./components/MindMapPage.vue'))
const HandbookPage = defineAsyncComponent(() => import('./components/HandbookPage.vue'))
const ExportPreview = defineAsyncComponent(() => import('./components/ExportPreview.vue'))
import { usePlanStream } from './composables/usePlanStream'
import { useSpace } from './composables/useSpace'
import { useStudyTimer } from './composables/useStudyTimer'
import { usePet } from './composables/usePet'
import { keyedStorage } from './composables/ownerTag'
import { useAuth } from './composables/useAuth'
import { usePlanHistory } from './composables/usePlanHistory'
import { api } from './api/client'
import PetGuide from './components/PetGuide.vue'
import PetCompanion from './components/PetCompanion.vue'
import PetProfileDialog from './components/PetProfileDialog.vue'
import TourDialog from './components/TourDialog.vue'

// ---------- 基础状态 ----------
const booted = ref(false)

// ---------- 角色引导 + 首访欢迎层 ----------
// 没选过宠物先出 PetGuide；选完再出 WelcomeScreen。
// 宠物按当前登录账号分档（zjxt.pet.u:用户名 / zjxt.pet.anon），不能只看旧的 zjxt.pet。
// zjxt.welcomed 只归欢迎层。?welcome=1 强制欢迎层，不让引导页挡住拍摄。
function hasPetSaved() {
  try {
    const key = keyedStorage('zjxt.pet')
    let raw = localStorage.getItem(key)
    // 未登录时才认升级前那把不分档的钥匙，避免登成别的账号却读到游客的学伴
    if (!raw && key === 'zjxt.pet.anon') raw = localStorage.getItem('zjxt.pet')
    if (!raw) return false
    const data = JSON.parse(raw)
    return !!(data && data.id)
  } catch (_) {
    return false
  }
}

function shouldShowGuide() {
  try {
    const qs = new URLSearchParams(window.location.search)
    if (qs.get('welcome') === '1') return false
    if (qs.get('course') || qs.get('auto') === '1') return false
    return !hasPetSaved()
  } catch (_) {
    return false
  }
}

function shouldShowWelcome() {
  try {
    const qs = new URLSearchParams(window.location.search)
    if (qs.get('welcome') === '1') return true
    if (qs.get('welcome') === '0') return false
    if (qs.get('course') || qs.get('auto') === '1') return false
    return !localStorage.getItem('zjxt.welcomed')
  } catch (_) {
    return false
  }
}
const showGuide = ref(shouldShowGuide())
const showWelcome = ref(shouldShowWelcome() && !showGuide.value)

const SETTINGS_ONBOARD_KEY = 'zjxt.settings_onboard'
/** 本轮是否正处在初始化这环（决定关窗后要不要接欢迎层） */
const settingsOnboarding = ref(false)

function settingsOnboardDone() {
  try {
    return localStorage.getItem(SETTINGS_ONBOARD_KEY) === 'true'
  } catch (_) {
    return false
  }
}

/** 深链不打扰：演示链接（auto=1）与 ?settings=0 都跳过这一环 */
function skipOnboardSettings() {
  try {
    const qs = new URLSearchParams(window.location.search)
    return qs.get('auto') === '1' || qs.get('settings') === '0'
  } catch (_) {
    return false
  }
}

function enterWelcome() {
  showWelcome.value = shouldShowWelcome()
  // 欢迎层本身不再出右上角 toast：学伴和气泡都在这一层，问候交给气泡。
  if (showWelcome.value) sayWelcome()
}

function isPhone() {
  try {
    return window.matchMedia('(max-width: 430px)').matches
  } catch (_) {
    return false
  }
}

function onGuideDone() {
  showGuide.value = false
  // 手机屏太窄，一进门就盖一层 LLM 设置，顶栏和侧边悬浮窗会把表单挤没。
  // 窄屏直接进欢迎层，模型稍后再从导航打开。
  if (!isPhone() && !settingsOnboardDone() && !skipOnboardSettings()) {
    settingsOnboarding.value = true
    showSettings.value = true
    return
  }
  enterWelcome()
}

function onWelcomeDone() {
  try {
    localStorage.setItem('zjxt.welcomed', '1')
  } catch (_) {
    /* 存不上也不阻塞进入 */
  }
  showWelcome.value = false
  // 欢迎问候只停在欢迎层；进功能页后把这句收掉，别跟到方案页。
  window.dispatchEvent(new CustomEvent('zjxt:pet-hush', { detail: { text: t('pet.welcome') } }))
  // 首访进主应用：宠物已选且没看过指引才弹（每次加载只自动弹一次）
  maybeShowTour()
}

// ---------- 首访新手指引弹窗 ----------
const showTour = ref(false)
let tourAutoShown = false
function maybeShowTour() {
  if (tourAutoShown) return
  if (!hasPetSaved()) return
  if (localStorage.getItem('zjxt.tour_done') === 'true') return
  tourAutoShown = true
  showTour.value = true
}
function onTourClose() {
  showTour.value = false
}
function onTourDismiss() {
  try {
    localStorage.setItem('zjxt.tour_done', 'true')
  } catch (_) {
    /* 存不上也不阻塞 */
  }
  showTour.value = false
}
// 设置里手动触发：重新打开但不写 zjxt.tour_done
function openTour() {
  showTour.value = true
}

// ---------- 宠物档案弹层：点击 PetCompanion 整体触发 ----------
const showProfile = ref(false)
function openProfile() {
  showProfile.value = true
}
function closeProfile() {
  showProfile.value = false
}
// 「更换学伴宠物」按钮：复用现有 SpacePanel 流程（打开个人空间面板）
function onProfileChangePet() {
  showProfile.value = false
  // 与 TopNav / SpaceFAB 同款入口
  spacePanelOpen.value = true
}

const { displayName, logExp, grantStudyExp, grantPlanExp, reloadForOwner } = usePet()
const { authEpoch } = useAuth()
// 登录、注册、退出、token 失效都会加一。换成这一档自己的学伴和经验；没选过就重新选。
// 拍摄用的 ?welcome=1 不改层，避免登录校验把欢迎层盖掉。
watch(authEpoch, () => {
  if (!authEpoch.value) return
  reloadForOwner()
  showProfile.value = false
  try {
    if (new URLSearchParams(window.location.search).get('welcome') === '1') return
  } catch (_) { /* 继续按是否已选决定 */ }
  if (hasPetSaved()) {
    showGuide.value = false
  } else {
    showWelcome.value = false
    showGuide.value = true
  }
})
const { record: recordPlan } = usePlanHistory()

const { applyLayout, panelOpen: spacePanelOpen } = useSpace()
const { scene: activeScene, onSessionComplete: registerSessionComplete } = useStudyTimer()

// 自习完整跑完钩子：grantStudyExp 内部已走 logExp('自习') + logExp('当日首练加成')，并判 bonusDate 去重
registerSessionComplete((minutes) => {
  grantStudyExp(minutes)
})

// 各功能第一次进入时，由学伴身上的气泡说一句。完整说明在使用手册，这里不另弹卡片。
const TIP_KEYS = {
  plan: 'zjxt.tip_plan',
  kb: 'zjxt.tip_kb',
  chat: 'zjxt.tip_chat',
  study: 'zjxt.tip_study',
  space: 'zjxt.tip_space',
  settings: 'zjxt.tip_settings',
}
const tipTimers = { plan: 0, kb: 0, chat: 0, study: 0, space: 0, settings: 0 }
const pendingTips = []
function sayTip(text) {
  window.dispatchEvent(new CustomEvent('zjxt:pet-say', { detail: { text } }))
}
function sayWelcome() {
  const text = t('pet.welcome')
  // 选伴后学伴下一帧才挂上，先进队列等 pet-ready；点「首页」时学伴已在，直接说。
  if (!document.querySelector('.buddy')) pendingTips.push(text)
  else sayTip(text)
}
function flushTips() {
  const queued = pendingTips.splice(0)
  queued.forEach((text) => sayTip(text))
}
if (typeof window !== 'undefined') {
  window.addEventListener('zjxt:pet-ready', flushTips)
}
function maybeTip(id, text) {
  const key = TIP_KEYS[id]
  try {
    if (localStorage.getItem(key) === 'true') return
    localStorage.setItem(key, 'true')
  } catch (_) {
    /* 存不上也不挡住这一次 */
  }
  clearTimeout(tipTimers[id])
  tipTimers[id] = setTimeout(() => {
    if (!document.querySelector('.buddy')) pendingTips.push(text)
    else sayTip(text)
    tipTimers[id] = 0
  }, 800)
}

const appView = ref('course')
const knowledgeSection = ref('notes')
const showLogin = ref(false)

function goHome() {
  // 「首页」= 回到初始欢迎层。
  // 注意不能走 shouldShowWelcome()：它读 localStorage 的 zjxt.welcomed，
  // 访问过一次就永远返回 false，点了会没反应。
  showGuide.value = false
  appView.value = 'course'
  showWelcome.value = true
  sayWelcome()
}

function goCourse() {
  if (showWelcome.value) onWelcomeDone()
  appView.value = 'course'
}

function openSettings() {
  if (showWelcome.value) onWelcomeDone()
  showSettings.value = true
}

function openHistory() {
  if (showWelcome.value) onWelcomeDone()
  showHistory.value = true
}

function openLogs() {
  if (showWelcome.value) onWelcomeDone()
  openTrace()
}

function goKnowledge(section) {
  if (showWelcome.value) onWelcomeDone()
  knowledgeSection.value = ['speech', 'map', 'wrong'].includes(section) ? section : 'notes'
  appView.value = 'knowledge'
}

function goImport() {
  if (showWelcome.value) onWelcomeDone()
  appView.value = 'import'
}

function goTranscribe() {
  goKnowledge('speech')
}

function goChat() {
  if (showWelcome.value) onWelcomeDone()
  appView.value = 'chat'
}

function goStudy() {
  if (showWelcome.value) onWelcomeDone()
  appView.value = 'study'
}

function goWrongBook() {
  goKnowledge('wrong')
}

function goProgress() {
  if (showWelcome.value) onWelcomeDone()
  appView.value = 'progress'
}

function goManual() {
  if (showWelcome.value) onWelcomeDone()
  appView.value = 'manual'
}

function goMindMap() {
  goKnowledge('map')
}

// 欢迎层显示期间锁住 body 滚动，避免底层工具界面跟着滚
function currentSpaceLayout() {
  if (showWelcome.value) return 'welcome'
  if (appView.value === 'study') return 'study'
  return 'app'
}

watch(
  [showWelcome, appView],
  () => {
    document.body.style.overflow = showWelcome.value || showGuide.value ? 'hidden' : ''
    applyLayout(currentSpaceLayout())
  },
  { immediate: true },
)

const mode = ref({})
const options = ref({ levels: [], daily_hours: [], goals: [] })
const suggestedDays = ref(7)
const traceFile = ref('')
const sourceDir = ref('')

const course = ref('')
const profile = ref({ level: '入门', daily_minutes: 60, daily_hours: '1h', goal: '兴趣', goal_other: '', deadline: '' })
const useCache = ref(true)

// ---------- 弹窗 / 抽屉 ----------
const showSettings = ref(false)

/** 收尾：写已做标记 + 关窗；若这轮是初始化就接上欢迎层 */
function finishSettingsOnboard() {
  try {
    localStorage.setItem(SETTINGS_ONBOARD_KEY, 'true')
  } catch (_) {
    /* 存不上也不阻塞 */
  }
  showSettings.value = false
  if (!settingsOnboarding.value) return
  settingsOnboarding.value = false
  enterWelcome()
}

/** 处于 LLM 模式但没配 Key —— 需要主动提示用户去填 */
const needsKey = ref(false)
const showHistory = ref(false)
const showTrace = ref(false)
const showExport = ref(false)
const exportAt = ref('')

watch(activeScene, (s) => {
  document.documentElement.classList.toggle('has-scene', !!s)
}, { immediate: true })

// appView 切换触发：course / knowledge / import / chat / study 各自对应气泡
watch(appView, (v) => {
  if (showGuide.value || showWelcome.value) return
  if (v === 'course') maybeTip('plan', t('tip.plan'))
  else if (v === 'knowledge' || v === 'import') maybeTip('kb', t('tip.kb'))
  else if (v === 'chat') maybeTip('chat', t('tip.chat'))
  else if (v === 'study') maybeTip('study', t('tip.study'))
})
watch(showSettings, (v) => {
  if (!v || showGuide.value || showWelcome.value || settingsOnboarding.value) return
  maybeTip('settings', t('tip.settings'))
})
watch(spacePanelOpen, (v) => {
  if (!v || showGuide.value || showWelcome.value) return
  maybeTip('space', t('tip.space'))
})

// ---------- 状态栏 ----------
const statusText = ref(t('status.ready'))
const statusTone = ref('normal')

// ---------- Toast ----------
const toasts = ref([])
let toastId = 0
function notify(payload) {
  const id = ++toastId
  const item = {
    id,
    type: payload?.type || 'info',
    text: payload?.text || '',
  }
  toasts.value.push(item)
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }, 4200)
}

// ---------- 链路状态机 ----------
const stream = usePlanStream()
const {
  STAGES,
  status,
  steps,
  traces,
  traceError,
  result,
  meta,
  error,
  activeIndex,
  progress,
  usedFallback,
} = stream

const busy = computed(() => status.value === 'running')

// 把链路状态同步到状态栏；方案生成 done 时调 grantPlanExp（内部走 logExp('方案生成', 40)）
watch(status, (v, prev) => {
  if (v === 'running') {
    statusTone.value = 'warn'
  } else if (v === 'error') {
    statusTone.value = 'error'
  } else if (v === 'done') {
    statusTone.value = 'success'
    grantPlanExp()
    const r = result.value
    if (prev === 'running' && r && r.course && r.type !== 'crisis') {
      recordPlan(r.course, profile.value)
    }
  } else {
    statusTone.value = 'normal'
  }
})

watch(
  () => result.value,
  (r) => {
    if (!r) return
    const head = r.from_cache ? '⚡ 命中缓存！' : '✓ 完成！'
    statusText.value = `${head}课程「${r.course}」方案已生成`
    const fromHistory = (r.generated_at || r.created_at || '').trim()
    if (fromHistory) {
      exportAt.value = fromHistory
    } else {
      const d = new Date()
      const p = (n) => String(n).padStart(2, '0')
      exportAt.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
    }
  },
)

watch(error, (e) => {
  if (e) statusText.value = `✗ 生成失败：${e}`
})

// ---------- 初始化 ----------
async function loadBootstrap() {
  try {
    const data = await api.bootstrap()
    mode.value = data.mode || {}
    options.value = data.options || options.value
    profile.value = { ...(data.profile || profile.value) }
    suggestedDays.value = data.suggested_days || 7
    sourceDir.value = data.source_dir || ''
    traceFile.value = data.trace_file || ''
    // label 由前端按语言出（后端返回的 label 固定中文），避免英文状态栏出现「Mock 模式」
    const m = data.mode || {}
    const modeLabel = m.mode === 'llm'
      ? t('status.llmLabel', { m: m.model || '' })
      : t('status.mockLabel')
    statusText.value = t('status.readyDetail', { label: modeLabel })
    // LLM 模式却没 Key：不主动提示的话，用户只能看着「LLM 模式」角标
    // 却不知道去哪儿填自己的 API Key（之前就是这样，体验很差）
    needsKey.value = !!data.mode && data.mode.mode !== 'mock' && !data.mode.has_key
    booted.value = true
  } catch (e) {
    statusTone.value = 'error'
    statusText.value = `后端未启动：${e.message}（请先运行 python server/api_server.py）`
    notify({ type: 'error', text: '呜呜，连不上大脑中枢了，请确认后端 server 启动了吗？' })
  }
}

onMounted(async () => {
  await loadBootstrap()

  // 匿名 LLM 限速命中（后端 429 + code: ANON_LIMIT_*）：提示并引导登录。
  // 登录用户不受限，登录后即可不限次使用全部 AI 功能
  // （见 server/api_server.py 的 _enforce_anon_llm_quota）。
  window.addEventListener('zjxt:anon-limit', (ev) => {
    const detail = ev?.detail || {}
    statusTone.value = 'warn'
    statusText.value =
      detail.message || '今日匿名体验额度已用完，登录后即可不限次使用全部 AI 功能。'
    if (!showLogin.value) showLogin.value = true
  })

  // 支持深链：?course=机器学习&auto=1&level=进阶&daily_hours=4h&goal=考试&deadline=2026-10-10
  // 便于把「一条完整链路」直接做成可分享的演示链接，也方便自动化截图验证。
  const qs = new URLSearchParams(window.location.search)
  const qCourse = (qs.get('course') || '').trim()
  if (qs.get('level')) profile.value.level = qs.get('level')
  if (qs.get('daily_minutes')) profile.value.daily_minutes = Number(qs.get('daily_minutes'))
  if (qs.get('daily_hours')) profile.value.daily_hours = qs.get('daily_hours')
  if (qs.get('goal')) profile.value.goal = qs.get('goal')
  if (qs.get('goal_other')) profile.value.goal_other = qs.get('goal_other')
  if (qs.get('deadline') !== null) profile.value.deadline = qs.get('deadline') || ''
  if (qs.get('cache') === '0') useCache.value = false

  if (qCourse) {
    course.value = qCourse
    if (qs.get('auto') === '1') onGenerate(qCourse)
  }

  // 需要填 Key 时自动弹设置，别让用户在一堆按钮里找入口。
  // 可用 ?settings=0 关掉，?settings=1 强制打开；演示链接（auto=1）不打扰。
  const wantSettings = qs.get('settings')
  if (wantSettings === '1') {
    showSettings.value = true
  } else if (wantSettings !== '0' && needsKey.value && qs.get('auto') !== '1' && !isPhone()) {
    showSettings.value = true
    statusTone.value = 'warn'
    statusText.value = '⚠ 当前是 LLM 模式但还没填 API Key —— 请在这里填入你自己的 Key'
  }

  // 首访新手指引：宠物已选且没看过才弹（每次加载只自动弹一次）
  maybeShowTour()
})

// ---------- 交互 ----------
function onGenerate(name, cacheOverride) {
  if (!name) {
    statusTone.value = 'warn'
    statusText.value = '⚠ 汪？好像还没告诉我今天要学什么课程呢'
    notify({ type: 'warn', text: '汪？好像还没告诉我今天要学什么课程呢' })
    return
  }
  course.value = name
  const allowCache = cacheOverride === undefined ? useCache.value : !!cacheOverride
  statusText.value = `⏳ 正在为「${name}」生成方案，链路执行中…`
  showTrace.value = false
  stream.generate(name, { ...profile.value }, allowCache)
}

function onReplayHistory(entry) {
  const name = String(entry?.name || '').trim()
  if (!name) return
  onGenerate(name, true)
}

async function onProfileChange(p) {
  // ⚠️ 这里**绝对不能**再写回 `profile.value = p`。
  //
  // CourseForm 用 `watch(profile, ..., { deep: true })` 监听，回调里
  // `emit('profile-change', { ...profile.value })` 每次都是一个**新对象**。
  // 若这里把新对象写回 profile，子组件的 model 值身份就变了，
  // 深度监听会再次触发 → 再次 emit → 再次写回……形成无限渲染循环。
  //
  // 后果：页面首屏能渲染出来，但 JS 线程随即被 100% 占满，
  // 表现为「所有按钮点了都没反应」+ CPU 飙升。
  //
  // 画像本来就已经通过 `v-model:profile` 双向同步过了，这里只需保存。
  try {
    const res = await api.saveProfile(p)
    suggestedDays.value = res.suggested_days || suggestedDays.value
  } catch (_) {
    /* 画像保存失败不阻断主流程 */
  }
}

function copyText(text, label) {
  if (!text) return
  const done = () => notify({ type: 'success', text: `收到！${label}已经乖乖跑到剪贴板里啦` })
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done))
  } else {
    fallbackCopy(text, done)
  }
}

function fallbackCopy(text, done) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  try {
    document.execCommand('copy')
    done()
  } catch (_) {
    notify({ type: 'error', text: '哎呀，没能复制成功，主人手动选一下吧' })
  }
  document.body.removeChild(ta)
}

function canExportPlan() {
  return !!result.value && result.value.type !== 'crisis'
}

function openExport() {
  if (!canExportPlan()) return
  if (!exportAt.value) {
    const d = new Date()
    const p = (n) => String(n).padStart(2, '0')
    exportAt.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
  }
  showExport.value = true
}

async function onExport() {
  openExport()
}

function onCopyOutline() {
  // 大纲从 v20 起是章节对象 {"title","points"}；旧的纯字符串项也兼容
  const list = (result.value?.outline || [])
    .map((c, i) => {
      const isObj = c && typeof c === 'object' && !Array.isArray(c)
      const title = String(isObj ? (c.title || c.name || `第 ${i + 1} 章`) : (c || `第 ${i + 1} 章`)).trim()
      const points = (isObj ? (c.points || c.items || []) : [])
        .map((p) => String(p).trim())
        .filter(Boolean)
        .map((p) => `   · ${p}`)
        .join('\n')
      return `${i + 1}. ${title}${points ? '\n' + points : ''}`
    })
    .join('\n')
  copyText(`【${result.value?.course}】课程大纲\n${list}`, '大纲')
}

function onCopyPlan() {
  const list = (result.value?.plan_items || [])
    .map((d) => `Day ${d.day}｜${d.title}${d.chapters?.length ? '（' + d.chapters.join(' / ') + '）' : ''}`)
    .join('\n')
  copyText(`【${result.value?.course}】学习计划\n${list}`, '计划')
}

async function openTrace() {
  showTrace.value = true
  await stream.refreshTrace()
}

function onLoadHistory(payload) {
  showHistory.value = false
  if (!payload?.ok) return
  // 把历史方案回填到三栏（不走流水线，因此节点全部标记完成）
  stream.reset()
  for (const s of STAGES) stream.steps[s.key].status = 'done'
  result.value = payload
  stream.status.value = 'done'
  course.value = payload.course
  statusText.value = `📜 已载入历史方案：${payload.course}（大纲 ${payload.stats.outline} 章 / 计划 ${payload.stats.plan} 天）`
  statusTone.value = 'success'
  notify({ type: 'success', text: `翻出旧档案啦！正在重温「${payload.course}」的方案~` })
  if (payload.type !== 'crisis') showExport.value = true
}

/** 学情页里点「打开这门课」：切回方案页并载入该课程的历史方案 */
async function onOpenCourseFromProgress(courseName) {
  if (!courseName) {
    goCourse()
    return
  }
  try {
    const payload = await api.historyDetail(courseName)
    appView.value = 'course'
    onLoadHistory(payload)
  } catch (e) {
    notify({ type: 'error', text: `打不开这页档案了呜呜：${e.message}` })
  }
}

// ---------- 学习进度（结果区勾选） ----------
/** {outline:[{title,done}], plan:[{title,done}]}，索引与 result 一一对应 */
const studyProgress = ref({ outline: [], plan: [] })

async function loadStudyProgress() {
  const c = result.value?.course
  if (!c) {
    studyProgress.value = { outline: [], plan: [] }
    return
  }
  try {
    const data = await api.historyDetail(c)
    studyProgress.value = data.progress || { outline: [], plan: [] }
  } catch (_) {
    // 方案刚落库时可能还查不到，静默处理；勾选时会重新对齐
    studyProgress.value = { outline: [], plan: [] }
  }
}

// 方案生成完成 / 从历史载入后，把勾选状态拉回来
watch([() => result.value?.course, status], ([c, s]) => {
  if (c && s === 'done') loadStudyProgress()
})

async function onToggleProgress({ kind, index, done }) {
  const c = result.value?.course
  if (!c) return

  // 乐观更新：先动界面，失败再回滚（点勾选框不该有延迟感）
  const list = [...(studyProgress.value[kind] || [])]
  const prev = list[index]?.done
  list[index] = { ...(list[index] || { title: '' }), done }
  studyProgress.value = { ...studyProgress.value, [kind]: list }

  try {
    const r = await api.progressDone(c, kind, index, done)
    if (r.progress) studyProgress.value = r.progress
    const st = r.stats || {}
    statusText.value = `进度已更新：${st.done ?? 0} / ${st.total ?? 0}`
  } catch (e) {
    const back = [...(studyProgress.value[kind] || [])]
    if (back[index]) back[index] = { ...back[index], done: prev }
    studyProgress.value = { ...studyProgress.value, [kind]: back }
    notify({ type: 'error', text: `没能保存成功，出了点小状况：${e.message}` })
  }
}

function onSettingsSaved(newMode) {
  if (newMode) {
    mode.value = newMode
    // 保存后重新判断是否仍缺 Key，角标高亮才会及时消失
    needsKey.value = newMode.mode !== 'mock' && !newMode.has_key
  }
  notify({ type: 'success', text: '运行模式换好啦，随时准备出发！' })
  finishSettingsOnboard()
}

function onSettingsClose() {
  finishSettingsOnboard()
}

const isMockMode = computed(() => mode.value?.mode === 'mock')

/**
 * 降级提示分两种语气（与桌面版逻辑一致，但 Web 上更直观）：
 * - Mock 模式：本来就是内置数据，用中性提示即可，不要吓用户；
 * - LLM 模式：大模型调用失败走了模板，必须橙色告警，明确说明「这不是大模型生成的」。
 */
function onPetGo(e) {
  const target = e.detail && e.detail.target
  if (target === 'study') goStudy()
  else if (target === 'chat') goChat()
  else if (target === 'knowledge') goKnowledge('notes')
  else if (target === 'wrong') goKnowledge('wrong')
}
if (typeof window !== 'undefined') window.addEventListener('zjxt:go', onPetGo)
onBeforeUnmount(() => {
  if (typeof window !== 'undefined') window.removeEventListener('zjxt:go', onPetGo)
})

const degradedBanner = computed(() => {
  const d = result.value?.degraded
  if (!d) return null
  const agents = (d.agents || []).join(' / ')
  if (isMockMode.value) {
    return {
      tone: 'info',
      icon: '📦',
      title: '当前在 Mock 模式，这是我用内置模板拼出来的方案哦',
      detail: `兜底节点：${agents}。章节和资源都来自我的小金库，不需要消耗任何魔法（API 额度）啦。`,
    }
  }
  return {
    tone: 'warn',
    icon: '⚠',
    title: '呜...这次的方案不是大模型生成的',
    detail: `${agents} 走内置模板兜底啦（因为：${d.error}）。请主人检查下 API Key、网络或者账户余额，然后再让我试一次吧！`,
  }
})

</script>

<template>
  <div class="app" :class="{ 'has-scene': !!activeScene }">
    <SceneBackdrop v-if="appView !== 'study'" :scene="activeScene" />
    <SpaceLayer v-show="!showGuide" />
    <PetCompanion
      :visible="!showGuide"
      @open-profile="openProfile"
    />

    <!-- 角色引导：没选过宠物先选化身 -->
    <PetGuide v-if="showGuide" @done="onGuideDone" />

    <!-- 首访欢迎层：关闭后进入下方工具界面 -->
    <WelcomeScreen
      v-if="showWelcome"
      :needs-key="needsKey"
      @start="onWelcomeDone"
      @open-knowledge="goKnowledge"
      @open-import="goImport"
      @open-transcribe="goTranscribe"
      @open-chat="goChat"
      @open-wrongbook="goWrongBook"
      @open-mindmap="goMindMap"
      @open-study="goStudy"
      @open-progress="goProgress"
      @open-manual="goManual"
      @open-settings="openSettings"
      @open-history="openHistory"
      @open-trace="openLogs"
    />

    <LoginDialog :open="showLogin" @close="showLogin = false" />

    <Teleport to="body" :disabled="!showWelcome">
    <AppHeader
      v-show="!showGuide"
      :mode="mode"
      :has-result="!!result"
      :busy="busy"
      :needs-key="needsKey"
      :current="showWelcome ? 'home' : appView"
      @export="onExport"
      @go-course="goCourse"
        @go-home="goHome"
        @open-login="showLogin = true"
      @open-trace="openLogs"
      @open-settings="openSettings"
      @open-history="openHistory"
      @open-knowledge="goKnowledge"
      @open-import="goImport"
      @open-transcribe="goTranscribe"
      @open-chat="goChat"
      @open-wrongbook="goWrongBook"
      @open-mindmap="goMindMap"
      @open-study="goStudy"
      @open-progress="goProgress"
      @open-manual="goManual"
    />
    </Teleport>

    <main class="main" :class="{ 'under-wins': !showWelcome && appView !== 'study', 'study-main': appView === 'study' }">
      <KnowledgePage
        v-if="appView === 'knowledge'"
        :section="knowledgeSection"
        @back="goCourse"
        @open-import="goImport"
        @go-course="goCourse"
        @notify="notify"
      />
      <ImportPage
        v-else-if="appView === 'import'"
        @back="goCourse"
        @open-knowledge="goKnowledge"
        @go-course="goCourse"
      />
      <TranscribePage
        v-else-if="appView === 'transcribe'"
        @back="goCourse"
        @open-knowledge="goKnowledge"
        @go-course="goCourse"
      />
      <ChatPage
        v-else-if="appView === 'chat'"
        :course-context="result?.course || course"
        :mode="mode"
        @notify="notify"
        @go-course="goCourse"
      />
      <WrongBookPage
        v-else-if="appView === 'wrongbook'"
        @back="goCourse"
        @go-course="goCourse"
        @notify="notify"
      />
      <LearningProgress
        v-else-if="appView === 'progress'"
        @back="goCourse"
        @open-course="onOpenCourseFromProgress"
        @notify="notify"
      />
      <HandbookPage
        v-else-if="appView === 'manual'"
        @back="goCourse"
      />
      <MindMapPage
        v-else-if="appView === 'mindmap'"
        @back="goCourse"
        @notify="notify"
      />
      <StudySpacePage v-else-if="appView === 'study'" />
      <template v-else>
      <!-- ① 课程名 + 画像 -->
      <CourseForm
        v-model:course="course"
        v-model:profile="profile"
        :options="options"
        :busy="busy"
        :suggested-days="suggestedDays"
        @generate="onGenerate"
        @profile-change="onProfileChange"
        @replay="onReplayHistory"
      />

      <!-- 生成选项 -->
      <div class="opts">
        <label class="check">
          <input v-model="useCache" type="checkbox" :disabled="busy" />{{ t('app.1') }}</label>
        <span v-if="usedFallback" class="chip chip-warn">{{ t('app.2') }}</span>
        <span v-if="sourceDir" class="src-path" :title="sourceDir">
          业务逻辑来源：{{ sourceDir }}
        </span>
      </div>

      <!-- ② Agent 流水线 -->
      <PipelineStepper
        :steps="steps"
        :status="status"
        :active-index="activeIndex"
        :progress="progress"
        :meta="meta"
      />

      <!-- 降级 / 错误提示 -->
      <div v-if="degradedBanner" class="banner" :class="degradedBanner.tone">
        <span class="b-ico">{{ degradedBanner.icon }}</span>
        <div>
          <b>{{ degradedBanner.title }}</b>
          <p>{{ degradedBanner.detail }}</p>
        </div>
      </div>

      <div v-if="error" class="banner err">
        <span class="b-ico">✗</span>
        <div>
          <b>{{ t('app.3') }}</b>
          <p>{{ error }}</p>
        </div>
      </div>

      <!-- ③ 三栏结果 -->
      <ResultsGrid
        :result="result"
        :loading="busy"
        :progress="studyProgress"
        @copy-outline="onCopyOutline"
        @copy-plan="onCopyPlan"
        @toggle-progress="onToggleProgress"
        @export="openExport"
      />

      <!-- ④ 课程问答 -->
      <ChatPanel
        :course-context="result?.course || course"
        :mode="mode"
        @notify="notify"
      />
      </template>
    </main>

    <!-- 抽屉 / 弹窗 -->
    <TraceDrawer
      :open="showTrace"
      :lines="traces"
      :trace-file="traceFile"
      :error="traceError"
      @close="showTrace = false"
      @refresh="stream.refreshTrace()"
    />

    <SettingsDialog
      :open="showSettings"
      :mode="mode"
      :onboarding="settingsOnboarding"
      @close="onSettingsClose"
      @saved="onSettingsSaved"
      @show-tour="openTour"
    />

    <TourDialog
      :open="showTour"
      :pet-name="displayName"
      @close="onTourClose"
      @dismiss="onTourDismiss"
    />

    <!-- 单界面气泡：六个功能位首次进入时延迟 800ms 浮起，无遮罩，z-index 150 -->
    <!-- 宠物档案弹层：点击宠物本体触发，z-index 155（高于悬浮窗 140 不盖总览 160） -->
    <PetProfileDialog
      :open="showProfile"
      @close="closeProfile"
      @change-pet="onProfileChangePet"
    />

    <HistoryDialog
      :open="showHistory"
      @close="showHistory = false"
      @load="onLoadHistory"
      @notify="notify"
    />

    <ExportPreview
      :open="showExport"
      :result="result"
      :profile="profile"
      :generated-at="exportAt"
      @close="showExport = false"
    />

    <!-- Toast -->
    <div class="toasts">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="`t-${t.type}`">
        {{ t.text }}
      </div>
    </div>

    <StatusBar
      :text="statusText"
      :tone="statusTone"
      :stats="result?.stats || null"
      :duration="result?.duration_ms || 0"
      :from-cache="!!result?.from_cache"
    />
  </div>
</template>

<style scoped>
.app {
  position: relative;
  min-height: 100vh;
  padding-bottom: 52px;
  z-index: 1;
}

.app.has-scene {
  background: transparent;
}

.app.has-scene :deep(.card),
.app.has-scene :deep(.form-card),
.app.has-scene :deep(.pipeline),
.app.has-scene :deep(.chat),
.app.has-scene :deep(.panel) {
  background: rgba(var(--bg-card-rgb), 0.86);
  backdrop-filter: blur(8px);
}

.main {
  position: relative;
  z-index: 1;
  max-width: 1360px;
  margin: 0 auto;
  padding: 78px 26px 26px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.main.under-wins {
  /* 左右缘竖签宽 36px，主区原来只有 26px，标题和说明会被切掉。 */
  padding-left: 52px;
  padding-right: 52px;
}

.main.study-main {
  max-width: none;
  margin: 0;
  padding: 78px 26px 26px;
  gap: 0;
}

.opts {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  padding: 0 4px;
}

.check {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
}

.check input {
  accent-color: var(--primary);
  width: 14px;
  height: 14px;
}

.src-path {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-faint);
  font-family: var(--font-mono);
  max-width: 46%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.banner {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 12px 16px;
  border-radius: var(--radius);
  font-size: 12.5px;
  line-height: 1.65;
}

.banner b {
  font-size: 13px;
}

.banner p {
  margin-top: 2px;
  opacity: 0.9;
}

.banner.warn {
  background: var(--warning-soft);
  border: 1px solid #fde68a;
  color: #92400e;
}

.banner.info {
  background: var(--bg-disabled);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}

.banner.err {
  background: var(--error-soft);
  border: 1px solid #fecaca;
  color: #991b1b;
}

.b-ico {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-weight: 800;
  font-size: 13px;
  background: rgba(var(--bg-card-rgb), 0.7);
}

/* ---------- Toast ---------- */
.toasts {
  position: fixed;
  /* 顶栏 z-index 128，会盖住右上角 16px 处的提示。挂到顶栏正下方，不改文案、不抢导航。 */
  top: 76px;
  right: 16px;
  z-index: 126;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 340px;
  pointer-events: none;
}

.toast {
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  font-weight: 600;
  box-shadow: var(--shadow);
  animation: fade-up 0.22s ease both;
  background: var(--bg-card);
  border-left: 4px solid var(--primary);
  color: var(--text-secondary);
  pointer-events: auto;
}

.toast.t-success {
  border-left-color: var(--success);
}

.toast.t-warn {
  border-left-color: var(--warning);
}

.toast.t-error {
  border-left-color: var(--error);
}

@media (max-width: 860px) {
  .toasts {
    top: 64px;
    right: 12px;
  }
  .main {
    padding: 170px 16px 22px;
  }
  .main.study-main {
    padding: 170px 16px 22px;
  }
  .src-path {
    display: none;
  }
}

@media (max-width: 430px) {
  .toasts {
    top: 108px;
    right: 12px;
    left: 12px;
    max-width: none;
  }
  .main.under-wins {
    padding-top: 248px;
    padding-bottom: 96px;
  }
  .main.study-main {
    padding: 8px 8px 72px;
  }
  /* 手机上三个悬浮窗都收成竖签，位置是固定的一列（x=0..36，每个 108 高）；
     而主区左右只有 8px 内边距 → 竖签会压住正文（实测「课程问答」的「课」字、
     「学习目标」都被盖住）。统一让出 46px = 36 竖签 + 10 间隙。 */
  .main,
  .main.study-main,
  .main.under-wins {
    padding-left: 46px !important;
  }
}
</style>
