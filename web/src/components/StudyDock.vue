<script setup>
/**
 * StudyDock —— 自习坞窗口内容
 * 场景只换背景；声音在「专注设置」里叠加。
 * 定时器开始才播当前组合，暂停静音，再开始接着响。
 */
import { ref, watch } from 'vue'
import { SCENES } from '@/study/catalog'
import { useStudyTimer } from '@/composables/useStudyTimer'

const emit = defineEmits(['scene-change'])

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

const panel = ref('') // '' | scene | focus
const customDraft = ref(String(customMin.value))

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
  panel.value = panel.value === name ? '' : name
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
  <div class="study">
    <div class="top">
      <span class="clock" :class="{ on: running }">{{ clock }}</span>
      <button type="button" class="act" :class="{ run: running }" @click="toggle">
        {{ running ? '暂停' : '开始' }}
      </button>
    </div>

    <div class="dur" role="group" aria-label="专注时长">
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
      >
        自定义
      </button>
    </div>
    <label v-if="usingCustom" class="custom">
      <span>分钟</span>
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

    <div class="row-btns">
      <button type="button" class="chip" :class="{ on: panel === 'scene' || !!sceneId }" @click="togglePanel('scene')">
        场景
      </button>
      <button type="button" class="chip" :class="{ on: panel === 'focus' }" @click="togglePanel('focus')">
        专注设置
        <em v-if="mixCount">{{ mixCount }}</em>
      </button>
    </div>

    <div v-if="panel === 'scene'" class="grid">
      <p class="hint">只换背景，不改声音</p>
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

    <div v-if="panel === 'focus'" class="mix">
      <p class="hint">环境声可叠加，每路独立音量。定时器开始才出声</p>
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
      <p class="hint music-hint">纯音乐三选一，可与环境声同时开，两首纯音乐不能一起响</p>
      <div class="music-picks" role="group" aria-label="纯音乐">
        <button
          type="button"
          class="chip"
          :class="{ on: !musicId }"
          @click="pickMusic('')"
        >
          关闭
        </button>
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
        <span>音量</span>
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
  background: #fff;
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
  background: #fff;
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

.dur,
.row-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.custom {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--text-secondary);
}

.custom input {
  width: 72px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 8px;
  background: #fff;
}

.hint {
  grid-column: 1 / -1;
  margin: 0 0 4px;
  font-size: 12px;
  color: var(--text-muted);
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
  background: #fff;
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
