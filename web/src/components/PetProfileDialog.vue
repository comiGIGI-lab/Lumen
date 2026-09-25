<script setup>
/**
 * PetProfileDialog —— 宠物档案弹层（点击宠物本体 / HUD / 经验条触发）
 *
 * 与 Lv5 「保持 / 进化」弹层（PetCompanion 内部 showEvolve）互不冲突：
 * 那个弹层走 usePet.showEvolve，z-index 118；本弹层 z-index 155（盖悬浮窗 140 不盖总览 160）。
 *
 * 内容字段（从上到下）：
 *   - 化身头像 96×96 + 名字 + 形态（基础/进阶）
 *   - 等级 + 经验值进度条
 *   - 性格 + 学习类型（两 pill 并排）
 *   - 连签信息「连签 X 天 · 找回池 N」
 *   - 升级时间一行（仅已进化到进阶形态时显示）
 *   - 成长记录最近 10 条倒序
 * 底部两按钮：
 *   - 知道了（emit close）
 *   - 更换学伴宠物（emit change-pet）
 */
import { computed } from 'vue'
import PetSprite from './PetSprite.vue'
import { usePet } from '@/composables/usePet'

const props = defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'change-pet'])

const {
  pet,
  hasPet,
  displayName,
  need,
  ratio,
  speciesOf,
  STREAK_POOL_MAX,
} = usePet()

const currentSpecies = computed(() => speciesOf(pet.id))
const formLabel = computed(() => (pet.form === 'evolved' ? '进阶形态' : '基础形态'))
const ratioPct = computed(() => Math.round((ratio.value || 0) * 100))

/** 升级时间（仅已进化） */
const evolvedAtText = computed(() => {
  if (!pet.evolvedAt) return ''
  const d = new Date(pet.evolvedAt)
  if (isNaN(d.getTime())) return ''
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
})

/** 成长记录：最近 10 条，倒序 */
const expLogRecent = computed(() => {
  const arr = Array.isArray(pet.expLog) ? pet.expLog : []
  return arr.slice(-10).reverse()
})

/** ISO → 'YYYY-MM-DD HH:MM' */
function formatTime(iso) {
  if (!iso || typeof iso !== 'string') return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
</script>

<template>
  <transition name="dlg">
    <div v-if="open && hasPet" class="mask" @click.self="emit('close')">
      <div class="dialog" role="dialog" aria-modal="true" aria-label="学伴宠物档案">
        <header>
          <h3>学伴宠物档案</h3>
          <button class="x" type="button" aria-label="关闭" @click="emit('close')">✕</button>
        </header>

        <div class="body">
          <!-- 化身头像 + 名字 + 形态 -->
          <section class="head">
            <div class="avatar">
              <PetSprite :pet-id="pet.id" :form="pet.form" :size="96" />
            </div>
            <div class="head-text">
              <p class="name">{{ displayName }}</p>
              <p class="form">{{ formLabel }}</p>
            </div>
          </section>

          <!-- 等级 + 经验值进度条 -->
          <section class="exp">
            <div class="exp-head">
              <span class="lv">Lv {{ pet.level }}</span>
              <span class="num">{{ pet.exp }} / {{ need }}</span>
            </div>
            <div
              class="bar"
              role="progressbar"
              :aria-valuenow="pet.exp"
              :aria-valuemin="0"
              :aria-valuemax="need"
            >
              <i :style="{ width: ratioPct + '%' }" />
            </div>
          </section>

          <!-- 性格 + 学习类型 pill -->
          <section class="traits">
            <div class="pill">
              <span class="k">性格</span>
              <span class="v">{{ currentSpecies?.personality || '—' }}</span>
            </div>
            <div class="pill">
              <span class="k">学习类型</span>
              <span class="v">{{ currentSpecies?.learningStyle || '—' }}</span>
            </div>
          </section>

          <!-- 连签 + 找回池 -->
          <section class="streak">
            <span>连签 <b>{{ pet.streak }}</b> 天 · 找回池 <b>{{ pet.streakPool }}</b> / {{ STREAK_POOL_MAX }}</span>
          </section>

          <!-- 升级时间（仅已进化） -->
          <section v-if="pet.form === 'evolved'" class="evolved">
            <span class="k">升级时间</span>
            <span class="v">{{ evolvedAtText || '—' }}</span>
          </section>

          <!-- 成长记录最近 10 条倒序 -->
          <section class="log">
            <h4>成长记录</h4>
            <ul v-if="expLogRecent.length">
              <li v-for="(e, idx) in expLogRecent" :key="e.time + '-' + idx">
                <span class="t">{{ formatTime(e.time) }}</span>
                <span class="s">{{ e.source }}</span>
                <span class="a" :class="{ zero: e.amount === 0 }">
                  {{ e.amount > 0 ? '+' : '' }}{{ e.amount }} 经验
                </span>
              </li>
            </ul>
            <p v-else class="empty">还没有成长记录，去自习或生成方案试试。</p>
          </section>
        </div>

        <footer>
          <button class="ghost" type="button" @click="emit('close')">知道了</button>
          <button class="ok" type="button" @click="emit('change-pet')">
            更换学伴宠物
          </button>
        </footer>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 155;
  /* 高于悬浮窗(140)、低于 TourDialog 总览(160) */
  background: rgba(25, 25, 25, 0.32);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 24px;
}

.dialog {
  width: 380px;
  max-width: 100%;
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  background: var(--bg-app);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  font-family: var(--font-sans);
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px 12px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, var(--bg-soft), var(--bg-card));
}

header h3 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 400;
  letter-spacing: 0.04em;
}

.x {
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 16px;
  padding: 2px 8px;
  border-radius: 6px;
  cursor: pointer;
}

.x:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.body {
  padding: 14px 18px 6px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 化身头像 + 名字 + 形态 */
.head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.avatar {
  width: 96px;
  height: 96px;
  flex: none;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  display: grid;
  place-items: center;
}

.head-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.name {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 22px;
  font-weight: 400;
  color: var(--text-primary);
}

.form {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}

/* 等级 + 经验值进度条 */
.exp {
  padding: 10px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
}

.exp-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 6px;
}

.lv {
  font-family: var(--font-serif);
  font-size: 14px;
  color: var(--text-primary);
}

.num {
  font-size: 12px;
  color: var(--text-muted);
}

.bar {
  height: 4px;
  background: var(--border);
  border-radius: 1000px;
  overflow: hidden;
}

.bar i {
  display: block;
  height: 100%;
  background: var(--primary);
  transition: width 0.4s ease;
}

/* 性格 + 学习类型 pill */
.traits {
  display: flex;
  gap: 8px;
}

.pill {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  background: var(--bg-soft);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.pill .k {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.06em;
}

.pill .v {
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 400;
  color: var(--text-primary);
}

/* 连签 */
.streak {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 0 2px;
}

.streak b {
  font-weight: 600;
  color: var(--text-primary);
}

/* 升级时间 */
.evolved {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--bg-soft);
  border-radius: 8px;
  font-size: 12.5px;
}

.evolved .k {
  color: var(--text-muted);
  letter-spacing: 0.06em;
}

.evolved .v {
  font-family: var(--font-mono, var(--font-serif));
  color: var(--text-primary);
}

/* 成长记录 */
.log h4 {
  margin: 4px 0 8px;
  font-family: var(--font-serif);
  font-size: 13.5px;
  font-weight: 400;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
}

.log ul {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-card);
}

.log li {
  display: grid;
  grid-template-columns: 130px 1fr auto;
  gap: 10px;
  padding: 7px 10px;
  font-size: 12px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border);
}

.log li:last-child {
  border-bottom: none;
}

.log .t {
  font-family: var(--font-mono, var(--font-serif));
  font-size: 11px;
  color: var(--text-muted);
}

.log .s {
  color: var(--text-primary);
}

.log .a {
  font-family: var(--font-mono, var(--font-serif));
  color: var(--primary);
  font-weight: 600;
}

.log .a.zero {
  color: var(--text-muted);
  font-weight: 400;
}

.log .empty {
  margin: 0;
  padding: 10px 12px;
  font-size: 12px;
  color: var(--text-muted);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
}

footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px 14px;
  border-top: 1px solid var(--border);
  background: var(--bg-soft);
}

.ghost,
.ok {
  border-radius: 1000px;
  padding: 7px 16px;
  font-size: 13px;
  cursor: pointer;
}

.ghost {
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
}

.ok {
  border: 1px solid var(--primary);
  background: var(--primary);
  color: #fff;
}

.ghost:hover {
  background: var(--bg-hover);
}

.ok:focus-visible,
.ghost:focus-visible,
.x:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.dlg-enter-active,
.dlg-leave-active {
  transition: opacity 0.18s ease;
}

.dlg-enter-from,
.dlg-leave-to {
  opacity: 0;
}

.dlg-enter-active .dialog,
.dlg-leave-active .dialog {
  transition: transform 0.18s ease;
}

.dlg-enter-from .dialog {
  transform: translateX(8px);
}

.dlg-leave-to .dialog {
  transform: translateX(8px);
}

/* 居中/右下：默认靠右，宽度收窄到 360。视口宽度 < 520 时改居中并占满。 */
@media (max-width: 520px) {
  .mask {
    align-items: center;
    padding: 16px;
  }
  .dialog {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .dlg-enter-active,
  .dlg-leave-active,
  .dlg-enter-active .dialog,
  .dlg-leave-active .dialog,
  .bar i {
    transition: none;
  }
}
</style>