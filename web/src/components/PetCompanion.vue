<script setup>
/**
 * 主界面右下常驻学伴（头脑的化身）。z-index 低于弹窗（120+），高于正文。
 * 不挡顶栏、不挡左下「空间」、不挡自习大窗；390 宽缩小。
 *
 * 点击 aside 整体（HUD + 经验条 + 本体）触发 emit 'open-profile'，
 * 由父组件 App.vue 弹 PetProfileDialog（z-index 155）。
 * Lv5「保持 / 进化」弹层（showEvolve，z-index 118）走原逻辑，与本 emit 互不干扰。
 */
import { ref, watch } from 'vue'
import PetSprite from './PetSprite.vue'
import { usePet } from '@/composables/usePet'

defineProps({
  visible: { type: Boolean, default: true },
})

const emit = defineEmits(['open-profile'])

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
} = usePet()

const pct = (n) => Math.round((n || 0) * 100)

function openProfile() {
  emit('open-profile')
}

function onKey(e) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    emit('open-profile')
  }
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
</script>

<template>
  <Teleport to="body">
    <aside
      v-if="visible && hasPet"
      class="buddy"
      :class="{ pulse: pulsing }"
      aria-label="学伴宠物，点击查看档案"
      role="button"
      tabindex="0"
      @click="openProfile"
      @keydown="onKey"
    >
      <div class="hud">
        <div class="row">
          <b>学伴宠物</b>
          <span>Lv {{ pet.level }}</span>
        </div>
        <p class="exp-cap">学伴宠物经验</p>
        <div
          class="bar"
          role="progressbar"
          :aria-valuenow="pet.exp"
          :aria-valuemin="0"
          :aria-valuemax="need"
          :aria-label="'学伴宠物经验 ' + pet.exp + ' / ' + need"
        >
          <i :style="{ width: pct(ratio) + '%' }" />
        </div>
      </div>
      <div class="sprite-in" :key="pet.form">
        <PetSprite :pet-id="pet.id" :form="pet.form" :size="72" />
      </div>
    </aside>

    <div
      v-if="visible && hasPet && showEvolve"
      class="mask"
      role="dialog"
      aria-label="学伴宠物升级"
    >
      <div class="card">
        <h3>学伴宠物升到了 {{ pet.level }} 级</h3>
        <p>
          可以保持现在的形态，也可以换上进阶形态。
          进阶形态只是外观变化，能力不变，等级和经验都保留。
        </p>
        <div class="pair">
          <button type="button" class="ghost" @click="keepForm">保持学伴宠物形态</button>
          <button type="button" class="ok" @click="evolve">学伴宠物继续进化</button>
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
  cursor: pointer;
}

.buddy:focus-visible {
  outline: 2px solid #e51520;
  outline-offset: 6px;
  border-radius: 6px;
}

.hud {
  min-width: 108px;
  padding: 6px 8px 7px;
  background: rgba(251, 249, 246, 0.92);
  border: 1px solid var(--border);
  border-radius: 4px;
  pointer-events: auto;
}

.row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
}

.row b {
  font-family: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  font-weight: 400;
  color: var(--text-primary);
}

.exp-cap {
  margin: 4px 0 0;
  font-size: 10px;
  color: #8c857c;
  letter-spacing: 0.02em;
}

.bar {
  margin-top: 5px;
  height: 4px;
  background: #e4ded5;
  overflow: visible;
}

.bar i {
  display: block;
  height: 100%;
  background: #e51520;
  transition: width 0.4s ease;
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
    color: var(--text-primary);
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
    color: var(--text-primary);
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
  animation: body-flash 0.55s ease 2;
}

/* ---------- 进化形象切换淡入 ---------- */
.sprite-in {
  animation: sprite-in 0.5s ease;
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

@media (max-width: 390px) {
  .buddy {
    right: 8px;
    bottom: 92px;
    transform: scale(0.82);
    transform-origin: bottom right;
  }
}

@media (prefers-reduced-motion: reduce) {
  .bar i {
    transition: none;
  }

  .buddy.pulse .bar,
  .buddy.pulse .row span,
  .buddy.pulse .sprite-in,
  .sprite-in {
    animation: none;
  }
}
</style>
