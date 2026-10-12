<script setup>
/**
 * PetGuide —— 欢迎层之前的角色引导（全屏覆盖）
 * 气质：欢迎一位麻瓜踏进会施法的世界。点题只用「麻瓜」「魔法」。
 * 选中一位化身才能继续；选择写入 zjxt.pet，下次不再出现。
 */
import { ref } from 'vue'
import { useI18n } from '@/i18n'
import PetSprite from './PetSprite.vue'
import { usePet } from '@/composables/usePet'

const emit = defineEmits(['done'])
const { t } = useI18n()

const { PETS, choosePet } = usePet()
const picked = ref('')

function confirm() {
  if (!picked.value) return
  choosePet(picked.value)
  emit('done')
}

function petName(p) {
  return t('pet.' + p.id + '.name')
}
function petTrait(p) {
  return t('pet.' + p.id + '.personality') + ' · ' + t('pet.' + p.id + '.tagline')
}
function petEvolved(p) {
  return t('pet.' + p.id + '.evolved')
}
</script>

<template>
  <Teleport to="body">
    <div class="guide" role="dialog" :aria-label="t('petGuide.1')">
      <div class="inner">
        <p class="wordmark">LUMEN</p>
        <h1 class="title">{{ t('petGuide.3') }}</h1>
        <p class="lead">{{ t('petGuide.4') }}<br />{{ t('petGuide.5') }}<br />{{ t('petGuide.6') }}</p>

        <div class="pick">
          <h2 class="pick-title">{{ t('petGuide.7') }}</h2>
          <div class="cards" role="radiogroup" :aria-label="t('petGuide.2')">
            <button
              v-for="p in PETS"
              :key="p.id"
              type="button"
              class="card"
              :class="{ on: picked === p.id }"
              role="radio"
              :aria-checked="picked === p.id"
              @click="picked = p.id"
              @dblclick="picked = p.id; confirm()"
            >
              <PetSprite :pet-id="p.id" form="base" :size="88" />
              <b>{{ petName(p) }}</b>
              <span>{{ petTrait(p) }}</span>
              <details class="evo" @click.stop @dblclick.stop @pointerdown.stop>
                <summary>{{ t('petGuide.evo') }}</summary>
                <p class="evo-sec">{{ t('petGuide.lv15') }}</p>
                <ol class="evo-path evo-lv15">
                  <li class="evo-stage">
                    <PetSprite :pet-id="p.id" form="base" :size="28" />
                    <em>Lv1</em>
                    <em>{{ petName(p) }}</em>
                  </li>
                  <li class="evo-stage">
                    <PetSprite :pet-id="p.id" form="base" :size="32" />
                    <em>Lv2</em>
                    <em>{{ t('petGuide.grow') }}</em>
                  </li>
                  <li class="evo-stage">
                    <PetSprite :pet-id="p.id" form="base" :size="36" />
                    <em>Lv3</em>
                    <em>{{ t('petGuide.grow') }}</em>
                  </li>
                  <li class="evo-stage">
                    <PetSprite :pet-id="p.id" form="base" :size="40" />
                    <em>Lv4</em>
                    <em>{{ t('petGuide.grow') }}</em>
                  </li>
                  <li class="evo-stage">
                    <PetSprite :pet-id="p.id" form="evolved" :size="44" />
                    <em>Lv5</em>
                    <em>{{ petEvolved(p) }}</em>
                  </li>
                </ol>
                <p class="evo-sec">{{ t('petGuide.lv30') }}</p>
                <div class="evo-path evo-lv30">
                  <span class="evo-stage">
                    <PetSprite :pet-id="p.id" form="evolved" :size="48" />
                    <em>Lv30</em>
                    <em>{{ petEvolved(p) }} · {{ t('petGuide.ultimate') }}</em>
                  </span>
                </div>
                <p class="evo-sec">{{ t('petGuide.xp') }}</p>
                <ul class="evo-xp">
                  <li>{{ t('petGuide.xp1') }}</li>
                  <li>{{ t('petGuide.xp2') }}</li>
                  <li>{{ t('petGuide.xp3') }}</li>
                  <li>{{ t('petGuide.xp4') }}</li>
                </ul>
              </details>
            </button>
          </div>
        </div>

        <button type="button" class="go" :disabled="!picked" @click="confirm">
          {{ picked ? t('petGuideX.1') : t('petGuideX.2') }}
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.guide {
  position: fixed;
  inset: 0;
  z-index: 175;
  overflow-y: auto;
  background: var(--bg-app);
  color: var(--text-primary);
  animation: guide-in 0.24s ease both;
}

.inner {
  min-height: 100svh;
  max-width: 760px;
  margin: 0 auto;
  padding: 12vh 24px 48px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.wordmark {
  margin: 0;
  font-family: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  font-size: 15px;
  letter-spacing: 0.34em;
  color: #e51520;
}

.title {
  margin: 18px 0 0;
  font-family: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  font-weight: 400;
  font-size: clamp(30px, 6vw, 44px);
  line-height: 1.25;
}

.lead {
  margin: 18px auto 0;
  max-width: 34em;
  font-size: 14.5px;
  line-height: 1.9;
  color: var(--text-secondary);
}

.pick {
  margin-top: 7vh;
  width: 100%;
}

.pick-title {
  margin: 0 0 18px;
  font-size: 13px;
  font-weight: 400;
  letter-spacing: 0.12em;
  color: #808080;
}

.cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  max-width: 620px;
  margin: 0 auto;
}

.card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 22px 12px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.card b {
  font-family: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  font-weight: 400;
  font-size: 16px;
}

.card span {
  font-size: 12px;
  color: #808080;
}

.card.on {
  border-color: #e51520;
  box-shadow: 0 6px 18px rgba(229, 21, 32, 0.12);
  transform: translateY(-2px);
}

.card:focus-visible {
  outline: 2px solid #e51520;
  outline-offset: 3px;
}

.go {
  margin-top: 34px;
  padding: 12px 44px;
  border: 1px solid #e51520;
  border-radius: 1000px;
  background: #e51520;
  color: #fff;
  font-size: 15px;
  letter-spacing: 0.06em;
  box-shadow: 0 5px 10px rgba(0, 0, 0, 0.15);
  cursor: pointer;
}

.go:disabled {
  border-color: var(--border);
  background: var(--bg-disabled);
  color: #a39b92;
  box-shadow: none;
  cursor: default;
}

.go:focus-visible {
  outline: 2px solid #e51520;
  outline-offset: 3px;
}

.evo {
  width: 100%;
  margin-top: 4px;
  border-top: 1px dashed var(--border, #e4ded5);
  padding-top: 8px;
  text-align: left;
  pointer-events: auto;
}
.evo > summary {
  list-style: none;
  cursor: pointer;
  font-size: 11.5px;
  color: var(--text-muted, #808080);
  letter-spacing: 0.04em;
  padding: 2px 0;
  user-select: none;
}
.evo > summary::-webkit-details-marker {
  display: none;
}
.evo > summary::before {
  content: "▸ ";
  display: inline-block;
}
.evo[open] > summary::before {
  content: "▾ ";
}
.evo-sec {
  margin: 10px 0 4px;
  font-size: 10.5px;
  letter-spacing: 0.08em;
  color: var(--text-muted, #808080);
}
.evo-path {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
  flex-wrap: wrap;
}
.evo-lv15 .evo-stage {
  flex: 1 1 0;
  min-width: 0;
}
.evo-lv30 {
  justify-content: center;
}
.evo-stage {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.evo-stage em {
  font-style: normal;
  font-size: 10px;
  line-height: 1.2;
  color: var(--text-secondary, #4a4540);
  text-align: center;
}
.evo-xp {
  margin: 0 0 2px;
  padding: 0 0 0 1.1em;
  font-size: 10.5px;
  line-height: 1.55;
  color: var(--text-muted, #808080);
}
.evo-xp li {
  margin: 0;
}

@keyframes guide-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@media (max-width: 430px) {
  .cards {
    grid-template-columns: repeat(2, 1fr);
    max-width: 340px;
    gap: 10px;
  }

  .card {
    padding: 16px 8px 14px;
  }

  .card b {
    font-size: 14px;
  }

  .inner {
    padding-top: 8vh;
  }
}

@media (prefers-reduced-motion: reduce) {
  .guide {
    animation: none;
  }

  .card {
    transition: none;
  }
}
</style>
