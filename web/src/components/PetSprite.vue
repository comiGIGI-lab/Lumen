<script setup>
/**
 * 学伴像素图：优先 /pet/{id}.png（id 为拼音，如 yaya / dengdeng-evo），
 * 没有文件或加载失败则用色块像素占位。
 * 不热链外网。
 */
import { computed, ref, watch } from 'vue'
import { usePet } from '@/composables/usePet'

const props = defineProps({
  petId: { type: String, default: '' },
  form: { type: String, default: 'base' },
  size: { type: Number, default: 72 },
})

const { speciesOf } = usePet()

const broken = ref(false)

const meta = computed(() => speciesOf(props.petId))
const file = computed(() => {
  const s = meta.value
  if (!s) return ''
  return props.form === 'evolved' ? s.evolvedFile : s.baseFile
})
const src = computed(() => (file.value ? `/pet/${file.value}.png` : ''))
const pixels = computed(() => spritePixels(props.petId, props.form === 'evolved'))

watch(
  () => [props.petId, props.form],
  () => {
    broken.value = false
  },
)

function onImgError() {
  broken.value = true
}

const PAL = {
  _: 'transparent',
  k: '#191919',
  w: '#fbf9f6',
  /* grass */
  g: '#4f9a5c',
  G: '#2f6b3c',
  l: '#cfe7b8',
  p: '#d36b7a',
  /* fire */
  o: '#ef7a32',
  O: '#c45318',
  c: '#f3d27a',
  f: '#e51520',
  y: '#f2c14b',
  /* water */
  b: '#4f97c4',
  B: '#2b6a94',
  s: '#c9964a',
  S: '#8f6a2e',
  t: '#efe6cf',
  /* electric / 灯灯 */
  Y: '#ffd23f',
  /* normal / 墨墨 棕 */
  M: '#9b6b43',
  /* fairy / 墨墨·仙 粉 */
  E: '#f7a8c4',
  /* 团团 灰 + 团团·六六 藏青 */
  m: '#8a8a8a',
  n: '#3b4a6b',
  /* 丑丑 浊 + 丑丑·仙仙 碧 */
  u: '#6b7a8f',
  q: '#7ec8e3',
  /* 啾啾 粉 + 啾啾·胖 发色 */
  e: '#fbd3e0',
  h: '#e48fb0',
}

const MAPS = {
  yaya: [
    '____kkkk____',
    '__kkGGggkk__',
    '_kGGppggGk__',
    '_kggGGgggk__',
    '_kllllllgk__',
    '_kllkwkwllk_',
    '_kllkkkkllk_',
    '__kllllllk__',
    '__kggggggk__',
    '__kgk__kgk__',
    '___k____k___',
    '____________',
  ],
  'yaya-evo': [
    '___kkkkkkk__',
    '__kGGGppGGG_',
    '_kGGppggppG_',
    '_kggGGggGGg_',
    '_kllllllllk_',
    '_kllkwkwllk_',
    '_klllkkkllk_',
    '__kllllllk__',
    '__kGGggggGk_',
    '__kGk__kGk__',
    '___kk__kk___',
    '____________',
  ],
  yanzai: [
    '_____kk_____',
    '____koook___',
    '___koccook__',
    '___kcwckok__',
    '___kcccok___',
    '___koook_k__',
    '___koookkfk_',
    '__kooooofyk_',
    '__koo__ook__',
    '__kok__kok__',
    '___k____k___',
    '____________',
  ],
  'yanzai-evo': [
    '____kkkk____',
    '___kooOook__',
    '__koccccoOk_',
    '__kcwckcOok_',
    '__kccccook__',
    '__kooOookk__',
    '_kooOookkfk_',
    '_koooooofyk_',
    '_kooO__Ook__',
    '_kOk____kOk_',
    '__k______k__',
    '____________',
  ],
  paopao: [
    '____kkkk____',
    '___kbbbbk___',
    '__kbtwtbbk__',
    '__kbkkkbbk__',
    '__kttttssk__',
    '__kbbbbSsk__',
    '__kbbbbssk__',
    '__kbk__kbk__',
    '__kb____bk__',
    '__kk____kk__',
    '____________',
    '____________',
  ],
  'paopao-evo': [
    '___kkkkkkk__',
    '__kBbbbbbbk_',
    '_kBtwtwtbbk_',
    '_kbkkkkbbBk_',
    '_ktttttSssk_',
    '_kbbbbbSSsk_',
    '_kbbbbbssk__',
    '_kbk___kBk__',
    '_kBk___kBk__',
    '__kk___kk___',
    '____________',
    '____________',
  ],
  dengdeng: [
    '__kk____kk__',
    '_kYYk__kYYk_',
    '_kYYYkkYYYk_',
    '__YYYYYYYY__',
    '_kYYYYYYYYk_',
    '_kYwwYYwwYk_',
    '_kYfYYYYfYk_',
    '_kYYYYYYYYk_',
    '__YYYYYYYY__',
    '_kYYYYYYYYk_',
    '__kYY__YYk__',
    '____________',
  ],
  'dengdeng-evo': [
    '_koo____koo_',
    '_kooo__kooo_',
    '_kooooooook_',
    '_koowkooook_',
    '_koofkooofk_',
    '_kooooooook_',
    '_kooooooook_',
    '_kowwwooowk_',
    '_kooooooook_',
    '_koo____ook_',
    '__k______k__',
    '____________',
  ],
  momo: [
    '_kMk____kMk_',
    '_kMMk__kMMk_',
    '_kMMcMkMMcM_',
    '_kMMMMMMMMk_',
    '_kMMwwkMMww_',
    '_kMMcMMMMcM_',
    '_kMMMMMMMMk_',
    '_kMMccccMMk_',
    '_kMMMMMMMMk_',
    '_kMM____MMk_',
    '__k______k__',
    '____________',
  ],
  'momo-evo': [
    '__kE____kE__',
    '_kEEk__kEEk_',
    '_kEEwkEEwk__',
    '_kEEEEEEEEk_',
    '_kEEwwkEEww_',
    '_kEEEEEEEEk_',
    '_kEEccEEk___',
    '_kEEEEEEEEk_',
    '_kEEEEEEEEk_',
    '_kEE____EEk_',
    '__k______k__',
    '____________',
  ],
  douding: [
    '__ko____ko__',
    '_kooo__kooo_',
    '_kocokocok__',
    '_kooooooook_',
    '_kooowkooow_',
    '_kooooooook_',
    '_kooooooko__',
    '_koooooook__',
    '_koowwooook_',
    '_kooooooook_',
    '__koo__ook__',
    '____________',
  ],
  'douding-evo': [
    '__kw____kw__',
    '_kww_kww_k__',
    '_kwwwkwwwk__',
    '_kwwwwwwwwk_',
    '_kwwkwwwkkw_',
    '_kwwwwwwwwk_',
    '_kwoooooook_',
    '_kwoooooook_',
    '_kwwwwwwwwk_',
    '_kww____wwk_',
    '__kw____wk__',
    '____________',
  ],
  tuantuan: [
    '__km____mk__',
    '_kmm_kmm_k__',
    '_kmmckmmck__',
    '_kmmmmmmmmk_',
    '_kmmwkmmwk__',
    '_kmcccccmmk_',
    '_kmmmmmmmmk_',
    '_kmmccmmcck_',
    '_kmmmmmmmmk_',
    '_kmm____mmk_',
    '__km____mk__',
    '____________',
  ],
  'tuantuan-evo': [
    '__kw____wk__',
    '_kww_kww_k__',
    '_kwwkwkwwk__',
    '_kwwwwwwwwk_',
    '_kwwkwwwkkw_',
    '_kwnnnnnwk__',
    '_kwnnnnnwk__',
    '_kwwwwwwwwk_',
    '_kwwwwwwwwk_',
    '_kww____wwk_',
    '__kw____wk__',
    '____________',
  ],
  chouchou: [
    '____kuuk____',
    '___kuuuuk___',
    '_kuuuuuuuuk_',
    '_kuuwkuukwu_',
    '_kuuuuuuuuk_',
    '_kuukkuukuk_',
    '_kuuuuuuuuk_',
    '_kuuuuuuuuk_',
    '____kuuk____',
    '_____kk_____',
    '____________',
    '____________',
  ],
  'chouchou-evo': [
    '____kqqk____',
    '___kqqqk____',
    '_kqqqqqqk___',
    '_kqqwkkqqwk_',
    '_kqqqqqqqqk_',
    '_kqEEqqEEqk_',
    '_kqqqqqqqqk_',
    '__kqqqqqk___',
    '___kqqqk____',
    '____kqk_____',
    '_____k______',
    '____________',
  ],
  jiujiu: [
    '_____kek____',
    '___keeeek___',
    '__keeeeeek__',
    '_keeeeeeeek_',
    '_keewkkeewk_',
    '_keefkeefk__',
    '_keeeeeeeek_',
    '_keeeeeeeek_',
    '_keeeeeeeek_',
    '__keeeeeek__',
    '___k____k___',
    '____________',
  ],
  'jiujiu-evo': [
    '____khhhk___',
    '___khhhhk___',
    '__keeeeeek__',
    '_keeeeeeeek_',
    '_keewkkeewk_',
    '_keeeeeeeek_',
    '_keeeeeeeek_',
    '_keeeeeeeek_',
    '_keeeeeeeek_',
    '__keeeeeek__',
    '___k____k___',
    '____________',
  ],
}

function spritePixels(id, evolved) {
  const s = speciesOf(id)
  if (!s) return []
  const key = evolved ? s.evolvedFile : s.baseFile
  const rows = MAPS[key]
  if (!rows) return []
  const cells = []
  rows.forEach((row) => {
    for (const ch of row) {
      cells.push(PAL[ch] || 'transparent')
    }
  })
  return cells
}
</script>

<template>
  <div
    class="sprite"
    :style="{ width: size + 'px', height: size + 'px' }"
    aria-hidden="true"
  >
    <img
      v-if="src && !broken"
      class="bit"
      :src="src"
      alt=""
      @error="onImgError"
    />
    <div v-else class="px" :style="{ width: size + 'px', height: size + 'px' }">
      <i v-for="(c, i) in pixels" :key="i" :style="{ background: c }" />
    </div>
  </div>
</template>

<style scoped>
.sprite {
  position: relative;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  flex: none;
}
.bit {
  width: 100%;
  height: 100%;
  object-fit: contain;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  display: block;
  pointer-events: none;
}
.px {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  grid-template-rows: repeat(12, 1fr);
  image-rendering: pixelated;
}
.px i {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
