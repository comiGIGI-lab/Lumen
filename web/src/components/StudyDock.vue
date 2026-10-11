<script setup>
/**
 * StudyDock —— 自习坞窗口内容
 * 场景只换背景；声音在「专注设置」里叠加。
 * 定时器开始才播当前组合，暂停静音，再开始接着响。
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import { SCENES } from '@/study/catalog'
import { useStudyTimer } from '@/composables/useStudyTimer'
import { useSpace } from '@/composables/useSpace'

const emit = defineEmits(['scene-change'])
const { t } = useI18n()

const {
  FOCUS_PRESETS,
  SOUNDS,
  MUSIC,
  presetMin,
  customMin,
  usingCustom,
  running,
  volumes,
  sceneId,
  scene,
  musicId,
  musicVolume,
  clock,
  mixCount,
  pickScene,
  pickPreset,
  applyCustom,
  toggle,
  onVolume,
  pickMusic,
  onMusicVolume,
} = useStudyTimer()
const { layoutMode, viewW } = useSpace()

// 横向并列只给自习空间页的电脑端（>860，与自习坞竖排同一断点）。
// 其它页面保持竖排，场景和专注设置互斥，进页不自动展开。
const sideBySide = computed(() => layoutMode.value === 'study' && viewW.value > 860)
const sceneOpen = ref(false)
const focusOpen = ref(false)
const customDraft = ref(String(customMin.value))

watch(
  sideBySide,
  (on) => {
    if (on) {
      sceneOpen.value = true
      focusOpen.value = true
      return
    }
    if (sceneOpen.value && focusOpen.value) focusOpen.value = false
  },
  { immediate: true },
)

watch(
  scene,
  (s) => {
    emit('scene-change', s)
  },
  { immediate: true },
)

function onPickScene(id) {
  pickScene(id)
}

function togglePanel(name) {
  const open = name === 'scene' ? sceneOpen : focusOpen
  const other = name === 'scene' ? focusOpen : sceneOpen
  if (sideBySide.value) {
    open.value = !open.value
    return
  }
  if (open.value) {
    open.value = false
    return
  }
  other.value = false
  open.value = true
}

function onCustomInput(e) {
  customDraft.value = e.target.value
}

function commitCustom() {
  const n = Number(customDraft.value)
  if (!Number.isFinite(n) || n <= 0) {
    customDraft.value = String(customMin.value)
    return
  }
  applyCustom(n)
  customDraft.value = String(customMin.value)
}
</script>

<template>
  <div class="study" :class="{ wide: sideBySide }">
    <div class="top">
      <span class="clock" :class="{ on: running }">{{ clock }}</span>
      <button type="button" class="act" :class="{ run: running }" @click="toggle">
        {{ running ? t('studyDockX.1') : t('studyDockX.2') }}
      </button>
    </div>

    <div class="dur" role="group" :aria-label="t('studyDock.1')">
      <button
        v-for="m in FOCUS_PRESETS"
        :key="m"
        type="button"
        class="chip"
        :class="{ on: !usingCustom && presetMin === m }"
        @click="pickPreset(m)"
      >
        {{ m }}
      </button>
      <button
        type="button"
        class="chip"
        :class="{ on: usingCustom }"
        @click="applyCustom(customMin)"
      >{{ t('studyDock.3') }}</button>
    </div>
    <label v-if="usingCustom" class="custom">
      <span>{{ t('studyDock.4') }}</span>
      <input
        type="number"
        min="1"
        max="180"
        :value="customDraft"
        @input="onCustomInput"
        @change="commitCustom"
        @keydown.enter.prevent="commitCustom"
      />
    </label>

    <div class="panels">
    <div class="panel">
      <button type="button" class="chip panel-name" :class="{ on: sceneOpen || !!sceneId }" :aria-expanded="sceneOpen" @click="togglePanel('scene')">{{ t('studyDock.5') }}</button>
      <div v-if="sceneOpen" class="grid">
      <p class="hint">{{ t('studyDock.7') }}</p>
      <button
        v-for="s in SCENES"
        :key="s.id"
        type="button"
        class="tile"
        :class="{ on: sceneId === s.id }"
        :style="{ '--sky': s.sky, '--glow': s.glow }"
        @click="onPickScene(s.id)"
      >
        <span class="tile-swatch"></span>
        <span>{{ s.name }}</span>
      </button>
    </div>
    </div>

    <div class="panel">
      <button type="button" class="chip panel-name" :class="{ on: focusOpen }" :aria-expanded="focusOpen" @click="togglePanel('focus')">{{ t('studyDock.6') }}<em v-if="mixCount">{{ mixCount }}</em></button>
      <div v-if="focusOpen" class="mix">
      <p class="hint">{{ t('studyDock.8') }}</p>
      <label v-for="s in SOUNDS" :key="s.id" class="mix-row">
        <span>{{ s.name }}</span>
        <input
          type="range"
          min="0"
          max="100"
          :value="volumes[s.id]"
          @input="onVolume(s.id, $event.target.value)"
        />
        <em>{{ volumes[s.id] }}</em>
      </label>
      <p class="hint music-hint">{{ t('studyDock.9') }}</p>
      <div class="music-picks" role="group" :aria-label="t('studyDock.2')">
        <button
          type="button"
          class="chip"
          :class="{ on: !musicId }"
          @click="pickMusic('')"
        >{{ t('studyDock.10') }}</button>
        <button
          v-for="m in MUSIC"
          :key="m.id"
          type="button"
          class="chip"
          :class="{ on: musicId === m.id }"
          @click="pickMusic(m.id)"
        >
          {{ m.name }}
        </button>
      </div>
      <label class="mix-row">
        <span>{{ t('studyDock.11') }}</span>
        <input
          type="range"
          min="0"
          max="100"
          :value="musicVolume"
          @input="onMusicVolume($event.target.value)"
        />
        <em>{{ musicVolume }}</em>
      </label>
    </div>
    </div>
    </div>
  </div>
</template>

<style scoped>
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.clock {
  font-family: var(--font-serif);
  font-size: 28px;
  letter-spacing: 0.08em;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.clock.on {
  color: var(--accent);
}

.act,
.chip {
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-primary);
  border-radius: 1000px;
  padding: 5px 11px;
  font-size: 12px;
}

.act {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}

.act.run {
  background: var(--bg-card);
  color: var(--text-primary);
  border-color: var(--border);
}

.chip.on,
.tile.on {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--primary-soft);
}

.chip em {
  font-style: normal;
  margin-left: 4px;
  font-size: 10px;
}

.dur {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.panel-name {
  align-self: flex-start;
}

.custom {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.custom input {
  width: 72px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 8px;
  background: var(--bg-card);
}

.panels {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hint {
  grid-column: 1 / -1;
  margin: 0 0 4px;
  font-size: 12px;
  color: var(--text-muted);
}

/* 横排只在自习空间页的电脑端。其它页面即使窗口很宽也保持上下叠。 */
.study.wide .panels {
  flex-direction: row;
  align-items: flex-start;
  gap: 16px;
}

.study.wide .panels > .panel {
  flex: 1 1 0;
  min-width: 0;
}

.panel {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}

.panel > .grid,
.panel > .mix {
  width: 100%;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-top: 4px;
}

.tile {
  display: flex;
  align-items: center;
  gap: 8px;
  text-align: left;
  border: 1px solid var(--border);
  background: var(--bg-card);
  border-radius: 10px;
  padding: 6px 8px;
  font-size: 12px;
  color: var(--text-primary);
}

.tile-swatch {
  flex: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background:
    radial-gradient(circle at 30% 30%, var(--glow), transparent 55%),
    var(--sky);
  border: 1px solid rgba(25, 25, 25, 0.12);
}

.mix {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
}

.mix-row {
  display: grid;
  grid-template-columns: 5.2em 1fr 2em;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.mix-row input[type='range'] {
  width: 100%;
  accent-color: var(--accent);
}

.mix-row em {
  font-style: normal;
  font-variant-numeric: tabular-nums;
  font-size: 11px;
  color: var(--text-muted);
  text-align: right;
}

.music-hint {
  margin-top: 6px;
}

.music-picks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

@media (max-width: 430px) {
  .clock {
    font-size: 24px;
  }
  .mix-row {
    grid-template-columns: 4.4em 1fr 2em;
    gap: 6px;
  }
  .tile {
    font-size: 11px;
  }
}
</style>
