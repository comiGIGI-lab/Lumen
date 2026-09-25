<script setup>
/**
 * SpacePanel —— 个人空间设置：开关三个悬浮窗，大小已随窗口操作写入 localStorage。
 * 兼有当前学伴宠物展示：性格 / 学习类型只读、升级经验条、更换学伴宠物。
 */
import { computed } from 'vue'
import { useSpace } from '@/composables/useSpace'
import { usePet } from '@/composables/usePet'

const { WIN_IDS, WIN_META, windows, panelOpen, setOn, resetLayout } = useSpace()
const { PETS, pet, hasPet, displayName, need, ratio, speciesOf, changeAvatar } = usePet()

/** 当前化身的 PETS 条目（含 personality/learningStyle/tagline） */
const currentSpecies = computed(() => speciesOf(pet.id))

function close() {
  panelOpen.value = false
}
</script>

<template>
  <Teleport to="body">
  <div class="mask" @click.self="close">
    <div class="card" role="dialog" aria-label="个人空间">
      <header>
        <h3>个人空间</h3>
        <button type="button" class="x" aria-label="关闭" @click="close">×</button>
      </header>
      <p class="lead">开关三个组件。大小、折叠和位置会记在这台浏览器里，没有账号。</p>
      <ul>
        <li v-for="id in WIN_IDS" :key="id">
          <label>
            <input type="checkbox" :checked="windows[id].on" @change="setOn(id, $event.target.checked)" />
            <span>{{ WIN_META[id].title }}</span>
          </label>
          <em>{{ windows[id].collapsed ? '已收起' : '大小 ' + windows[id].size }}</em>
        </li>
      </ul>

      <div v-if="hasPet" class="avatar">
        <p class="who">当前学伴宠物 · {{ displayName }}</p>
        <!-- 性格与学习类型：只读静态展示，要换请走下方「更换学伴宠物」 -->
        <section class="traits" aria-label="性格与学习类型">
          <h4>性格与学习类型</h4>
          <div class="trait-row">
            <div class="trait">
              <span class="k">性格</span>
              <span class="v">{{ currentSpecies?.personality || '—' }}</span>
            </div>
            <div class="trait">
              <span class="k">学习类型</span>
              <span class="v">{{ currentSpecies?.learningStyle || '—' }}</span>
            </div>
          </div>
          <p class="hint">文案不可编辑。要换请走下方「更换学伴宠物」。</p>
        </section>
        <!-- 升级经验条 -->
        <section class="exp" aria-label="升级经验">
          <div class="exp-head">
            <span>Lv {{ pet.level }}</span>
            <span>{{ pet.exp }} / {{ need }}</span>
          </div>
          <div class="exp-bar" :aria-valuenow="pet.exp" :aria-valuemin="0" :aria-valuemax="need" role="progressbar">
            <i :style="{ width: Math.round((ratio || 0) * 100) + '%' }" />
          </div>
        </section>

        <p class="change-label">更换学伴宠物</p>
        <div class="picks">
          <button
            v-for="p in PETS"
            :key="p.id"
            type="button"
            :class="{ on: pet.id === p.id }"
            @click="changeAvatar(p.id)"
          >{{ p.name }}</button>
        </div>
      </div>

      <div class="foot">
        <button type="button" class="ghost" @click="resetLayout">恢复默认位置</button>
        <button type="button" class="ok" @click="close">完成</button>
      </div>
    </div>
  </div>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 160;
  background: rgba(25, 25, 25, 0.28);
  display: grid;
  place-items: center;
  padding: 16px;
}

.card {
  width: min(380px, 100%);
  background: var(--bg-app);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 16px 18px 14px;
  box-shadow: var(--shadow);
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

h3 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 400;
}

.x {
  border: none;
  background: transparent;
  font-size: 20px;
  color: var(--text-muted);
}

.lead {
  margin: 8px 0 14px;
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.6;
}

ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-top: 1px solid var(--border);
}

label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

em {
  font-style: normal;
  font-size: 12px;
  color: var(--text-muted);
}

.avatar {
  margin-top: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.who {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--text-secondary);
}

/* 性格与学习类型：只读静态展示 */
.traits {
  margin: 0 0 12px;
  padding: 10px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
}

.traits h4 {
  margin: 0 0 8px;
  font-family: var(--font-serif);
  font-size: 13.5px;
  font-weight: 400;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
}

.trait-row {
  display: flex;
  gap: 10px;
}

.trait {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  background: var(--bg-soft);
  border-radius: 6px;
}

.trait .k {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.06em;
}

.trait .v {
  font-family: var(--font-serif);
  font-size: 14.5px;
  font-weight: 400;
  color: var(--text-primary);
}

.traits .hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
}

/* 升级经验条 */
.exp {
  margin: 0 0 12px;
}

.exp-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 5px;
}

.exp-head span:first-child {
  font-family: var(--font-serif);
  font-size: 14px;
  color: var(--text-primary);
}

.exp-bar {
  height: 4px;
  background: var(--border);
  border-radius: 1000px;
  overflow: hidden;
}

.exp-bar i {
  display: block;
  height: 100%;
  background: var(--primary);
  transition: width 0.4s ease;
}

.change-label {
  margin: 0 0 8px;
  font-weight: 500;
  font-size: 12.5px;
  color: var(--text-secondary);
}

.picks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.picks button {
  border: 1px solid var(--border);
  background: var(--bg-card);
  border-radius: 1000px;
  padding: 4px 10px;
  font-size: 12px;
}

.picks button.on {
  border-color: var(--primary);
  color: var(--primary);
}

.foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 12px;
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
  border: 1px solid var(--primary);
  background: var(--primary);
  color: #fff;
}

@media (prefers-reduced-motion: reduce) {
  .exp-bar i {
    transition: none;
  }
}
</style>