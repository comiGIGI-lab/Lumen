<script setup>
/**
 * 主界面右下常驻学伴（头脑的化身）。z-index 低于弹窗（120+），高于正文。
 * 不挡顶栏、不挡左下「空间」、不挡自习大窗；窄屏再小一档。
 *
 * 指针：只有立绘 .sprite-in 接收指针，aside 与 HUD 的占位区域一律点穿，
 * 免得手机上盖住底下的按钮。点（位移很小的抬手）才 emit 'open-profile'，
 * 由父组件 App.vue 弹 PetProfileDialog（z-index 155）。
 * 拖动：按住立绘移动，松手离左右缘 ≤24px 就收成探头。刷新 / 换页清掉位置。
 * Lv5「保持 / 进化」弹层（showEvolve，z-index 118）走原逻辑，与本 emit 互不干扰。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import PetSprite from './PetSprite.vue'
import { usePet } from '@/composables/usePet'
import { usePetInteraction } from '@/composables/usePetInteraction'

defineProps({
  visible: { type: Boolean, default: true },
})

const emit = defineEmits(['open-profile'])
const { t } = useI18n()

const {
  pet,
  hasPet,
  displayName,
  need,
  ratio,
  showEvolve,
  levelStamp,
  keepForm,
  evolve,
  grantExp,
  logExp,
} = usePet()

const pct = (n) => Math.round((n || 0) * 100)

// ---------- 位置、拖动、贴边探头 ----------
// 默认右下（交给 CSS 的 right/bottom）；拖过一次就记成 left/top 像素，刷新还在。
const POS_KEY = 'zjxt.pet_pos'
/** 抬手时位移超过这个像素数算「拖」，否则算「点」 */
const DRAG_SLOP = 6
/** 松手时离边缘这么近，就吸成一条探头 */
const DOCK_ZONE = 24
/** 探头状态下要拖出这么多像素才脱离贴边（免得手抖把探头拽出来） */
const UNDOCK_SLOP = 30
/** 贴边时至少离顶栏这么远，别压住「首页 / 更多」 */
const TOP_SAFE_DESKTOP = 56
const TOP_SAFE_MOBILE = 0
const TOP_SAFE = computed(() => (isNarrow.value ? TOP_SAFE_MOBILE : TOP_SAFE_DESKTOP))

const buddyEl = ref(null)
const pos = ref(null) // { x, y }；null = 还没拖过，用默认右下
const dock = ref(null) // 'left' | 'right' | null：贴边收成一条探头
const dockY = ref(0) // 探头贴在哪个高度
const dragging = ref(false)

// 窄屏再小一档：改尺寸而不是 transform: scale ——
// scale 会让 getBoundingClientRect 与布局值不一致，第一次拖动就会跳一下。
const isNarrow = ref(false)
const spriteSize = computed(() => {
  if (dock.value) return isNarrow.value ? 44 : 52
  return isNarrow.value ? 52 : 72
})

function loadPos() {
  try {
    const raw = localStorage.getItem(POS_KEY)
    if (!raw) return
    const d = JSON.parse(raw)
    if (d && Number.isFinite(d.x) && Number.isFinite(d.y)) pos.value = { x: d.x, y: d.y }
    if (d && (d.dock === 'left' || d.dock === 'right')) {
      dock.value = d.dock
      dockY.value = Number.isFinite(d.dy) ? d.dy : pos.value ? pos.value.y : 0
    }
  } catch (_) {
    /* 读不到就用默认位置 */
  }
}

function savePos() {
  try {
    if (!pos.value && !dock.value) return
    localStorage.setItem(
      POS_KEY,
      JSON.stringify({
        x: pos.value ? pos.value.x : 0,
        y: pos.value ? pos.value.y : 0,
        dock: dock.value,
        dy: dockY.value,
      }),
    )
  } catch (_) {
    /* 存不上就这次有效，刷新回默认 */
  }
}

/** 空间面板「恢复默认位置」：回到 CSS 右下，清贴边。 */
function resetPos() {
  pos.value = null
  dock.value = null
  dockY.value = 0
  dragging.value = false
  try {
    localStorage.removeItem(POS_KEY)
  } catch (_) {
    /* ignore */
  }
}

function onSpaceReset() {
  resetPos()
  showActionMenu.value = false
}

const HINT_KEY = 'zjxt.tuck_hint_v2'
const showTuckHint = ref(false)
let hintTimer = 0

function maybeShowTuckHint() {
  try {
    if (localStorage.getItem(HINT_KEY) === '1') return
  } catch (_) {
    /* ignore */
  }
  showTuckHint.value = true
  hintTimer = setTimeout(dismissTuckHint, 7000)
}

function dismissTuckHint() {
  if (!showTuckHint.value) return
  showTuckHint.value = false
  if (hintTimer) {
    clearTimeout(hintTimer)
    hintTimer = 0
  }
  try {
    localStorage.setItem(HINT_KEY, '1')
  } catch (_) {
    /* ignore */
  }
}

function clamp(x, y) {
  const w = spriteSize.value
  const h = spriteSize.value
  return {
    x: Math.min(Math.max(0, x), Math.max(0, window.innerWidth - w)),
    y: Math.min(Math.max(0, y), Math.max(0, window.innerHeight - h)),
  }
}

/** 贴边时的纵向范围：上不压顶栏，下不出屏幕。高度按立绘算。 */
function clampDockY(y) {
  const h = spriteSize.value
  const safe = TOP_SAFE.value
  const max = Math.max(safe, window.innerHeight - h - 8)
  return Math.min(Math.max(safe, y), max)
}

/** 拖过之后改用 left/top 定位；贴边时贴到那一侧；都没发生就返回 null，继续走 CSS 的 right/bottom */
const buddyStyle = computed(() => {
  if (dock.value) {
    return {
      left: dock.value === 'left' ? '0px' : 'auto',
      right: dock.value === 'right' ? '0px' : 'auto',
      top: `${dockY.value}px`,
      bottom: 'auto',
    }
  }
  if (!pos.value) return null
  return { left: `${pos.value.x}px`, top: `${pos.value.y}px`, right: 'auto', bottom: 'auto' }
})

let startX = 0
let startY = 0
let startLeft = 0
let startTop = 0
let moved = 0
/** 本次拖动是不是「从边缝往外拉」：出界先不夹，松手再收回视口 */
let pullOut = false

function onPointerDown(e) {
  if (e.button != null && e.button !== 0) return
  const el = buddyEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  // 贴边时 pos 是旧的自由位置，得用实际视觉位置（带负偏移）当起点，
  // 这样往外拖就是「从边缝里拉出来」；没拖过同理用 rect，第一次拖不跳。
  const fromRect = dock.value || !pos.value
  startLeft = fromRect ? rect.left : pos.value.x
  startTop = fromRect ? rect.top : pos.value.y
  startX = e.clientX
  startY = e.clientY
  moved = 0
  pullOut = false
  dragging.value = true
  // 启动长按计时（如果最终触发长按，onPointerUp 会 cancel 这次单击）
  interaction.pressStart()
  try {
    e.currentTarget.setPointerCapture(e.pointerId)
  } catch (_) {
    /* 不支持指针捕获就退化，拖动可能不跟手 */
  }
}

function onPointerMove(e) {
  if (!dragging.value) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  moved = Math.max(moved, Math.abs(dx), Math.abs(dy))
  if (moved > DRAG_SLOP) interaction.pressCancel() // 拖动算移动，取消长按
  if (dock.value) {
    if (moved <= UNDOCK_SLOP) return // 探头状态：要拖够 30px 才脱离贴边
    dock.value = null
    pullOut = true
  }
  if (moved <= DRAG_SLOP) return // 还在「点」的容忍范围内，先不挪
  const nx = startLeft + dx
  const ny = startTop + dy
  pos.value = pullOut ? { x: nx, y: ny } : clamp(nx, ny)
}

function onPointerUp(e) {
  if (!dragging.value) return
  dragging.value = false
  interaction.pressCancel() // 没长按触发就取消
  try {
    e.currentTarget.releasePointerCapture(e.pointerId)
  } catch (_) {
    /* 没捕获过就不用放 */
  }
  if (moved > DRAG_SLOP) {
    if (pos.value) pos.value = clamp(pos.value.x, pos.value.y) // 从边缝拉出来的，松手收回视口
    maybeDockOnRelease()
    savePos() // 拖过了：落在新位置，不算点击
    return
  }
  if (dock.value) {
    undock() // 点探头 = 滑回完整立绘，不开档案
    return
  }
  if (interaction.wasLongPressed()) {
    // 触发长按撒娇模式，抬手不产生点击或双击
    return
  }
  // 位移很小才算点；做双击识别
  const isDouble = interaction.detectDoubleTap(Date.now(), e.clientX, e.clientY)
  if (isDouble) {
    if (tapTimer) {
      clearTimeout(tapTimer)
      tapTimer = null
    }
    showActionMenu.value = !showActionMenu.value
    return
  }
  // 单击延迟防抖：240ms 内若无第二次点击则打开档案
  if (tapTimer) clearTimeout(tapTimer)
  tapTimer = setTimeout(() => {
    openProfile()
    tapTimer = null
  }, 240)
}

/** 松手时贴到左右边缘，就吸成一条探头。拖动时 HUD 还在，用整块宽度判边。 */
function maybeDockOnRelease() {
  if (!pos.value) return
  const w = spriteSize.value
  const right = pos.value.x + w
  if (pos.value.x <= DOCK_ZONE) {
    dock.value = 'left'
    dockY.value = clampDockY(pos.value.y)
    dismissTuckHint()
  } else if (right >= window.innerWidth - DOCK_ZONE) {
    dock.value = 'right'
    dockY.value = clampDockY(pos.value.y)
    dismissTuckHint()
  }
}

/** 点探头：滑回完整立绘，停在它贴的那一侧。HUD 重新占位后再夹一次，别顶出屏幕。 */
function undock() {
  const side = dock.value
  if (!side) return
  const w = spriteSize.value
  const x = side === 'left' ? 0 : Math.max(0, window.innerWidth - w)
  dock.value = null
  pos.value = { x, y: dockY.value }
  nextTick(() => {
    if (pos.value) pos.value = clamp(pos.value.x, pos.value.y)
    savePos()
  })
}

function onPointerCancel() {
  dragging.value = false
}

function syncNarrow() {
  isNarrow.value = window.innerWidth <= 430
}

function onResize() {
  syncNarrow()
  if (dock.value) {
    dockY.value = clampDockY(dockY.value) // 窗口变矮别把探头顶出屏幕、也别顶到顶栏上
    savePos()
    return
  }
  if (!pos.value) return
  pos.value = clamp(pos.value.x, pos.value.y) // 窗口变小别把学伴顶出屏幕
  savePos()
}

let tapTimer = null
const showActionMenu = ref(false)

onMounted(() => {
  syncNarrow()
  // 刷新不恢复上次拖动 / 贴边；会话内拖动仍走 savePos，导航和「恢复默认位置」靠事件清掉。
  window.addEventListener('resize', onResize)
  window.addEventListener('zjxt:reset-layout', onSpaceReset)
  interaction.startIdleWatcher()
  maybeShowTuckHint()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('zjxt:reset-layout', onSpaceReset)
  interaction.stopIdleWatcher()
  clearTimeout(bubbleTimer)
  if (hudTimer) clearTimeout(hudTimer)
  if (tapTimer) clearTimeout(tapTimer)
  if (hintTimer) clearTimeout(hintTimer)
})

function openProfile() {
  emit('open-profile')
}

function onKey(e) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    emit('open-profile')
  }
}

// HUD 默认收起：鼠标进入立绘 .sprite-in 时显形，离开后延迟 150ms 淡出消失。
// 升级 pulse 走独立动画，不强制拉起 HUD。
const hudVisible = ref(false)
let hudTimer = null

function showHud() {
  if (hudTimer) {
    clearTimeout(hudTimer)
    hudTimer = null
  }
  hudVisible.value = true
}

function hideHud() {
  if (hudTimer) clearTimeout(hudTimer)
  hudTimer = setTimeout(() => {
    hudVisible.value = false
    hudTimer = null
  }, 150)
}

// 升级反馈：经验条发光 + 等级数字变红一瞬 + 本体闪一下（纯 CSS，见 .buddy.pulse）
const pulsing = ref(false)
let pulseTimer = 0
watch(levelStamp, () => {
  clearTimeout(pulseTimer)
  pulsing.value = true
  pulseTimer = setTimeout(() => {
    pulsing.value = false
  }, 1800)
})

/** 贴边成探头时不浮 HUD；升级 pulse 走独立动画，不拉起 HUD */
const hudOn = computed(() => !dock.value && hudVisible.value)

// ---------- 互动层（双击 / 长按 / 闲置） ----------
const bubbleText = ref('')
const bubbleKind = ref('') // 'action' | 'cozy' | 'idle' | 'cooldown'
let bubbleTimer = 0
function showBubble(text, kind = 'action', ttl = 1800) {
  bubbleText.value = text
  bubbleKind.value = kind
  clearTimeout(bubbleTimer)
  bubbleTimer = setTimeout(() => {
    bubbleText.value = ''
    bubbleKind.value = ''
  }, ttl)
}

const interaction = usePetInteraction({
  getPetName: () => displayName.value,
  onAction(action, exp) {
    if (typeof logExp === 'function') {
      logExp(`学伴互动·${action.id}`, exp)
    } else if (typeof grantExp === 'function') {
      grantExp(exp)
    }
    showBubble(t(action.bubbleKey), 'action')
    showBubble(t('pet.toast.exp', { n: exp }), 'action', 1800)
  },
  onCozyBubble(name) {
    showBubble(t('pet.toast.cozy', { name }), 'cozy', 3000)  },
  onIdleBubble() {
    const keys = ['pet.idle.1', 'pet.idle.2', 'pet.idle.3', 'pet.idle.4']
    const text = t(keys[Math.floor(Math.random() * keys.length)])
    showBubble(text, 'idle', 4000)  },
})

function actionLabel(action) {
  return t(action.nameKey)
}

function handleMenuAction(action) {
  const res = interaction.runAction(action)
  if (!res.success) {
    showBubble(t('pet.toast.cooldown', { name: actionLabel(action), s: res.remaining }), 'cooldown', 1500)  }
}
</script>

<template>
  <Teleport to="body">
    <aside
      v-if="visible && hasPet"
      ref="buddyEl"
      class="buddy"
      :class="{ pulse: pulsing, dragging, 'dock-left': dock === 'left', 'dock-right': dock === 'right' }"
      :style="buddyStyle"
      :aria-label="t('petCompanion.1')"
      role="button"
      tabindex="0"
      @keydown="onKey"
    >
      <div v-show="!dock" class="hud" :class="{ 'hud-on': hudOn }">
        <div class="row">
          <span>Lv {{ pet.level }}</span>
        </div>
        <div
          class="bar"
          role="progressbar"
          :aria-valuenow="pet.exp"
          :aria-valuemin="0"
          :aria-valuemax="need"
          :aria-label="t('petCompanionX.1') + pet.exp + ' / ' + need"
        >
          <i :style="{ width: pct(ratio) + '%' }" />
        </div>
      </div>
      <div
        class="sprite-in"
        :key="pet.form"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerCancel"
        @mouseenter="showHud"
        @mouseleave="hideHud"
      >
        <PetSprite :pet-id="pet.id" :form="pet.form" :size="spriteSize" />
      </div>
      <p v-if="showTuckHint && !dock" class="tuck-hint" role="status">{{ t('pet.tuck') }}</p>
      <!-- 双击互动菜单：摸摸 / 喂食 / 玩耍 -->
      <div
        v-if="!dock && showActionMenu"
        class="interaction-menu"
        role="menu"
        :aria-label="t('pet.menu.label')"
      >
        <div class="menu-head">
          <span class="menu-title">{{ t('pet.menu.title', { name: displayName }) }}</span>
          <button type="button" class="menu-x" @click.stop="showActionMenu = false">×</button>
        </div>
        <div class="menu-list">
          <button
            v-for="act in interaction.actions"
            :key="act.id"
            type="button"
            class="menu-item"
            :class="{ disabled: !interaction.canRun(act.id) }"
            @click.stop="handleMenuAction(act)"
          >
            <span class="item-name">{{ actionLabel(act) }}</span>
            <span class="item-exp">+{{ act.exp }} exp</span>
            <span v-if="!interaction.canRun(act.id)" class="item-cd">
              {{ interaction.getRemainingCooldown(act.id) }}s
            </span>
          </button>
        </div>
      </div>
      <!-- 提醒气泡跟着立绘走。贴左缘时翻到右侧，贴右缘时翻到左侧，避免挤进边缝。 -->
      <div
        v-if="bubbleText"
        class="bubble"
        :class="['bubble-' + bubbleKind, dock ? 'bubble-dock' : '']"
        role="status"
        aria-live="polite"
      >{{ bubbleText }}</div>
    </aside>

    <div
      v-if="visible && hasPet && showEvolve"
      class="mask"
      role="dialog"
      :aria-label="t('petCompanion.2')"
    >
      <div class="card">
        <h3>学伴宠物升到了 {{ pet.level }} 级</h3>
        <p>{{ t('petCompanion.5') }}</p>
        <div class="pair">
          <button type="button" class="ghost" @click="keepForm">{{ t('petCompanion.6') }}</button>
          <button type="button" class="ok" @click="evolve">{{ t('petCompanion.7') }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.buddy {
  position: fixed;
  right: 16px;
  bottom: 56px;
  z-index: 80;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  /* 整块不接指针：HUD 收起时那块占位要能点穿到底下的按钮 */
  pointer-events: none;
  /* 贴边改位移不改宽度；拖动改的是 left/top，跟手不拖影 */
  transition: transform 0.22s ease;
}

/* 贴边探头：缩小立绘、米底边签，略叠进边缝，点一下拉回。 */
.buddy.dock-left,
.buddy.dock-right {
  gap: 0;
}

.buddy.dock-left {
  --peek-dir: 1;
  align-items: flex-start;
  transform: translateX(-8px);
}

.buddy.dock-right {
  --peek-dir: -1;
  align-items: flex-end;
  transform: translateX(8px);
}

.buddy.dock-left .sprite-in,
.buddy.dock-right .sprite-in {
  background: rgba(var(--bg-app-rgb), 0.92);
  border: 1px solid var(--border);
  opacity: 0.92;
}

.buddy.dock-left .sprite-in {
  border-left: none;
  border-right: 2px solid #e51520;
  border-radius: 0 12px 12px 0;
}

.buddy.dock-right .sprite-in {
  border-right: none;
  border-left: 2px solid #e51520;
  border-radius: 12px 0 0 12px;
}

.tuck-hint {
  pointer-events: none;
  align-self: flex-end;
  max-width: 168px;
  margin: 0;
  padding: 6px 8px;
  background: rgba(var(--bg-app-rgb), 0.96);
  border: 1px solid var(--border);
  border-left: 2px solid #e51520;
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.5;
}

/* 桌面悬停探头时再多露一点，看清是谁在往外看。
   触控设备没有 hover，走点按展开那条路。 */
@media (hover: hover) and (pointer: fine) {
  .buddy.dock-left .sprite-in:hover,
  .buddy.dock-right .sprite-in:hover {
    opacity: 1;
  }
}

.buddy:focus-visible {
  outline: 2px solid #e51520;
  outline-offset: 6px;
  border-radius: 6px;
}

.hud {
  min-width: 108px;
  padding: 6px 8px 7px;
  background: rgba(var(--bg-app-rgb), 0.92);
  border: 1px solid var(--border);
  border-radius: 4px;
  /* HUD 是只读信息，且收起时那块占位必须点穿 */
  pointer-events: none;
  /* 默认收起：位置照旧占着（显形时不跳版），只是看不见、也不进无障碍树 */
  opacity: 0;
  visibility: hidden;
  transform: translateY(4px);
  transition: opacity 0.16s ease, transform 0.16s ease, visibility 0s linear 0.16s;
}

/* 鼠标移到宠物本体上 / 键盘焦点落在这块 / 升级 pulse 那一下，才显形 */
.hud.hud-on {
  opacity: 1;
  visibility: visible;
  transform: none;
  transition: opacity 0.16s ease, transform 0.16s ease, visibility 0s;
}

.row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
}

/* 行里只剩 Lv 数字了，给它衬线 + 深色，让它自己站得住 */
.row span {
  font-family: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  font-weight: 400;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.bar {
  margin-top: 5px;
  height: 4px;
  background: var(--border);
  overflow: visible;
}

.bar i {
  display: block;
  height: 100%;
  background: #e51520;
  transition: width 0.4s ease;
}

/* ---------- 互动气泡（双击/长按/闲置） ----------
   放在宠物本体上方，米底卡片、深色文字、左侧 2px 红色条与品牌色一致；
   出现时由下往上轻微浮入（不用 transform: scale 那种大动作，免得遮 HUD）。 */
.bubble {
  pointer-events: none;
  position: absolute;
  right: calc(100% + 4px);
  bottom: 0;
  width: max-content;
  max-width: min(220px, calc(100vw - 96px));
  margin: 0;
  padding: 1px 3px;
  background: rgba(var(--bg-app-rgb), 0.96);
  border: 1px solid var(--border);
  border-left: 2px solid #e51520;
  border-radius: 3px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
  line-height: 1.25;
  white-space: normal;
  word-break: break-all;
  box-shadow: 0 2px 6px rgba(25, 25, 25, 0.08);
  animation: bubble-in 0.18s ease-out;
}
/* 贴左缘时翻到右侧，否则气泡会伸到屏幕外面。贴右缘沿用左侧默认位置。 */
.buddy.dock-left .bubble.bubble-dock {
  right: auto;
  left: calc(100% + 4px);
}
.bubble-cozy {
  border-left-color: #d36b7a; /* 撒娇用粉，避免每次都是红 */
}
.bubble-idle {
  border-left-color: #4f9a5c; /* 闲置提醒用草绿 */
}
.bubble-cooldown {
  border-left-color: #8a8a8a; /* 冷却中灰 */
}
@keyframes bubble-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 探头里不上下飞：改成轻轻探出探进，方向跟着贴的那一侧（--peek-dir）。
   放在 .buddy.pulse 之前，升级那 1.8 秒照旧让闪光接管。 */
.buddy.dock-left .sprite-in,
.buddy.dock-right .sprite-in {
  animation: sprite-in 0.5s ease, buddy-peek 3.2s ease-in-out infinite;
}

@keyframes buddy-peek {
  0%,
  100% {
    transform: translateX(0) translateY(8px) scale(0.9);
  }
  50% {
    transform: translateX(calc(var(--peek-dir, 1) * 4px)) translateY(8px) scale(0.9);
  }
}

/* ---------- 升级反馈（.buddy.pulse，纯 CSS） ---------- */
@keyframes bar-glow {
  0%,
  100% {
    box-shadow: none;
  }
  50% {
    box-shadow: 0 0 8px 2px rgba(229, 21, 32, 0.55);
  }
}

@keyframes lv-pop {
  0% {
    color: #191919;
    transform: none;
  }
  20% {
    color: #e51520;
    transform: scale(1.25);
  }
  70% {
    color: #e51520;
    transform: none;
  }
  100% {
    color: #191919;
  }
}

@keyframes body-flash {
  0%,
  100% {
    filter: none;
  }
  50% {
    filter: brightness(1.8) saturate(1.4);
  }
}

.buddy.pulse .bar {
  animation: bar-glow 0.45s ease 2;
}

.buddy.pulse .row span {
  animation: lv-pop 1.6s ease;
}

.buddy.pulse .sprite-in {
  animation: body-flash 0.55s ease 2, buddy-idle 2.4s ease-in-out infinite;
}

/* ---------- 立绘：整块里唯一接指针的地方 ---------- */
.sprite-in {
  pointer-events: auto;
  cursor: pointer;
  touch-action: none; /* 触屏按住拖动时不要带着页面一起滚 */
  animation: sprite-in 0.5s ease, buddy-idle 2.4s ease-in-out infinite;
}

/* 很轻的呼吸式跳动，表示还活着：幅度 3px，不上下飞也不挡字 */
@keyframes buddy-idle {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-3px);
  }
}

/* 拖动时不抖、光标变抓握（写在 pulse 之后：两条同时命中时以拖动为准） */
.buddy.dragging .sprite-in {
  cursor: grabbing;
  animation: none;
}

@keyframes sprite-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.mask {
  position: fixed;
  inset: 0;
  z-index: 118;
  background: rgba(25, 25, 25, 0.28);
  display: grid;
  place-items: center;
  padding: 16px;
}

.card {
  width: min(360px, 100%);
  background: var(--bg-app);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 18px 14px;
}

h3 {
  margin: 0;
  font-family: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  font-size: 18px;
  font-weight: 400;
}

p {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.pair {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.ghost,
.ok {
  border-radius: 1000px;
  padding: 7px 14px;
  font-size: 13px;
}

.ghost {
  border: 1px solid var(--border);
  background: var(--bg-card);
}

.ok {
  border: 1px solid #e51520;
  background: #e51520;
  color: #fff;
}

.ghost:focus-visible,
.ok:focus-visible {
  outline: 2px solid #e51520;
  outline-offset: 3px;
}

/* ---------- 双击互动菜单 ---------- */
.interaction-menu {
  pointer-events: auto;
  align-self: flex-end;
  min-width: 148px;
  background: rgba(var(--bg-app-rgb), 0.98);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(25, 25, 25, 0.12);
  padding: 8px 10px 10px;
  margin-bottom: 4px;
  animation: bubble-in 0.18s ease-out;
}
.menu-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 6px;
  border-bottom: 1px solid #ece7df;
  margin-bottom: 6px;
}
.menu-title {
  font-size: 11px;
  color: #7a7369;
  font-weight: 500;
}
.menu-x {
  background: none;
  border: none;
  font-size: 15px;
  line-height: 1;
  color: #999;
  cursor: pointer;
  padding: 0 2px;
}
.menu-x:hover {
  color: var(--text-primary);
}
.menu-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.menu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 9px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-primary);
  transition: all 0.15s ease;
}
.menu-item:hover:not(.disabled) {
  border-color: #e51520;
  background: #fdf5f5;
}
.menu-item.disabled {
  opacity: 0.6;
  cursor: not-allowed;
  background: #f5f3f0;
}
.item-name {
  font-weight: 500;
}
.item-exp {
  font-size: 10px;
  color: #e51520;
  font-weight: 600;
  margin-left: 6px;
}
.item-cd {
  font-size: 10px;
  color: #888;
  margin-left: auto;
  padding-left: 6px;
}

/* 窄屏（393 这类常见手机宽度也算）：立绘再小一档（尺寸走 spriteSize，不用 scale），
   位置抬一点别压在底栏上。拖过之后以 left/top 为准，这条不再生效。 */
@media (max-width: 430px) {
  .buddy {
    right: 6px;
    bottom: 84px;
    gap: 4px;
    --peek: 34px; /* 手机上立绘更小，探头也相应窄一点，但要够手指点 */
    --peek-hover: 48px;
  }

  .hud {
    min-width: 92px;
    padding: 5px 7px 6px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .bar i {
    transition: none;
  }

  .hud,
  .hud.hud-on {
    transition: none;
  }

  /* 系统开了减少动效：不跳，探头也不要滑出动画 */
  .buddy {
    transition: none;
  }

  .buddy.pulse .bar,
  .buddy.pulse .row span,
  .buddy.pulse .sprite-in,
  .buddy.dock-left .sprite-in,
  .buddy.dock-right .sprite-in,
  .sprite-in {
    animation: none;
  }
}
</style>
