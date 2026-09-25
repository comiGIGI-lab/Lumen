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
              <b>{{ p.name }}</b>
              <span>{{ p.personality }}：{{ p.tagline }}</span>
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
