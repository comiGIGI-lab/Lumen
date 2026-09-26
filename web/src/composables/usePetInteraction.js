/**
 * 学伴互动层：和 usePet 数据层解耦，处理手势识别、冷却记录和经验事件派发。
 *
 * 规范：
 * - 双击宠物弹出「摸摸 / 喂食 / 玩耍」菜单，分别增加 2/5/8 经验，同一动作冷却 30 秒。
 * - 长按宠物 1 秒触发「撒娇模式」，屏幕中央弹出气泡「XXX 蹭了蹭你的手指」，3 秒后自动消失。
 * - 宠物空闲超过 5 分钟，自动在屏幕中央弹出「提醒自习」气泡「要不要去自习一会儿？我陪你。」。
 */
import { onBeforeUnmount, reactive, ref } from 'vue'

export const DEFAULT_ACTIONS = [
  { id: 'pet', name: '摸摸', exp: 2, cooldown: 30, bubble: '蹭了蹭你的手指~' },
  { id: 'feed', name: '喂食', exp: 5, cooldown: 30, bubble: '吃饱啦，谢谢！' },
  { id: 'play', name: '玩耍', exp: 8, cooldown: 30, bubble: '玩得超开心！' },
]

export const DEFAULT_LONG_PRESS_MS = 1000
export const DEFAULT_DOUBLE_TAP_MS = 320
export const DEFAULT_DOUBLE_TAP_SLOP = 14
export const DEFAULT_IDLE_MS = 5 * 60 * 1000 // 5 分钟

export function usePetInteraction(options = {}) {
  const {
    actions = DEFAULT_ACTIONS,
    longPressMs = DEFAULT_LONG_PRESS_MS,
    doubleTapMs = DEFAULT_DOUBLE_TAP_MS,
    doubleTapSlop = DEFAULT_DOUBLE_TAP_SLOP,
    idleMs = DEFAULT_IDLE_MS,
    onAction,         // (action, exp) => void
    onCozyBubble,     // (petName) => void 撒娇气泡回调
    onIdleBubble,     // () => void 闲置提醒回调
    getPetName = () => '学伴',
  } = options

  /** 各动作上次执行时间戳（内存记录，也可以扩展持久化） */
  const cooldowns = reactive({})

  function getRemainingCooldown(actionId) {
    const last = cooldowns[actionId] || 0
    const action = actions.find((a) => a.id === actionId)
    const cd = action ? action.cooldown : 30
    const elapsed = (Date.now() - last) / 1000
    return Math.max(0, Math.ceil(cd - elapsed))
  }

  function canRun(actionId) {
    return getRemainingCooldown(actionId) === 0
  }

  /** 执行动作：记录冷却、增加经验、重置闲置 */
  function runAction(action) {
    if (!canRun(action.id)) {
      return { success: false, remaining: getRemainingCooldown(action.id) }
    }
    cooldowns[action.id] = Date.now()
    resetIdle()
    if (typeof onAction === 'function') {
      onAction(action, action.exp)
    }
    return { success: true, remaining: action.cooldown }
  }

  // ---------- 双击检测 ----------
  let lastTapAt = 0
  let lastTapX = 0
  let lastTapY = 0

  function detectDoubleTap(now, x, y) {
    const dt = now - lastTapAt
    const dx = Math.abs(x - lastTapX)
    const dy = Math.abs(y - lastTapY)
    const isDouble = dt > 30 && dt <= doubleTapMs && dx <= doubleTapSlop && dy <= doubleTapSlop
    lastTapAt = now
    lastTapX = x
    lastTapY = y
    return isDouble
  }

  // ---------- 长按 1 秒检测 ----------
  let pressTimer = null
  const longPressTriggered = ref(false)

  function pressStart() {
    longPressTriggered.value = false
    clearTimeout(pressTimer)
    pressTimer = setTimeout(() => {
      longPressTriggered.value = true
      resetIdle()
      if (typeof onCozyBubble === 'function') {
        onCozyBubble(getPetName())
      }
    }, longPressMs)
  }

  function pressCancel() {
    clearTimeout(pressTimer)
    pressTimer = null
  }

  function wasLongPressed() {
    return longPressTriggered.value
  }

  // ---------- 空闲 5 分钟检测 ----------
  const lastActiveAt = ref(Date.now())
  let idleTimer = null
  let idleFired = false

  function resetIdle() {
    lastActiveAt.value = Date.now()
    idleFired = false
  }

  function startIdleWatcher() {
    stopIdleWatcher()
    resetIdle()
    if (typeof window !== 'undefined') {
      window.addEventListener('pointerdown', resetIdle, { passive: true })
      window.addEventListener('keydown', resetIdle, { passive: true })
    }
    idleTimer = setInterval(() => {
      const elapsed = Date.now() - lastActiveAt.value
      if (elapsed >= idleMs && !idleFired) {
        idleFired = true
        if (typeof onIdleBubble === 'function') {
          onIdleBubble()
        }
      }
    }, 15 * 1000)
  }

  function stopIdleWatcher() {
    if (idleTimer) clearInterval(idleTimer)
    idleTimer = null
    clearTimeout(pressTimer)
    pressTimer = null
    if (typeof window !== 'undefined') {
      window.removeEventListener('pointerdown', resetIdle)
      window.removeEventListener('keydown', resetIdle)
    }
  }

  onBeforeUnmount(() => {
    stopIdleWatcher()
  })

  return {
    actions,
    cooldowns,
    getRemainingCooldown,
    canRun,
    runAction,
    detectDoubleTap,
    pressStart,
    pressCancel,
    wasLongPressed,
    resetIdle,
    startIdleWatcher,
    stopIdleWatcher,
  }
}
