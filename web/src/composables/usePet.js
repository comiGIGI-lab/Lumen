/**
 * 学伴：网页右下角的学习伙伴，头脑的化身。
 * 形象 / 等级 / 经验 / 形态只存本地 localStorage（按账号分档 zjxt.pet.<用户名|anon>），
 * 不上传服务器；zjxt.welcomed 归欢迎层，两边互不相干。
 */
import { computed, reactive, ref } from 'vue'
import { keyedStorage } from '@/composables/ownerTag'

export const PET_KEY = 'zjxt.pet'

/**
 * 经验来源：
 * - 自习计时按分钟给，每分钟 1 经验，完整跑完才结算（暂停 / 放弃不给）；
 *   当天第一次完整自习额外 +10（按本地日期记在 zjxt.pet.bonusDate）。
 * - 生成一次学习方案 +40，每天只有前两次生成给经验，之后不给。
 * - 课程问答不给。
 * 升级曲线：第 N 级升 N+1 需要 40 + 20×(N-1)。
 *
 * 进化两段：Lv5 开放进阶形态；首次进化后下一段（究极形态）门槛 Lv30，
 * 保证二段进化不早于 30 天。
 *
 * 连签：每天首次完整自习计连签；断签且找回池有次数则自动消耗一次续上；
 * 找回池每周自动补到 1 次（本周已补过就不再补）。
 */
export const XP_STUDY_PER_MIN = 1
export const XP_STUDY_DAILY_BONUS = 10
export const XP_PLAN = 40
/** 每天前几次方案生成给经验 */
export const XP_PLAN_DAILY_CAP = 2

/** Lv5 起开放进阶形态；选「保持」后每次升级仍会再问 */
export const EVOLVE_LEVEL = 5
/** 进阶形态之后，下一段（究极形态）门槛 */
export const EVOLVE2_LEVEL = 30
/** 连签找回池上限 / 每周自动补充到 */
export const STREAK_POOL_MAX = 1

export const PETS = [
  {
    id: 'yaya',
    name: '芽芽',
    // 性格 / 学习类型 / 引导页副标语（PetGuide 卡片底部按这三字段渲染）
    personality: '踏实型',
    learningStyle: '阅读型',
    tagline: '先扎根，再生长',
    baseFile: 'yaya',
    evolvedFile: 'yaya-evo',
    evolvedName: '芽芽·树',
  },
  {
    id: 'yanzai',
    name: '焰仔',
    personality: '热忱型',
    learningStyle: '视觉型',
    tagline: '越学越有劲',
    baseFile: 'yanzai',
    evolvedFile: 'yanzai-evo',
    evolvedName: '焰仔·龙',
  },
  {
    id: 'paopao',
    name: '泡泡',
    personality: '稳健型',
    learningStyle: '听觉型',
    tagline: '稳稳游向深处',
    baseFile: 'paopao',
    evolvedFile: 'paopao-evo',
    evolvedName: '泡泡·甲',
  },
  {
    id: 'dengdeng',
    name: '灯灯',
    personality: '灵动型',
    learningStyle: '动手型',
    tagline: '一触即发的灵感',
    baseFile: 'dengdeng',
    evolvedFile: 'dengdeng-evo',
    evolvedName: '灯灯·闪',
  },
  {
    id: 'momo',
    name: '墨墨',
    personality: '善变型',
    learningStyle: '视觉型',
    tagline: '你学什么它就偏什么',
    baseFile: 'momo',
    evolvedFile: 'momo-evo',
    evolvedName: '墨墨·仙',
  },
  {
    id: 'douding',
    name: '豆丁',
    personality: '温润型',
    learningStyle: '阅读型',
    tagline: '慢慢把知识焐热',
    baseFile: 'douding',
    evolvedFile: 'douding-evo',
    evolvedName: '豆丁·焰',
  },
  {
    id: 'tuantuan',
    name: '团团',
    personality: '好奇型',
    learningStyle: '动手型',
    tagline: '见缝就钻进去看',
    baseFile: 'tuantuan',
    evolvedFile: 'tuantuan-evo',
    evolvedName: '团团·六六',
  },
  {
    id: 'chouchou',
    name: '丑丑',
    personality: '潜力型',
    learningStyle: '听觉型',
    tagline: '丑小鸭也会发光',
    baseFile: 'chouchou',
    evolvedFile: 'chouchou-evo',
    evolvedName: '丑丑·仙仙',
  },
  {
    id: 'jiujiu',
    name: '啾啾',
    personality: '松弛型',
    learningStyle: '阅读型',
    tagline: '唱着歌就把事做了',
    baseFile: 'jiujiu',
    evolvedFile: 'jiujiu-evo',
    evolvedName: '啾啾·胖',
  },
]

/** 升到下一级需要的经验：等级越高要得越多 */
export function expNeed(level) {
  return 40 + Math.max(0, level - 1) * 20
}

/**
 * 旧侵权 id（知识产权合规）：这些名字一律清成空，等级 / 经验 / 连签等成长原样保留，
 * 由 App.vue 首屏判断触发一次单独的 PetGuide 让用户重新选化身（等级经验不丢）。
 */
const INFRINGE_IDS = [
  'bulbasaur', 'charmander', 'squirtle', 'pikachu', 'eevee', 'vulpix',
  'zigzagoon', 'feebas', 'jigglypuff', 'ivysaur', 'wartortle', 'charmeleon',
  'raichu', 'sylveon', 'ninetales', 'linoone', 'milotic', 'wigglytuff',
]

/** 旧侵权 id 命中标记：命中后要在 pet 初始化后立即把清空结果写回存储，让首屏引导页能重新出现 */
let clearedInfringe = false

function petKey() {
  // 按账号分档：同一浏览器多账号不互相污染；anon 档兼容旧的 zjxt.pet
  // （老数据只在 anon 身份下读得到，首次保存后落到新 key，旧 key 不再写）
  return keyedStorage('zjxt.pet')
}

function loadPet() {
  try {
    const key = petKey()
    let raw = localStorage.getItem(key)
    if (!raw && key !== PET_KEY) raw = localStorage.getItem(PET_KEY) // 旧版未分档数据
    if (!raw) return null
    const data = JSON.parse(raw)
    if (!data || typeof data.id !== 'string') return null
    // 知识产权兼容：旧侵权 id 清空，等级 / 经验 / 连签等成长字段原样保留
    if (INFRINGE_IDS.includes(data.id)) {
      clearedInfringe = true
      return {
        id: '',
        form: null,
        level: Math.min(99, Math.max(1, Number(data.level) || 1)),
        exp: Math.max(0, Number(data.exp) || 0),
        bonusDate: typeof data.bonusDate === 'string' ? data.bonusDate : '',
        planDate: typeof data.planDate === 'string' ? data.planDate : '',
        planCount: Math.max(0, Number(data.planCount) || 0),
        streak: Math.max(0, Number(data.streak) || 0),
        lastStudyDate:
          typeof data.lastStudyDate === 'string' ? data.lastStudyDate : '',
        streakPool: Math.max(0, Number(data.streakPool) || 0),
        streakPoolWeek:
          typeof data.streakPoolWeek === 'string' ? data.streakPoolWeek : '',
      }
    }
    if (!PETS.some((p) => p.id === data.id)) return null
    return {
      id: data.id,
      form: data.form === 'evolved' ? 'evolved' : 'base',
      level: Math.min(99, Math.max(1, Number(data.level) || 1)),
      exp: Math.max(0, Number(data.exp) || 0),
      // 向后兼容：旧数据缺字段一律按默认补，等级经验原样保留
      bonusDate: typeof data.bonusDate === 'string' ? data.bonusDate : '',
      planDate: typeof data.planDate === 'string' ? data.planDate : '',
      planCount: Math.max(0, Number(data.planCount) || 0),
      streak: Math.max(0, Number(data.streak) || 0),
      lastStudyDate:
        typeof data.lastStudyDate === 'string' ? data.lastStudyDate : '',
      streakPool: Math.max(0, Number(data.streakPool) || 0),
      streakPoolWeek:
        typeof data.streakPoolWeek === 'string' ? data.streakPoolWeek : '',
      // 性格 / 学习类型 / 引导页副标语：旧数据缺这三字段按空串补全，等级经验等不动
      personality: typeof data.personality === 'string' ? data.personality : '',
      learningStyle: typeof data.learningStyle === 'string' ? data.learningStyle : '',
      tagline: typeof data.tagline === 'string' ? data.tagline : '',
      // 成长记录与进化时间戳：旧数据缺按 [] / '' 补全
      expLog: Array.isArray(data.expLog)
        ? data.expLog.filter(
            (e) =>
              e &&
              typeof e.time === 'string' &&
              typeof e.source === 'string' &&
              typeof e.amount === 'number',
          )
        : [],
      evolvedAt: typeof data.evolvedAt === 'string' ? data.evolvedAt : '',
    }
  } catch (_) {
    return null
  }
}

const pet = reactive(loadPet() || {
  id: '',
  form: 'base',
  level: 1,
  exp: 0,
  bonusDate: '',
  planDate: '',
  planCount: 0,
  streak: 0,
  lastStudyDate: '',
  streakPool: 0,
  streakPoolWeek: '',
  personality: '',
  learningStyle: '',
  tagline: '',
  expLog: [],
  evolvedAt: '',
})
// 知识产权兼容：旧侵权 id 已清空，立即把清空结果写回存储。
// 这样首屏 hasPetSaved() 读到空 id → PetGuide 重新出现，用户重选化身时等级 / 经验 / 连签等成长由 choosePet 原样保留。
if (clearedInfringe) persist()
const hasPet = ref(!!pet.id)
const showEvolve = ref(false)
/** 每次升级 +1，给右下 HUD 触发一次跳动反馈 */
const levelStamp = ref(0)

function todayStr() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** 本周周一的 YYYY-MM-DD，用于「每周补一次找回池」 */
function weekKeyStr() {
  const d = new Date()
  const dow = (d.getDay() + 6) % 7 // 周一为 0
  const mon = new Date(d.getFullYear(), d.getMonth(), d.getDate() - dow)
  const p = (n) => String(n).padStart(2, '0')
  return `${mon.getFullYear()}-${p(mon.getMonth() + 1)}-${p(mon.getDate())}`
}

/** 'YYYY-MM-DD' → 'YYYY-MM-DD' 的次日 */
function nextDayStr(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || '')
  if (!m) return ''
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  d.setDate(d.getDate() + 1)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function persist() {
  try {
    localStorage.setItem(petKey(), JSON.stringify({ ...pet }))
  } catch (_) {
    /* 存不上不阻塞 */
  }
}

function speciesOf(id) {
  return PETS.find((p) => p.id === id) || null
}

const displayName = computed(() => {
  const s = speciesOf(pet.id)
  if (!s) return '学伴宠物'
  return pet.form === 'evolved' ? s.evolvedName || s.name : s.name
})

const need = computed(() => expNeed(pet.level))
const ratio = computed(() =>
  pet.level >= 99 ? 1 : Math.min(1, Math.max(0, pet.exp / need.value)),
)
/** 下一进化档：未进化→进阶（Lv5）；已进阶→究极（Lv30） */
const nextEvolveLevel = computed(() =>
  pet.form === 'evolved' ? EVOLVE2_LEVEL : EVOLVE_LEVEL,
)

/** 引导页选完化身调用；之后不再重复出现引导页 */
function choosePet(id) {
  if (!speciesOf(id)) return
  // 兼容重选：旧侵权 id 清空后用户重新选化身（id 为空但等级经验还在），
  // 此时只换形象与形态，保留原有等级 / 经验 / 连签等成长。
  const pristine =
    pet.level <= 1 &&
    pet.exp <= 0 &&
    pet.streak <= 0 &&
    !pet.bonusDate &&
    !pet.lastStudyDate
  pet.id = id
  pet.form = 'base'
  if (!pristine) {
    hasPet.value = true
    persist()
    return
  }
pet.level = 1
    pet.exp = 0
    pet.bonusDate = ''
    pet.planDate = ''
    pet.planCount = 0
    pet.streak = 0
    pet.lastStudyDate = ''
    pet.streakPool = 0
    pet.streakPoolWeek = ''
    pet.expLog = []
    pet.evolvedAt = ''
    hasPet.value = true
    persist()
}

/** 加经验；经验满自动升级。Lv5 起且未进化才弹「保持 / 进化」，之前正常升 */
function grantExp(amount) {
  if (!hasPet.value || pet.level >= 99) return
  pet.exp += Math.max(0, amount)
  let leveled = false
  while (pet.level < 99 && pet.exp >= expNeed(pet.level)) {
    pet.exp -= expNeed(pet.level)
    pet.level += 1
    leveled = true
  }
  if (leveled) {
    levelStamp.value += 1
    if (pet.form === 'base' && pet.level >= EVOLVE_LEVEL) {
      showEvolve.value = true
    }
  }
  persist()
}

/**
 * 经验事件入口：所有加经验路径（自习 / 方案 / 课程问答 / 当日首练加成）走这里，
 * 内部调 grantExp 加经验并往 expLog 追加一条记录（含 ISO 时间戳、来源、amount、变动前后等级/Exp）。
 * amount=0 也允许：用于「课程问答不加经验但留痕」。
 */
function logExp(source, amount) {
  if (!hasPet.value) return
  const value = Math.max(0, Number(amount) || 0)
  const lvBefore = pet.level
  const expBefore = pet.exp
  grantExp(value)
  try {
    const entry = {
      time: new Date().toISOString(),
      source: String(source || ''),
      amount: value,
      lv_before: lvBefore,
      lv_after: pet.level,
    }
    pet.expLog = Array.isArray(pet.expLog) ? pet.expLog.concat([entry]) : [entry]
  } catch (_) {
    /* expLog 写不上不阻塞主流程 */
  }
}

/** 连签 + 找回池：每天首次完整自习结算时调用 */
function updateStreak(today) {
  // 每周免费补一次找回池（本周已补过就不补）
  const weekKey = weekKeyStr()
  if (pet.streakPoolWeek !== weekKey) {
    pet.streakPool = Math.min(STREAK_POOL_MAX, pet.streakPool + 1)
    pet.streakPoolWeek = weekKey
  }
  if (pet.lastStudyDate === today) return // 今天已签到
  if (nextDayStr(pet.lastStudyDate) === today) {
    pet.streak += 1
  } else if (pet.streak > 0 && pet.streakPool > 0) {
    // 断签：找回池有次数就消耗一次续上
    pet.streakPool -= 1
    pet.streak += 1
  } else {
    pet.streak = 1
  }
  pet.lastStudyDate = today
}

/** 完整跑完一次自习：每分钟 1 经验；当天第一次完整自习额外 +10 并计连签 */
function grantStudyExp(minutes) {
  if (!hasPet.value) return
  const gain = Math.max(0, Math.round(Number(minutes) || 0))
  if (gain <= 0) return
  const today = todayStr()
  // 自习按分钟累加经验
  logExp('自习', gain * XP_STUDY_PER_MIN)
  if (pet.bonusDate !== today) {
    // 当天首次完整自习额外 +10（独立一条成长记录）
    pet.bonusDate = today
    updateStreak(today)
    logExp('当日首练加成', XP_STUDY_DAILY_BONUS)
  }
}

/** 生成一次学习方案：每天前 XP_PLAN_DAILY_CAP 次给经验，之后不给 */
function grantPlanExp() {
  if (!hasPet.value) return
  const today = todayStr()
  if (pet.planDate !== today) {
    pet.planDate = today
    pet.planCount = 0
  }
  if (pet.planCount >= XP_PLAN_DAILY_CAP) return
  pet.planCount += 1
  logExp('方案生成', XP_PLAN)
}

function keepForm() {
  showEvolve.value = false
}

/** 进化只换图与形态字段，等级经验不动；首次进化打 ISO 时间戳存到 evolvedAt */
function evolve() {
  pet.form = 'evolved'
  if (!pet.evolvedAt) pet.evolvedAt = new Date().toISOString()
  showEvolve.value = false
  persist()
}

/** 个人空间里更换化身：只换形象，成长保留 */
function changeAvatar(id) {
  if (!speciesOf(id) || id === pet.id) return
  pet.id = id
  pet.form = 'base'
  persist()
}

export function usePet() {
  return {
    PETS,
    pet,
    hasPet,
    showEvolve,
    levelStamp,
    speciesOf,
    displayName,
    need,
    ratio,
    nextEvolveLevel,
    expNeed,
    choosePet,
    grantExp,
    logExp,
    grantStudyExp,
    grantPlanExp,
    keepForm,
    evolve,
    changeAvatar,
    XP_STUDY_PER_MIN,
    XP_STUDY_DAILY_BONUS,
    XP_PLAN,
    XP_PLAN_DAILY_CAP,
    EVOLVE_LEVEL,
    EVOLVE2_LEVEL,
    STREAK_POOL_MAX,
  }
}
