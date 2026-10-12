<script setup>
/**
 * SettingsDialog —— AI 模型设置
 *
 * 严格对齐桌面版 `ui/settings_dialog.py` 的结构：
 *   1. 运行模式：两段**等宽**按钮（离线 Mock / 在线 LLM），而不是一堆混在一起的选项
 *   2. 模型配置：可提前配置，切到 LLM 模式后生效（Mock 下也不隐藏）
 *   3. 平台下拉：选中后自动填 Base URL 与模型名（预设与桌面版 PLATFORMS 完全一致）
 *   4. API Key：密码框 + 「显示」切换 + 红色必填提示
 *   5. 测试连接：真发一次最小请求验 Key（与桌面版判定一致）
 *   6. 使用说明：可展开的帮助面板
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import ModalDialog from './ModalDialog.vue'
import { api } from '@/api/client'

const props = defineProps({
  open: { type: Boolean, default: false },
  mode: { type: Object, default: () => ({}) },
  onboarding: { type: Boolean, default: false },
})
const { t } = useI18n()

const emit = defineEmits(['close', 'saved', 'show-tour'])

/** 平台预设 —— 与桌面版 ui/settings_dialog.py 的 PLATFORMS 一一对应 */
const PLATFORMS = [
  { name: 'DeepSeek', base_url: 'https://api.deepseek.com', model: 'deepseek-chat' },
  { name: 'OpenAI', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  {
    name: '通义千问 (Qwen)',
    labelKey: 'plat.qwen',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-plus',
  },
  {
    name: '智谱 GLM',
    labelKey: 'plat.zhipu',
    base_url: 'https://open.bigmodel.cn/api/paas/v4',
    model: 'glm-4-flash',
  },
  {
    name: '月之暗面 (Kimi)',
    labelKey: 'plat.kimi',
    base_url: 'https://api.moonshot.cn/v1',
    model: 'moonshot-v1-8k',
  },
  { name: '自定义', labelKey: 'plat.custom', base_url: '', model: '' },
]

const form = reactive({
  provider: 'mock',
  api_key: '',
  base_url: 'https://api.deepseek.com',
  model: 'deepseek-chat',
  platform: 'DeepSeek',
})

const ui = reactive({
  showKey: false,
  showHelp: false,
  busy: false,
  msg: '',
  tone: '',
  testing: false,
  testMsg: '',
  testTone: '',
  wantClearKey: false,
  missingFields: [],
  foldOpen: { base: true, key: false, model: false },
})

const hasSavedKey = ref(false)
const savedKeyMasked = ref('')
const isNarrow = ref(false)
let _mq = null
function syncNarrow() {
  isNarrow.value = !!(typeof window !== 'undefined' && window.matchMedia('(max-width: 430px)').matches)
}
const isLLM = computed(() => form.provider === 'llm')
const showLlmForm = ref(false)
const openBase = computed(() => showLlmForm.value && (!isNarrow.value || ui.foldOpen.base))
const openKey = computed(() => showLlmForm.value && (!isNarrow.value || ui.foldOpen.key))
const openModel = computed(() => showLlmForm.value && (!isNarrow.value || ui.foldOpen.model))

onMounted(() => {
  syncNarrow()
  if (typeof window === 'undefined') return
  _mq = window.matchMedia('(max-width: 430px)')
  const onChange = () => syncNarrow()
  if (_mq.addEventListener) _mq.addEventListener('change', onChange)
  else _mq.addListener(onChange)
  _mq._onChange = onChange
})
onBeforeUnmount(() => {
  if (!_mq || !_mq._onChange) return
  if (_mq.removeEventListener) _mq.removeEventListener('change', _mq._onChange)
  else _mq.removeListener(_mq._onChange)
})

/** 打开时把当前配置灌进来（Key 永不回填，只提示「已保存」） */
watch(
  () => props.open,
  (v) => {
    if (!v) return
    const m = props.mode || {}
    // 只有明确是 llm 才选中 LLM，其余（含 mode 尚未加载）一律落到 Mock，
    // 避免后端还没就绪时误显示成 LLM 模式
    form.provider = m.mode === 'llm' ? 'llm' : 'mock'
    showLlmForm.value = form.provider === 'llm'
    form.api_key = ''
    form.base_url = m.base_url || 'https://api.deepseek.com'
    form.model = m.model || 'deepseek-chat'

    // 按 base_url 反查平台，查不到就是「自定义」
    const hit = PLATFORMS.find(
      (p) => p.base_url && p.base_url.replace(/\/+$/, '') === form.base_url.replace(/\/+$/, ''),
    )
    form.platform = hit ? hit.name : '自定义'

    hasSavedKey.value = !!m.has_key
    savedKeyMasked.value = m.api_key_masked || ''
    ui.showKey = false
    ui.showHelp = false
    ui.msg = ''
    ui.tone = ''
    ui.testMsg = ''
    ui.testTone = ''
    ui.testing = false
    ui.wantClearKey = false
    ui.missingFields = []
    ui.foldOpen = { base: true, key: false, model: false }
  },
  { immediate: true },
)

/** 主动清空已保存的 Key（点保存后生效） */
function markClearKey() {
  form.api_key = ''
  ui.wantClearKey = true
  ui.tone = ''
  ui.msg = '已标记清空密钥，点「保存设置」后生效'
}

/** 选平台 → 自动填 Base URL 与模型名（「自定义」不覆盖用户已填内容） */
function pickPlatform() {
  const p = PLATFORMS.find((x) => x.name === form.platform)
  if (!p || p.name === '自定义') return
  form.base_url = p.base_url
  form.model = p.model
  ui.testMsg = ''
}

/** 切运行模式时清掉上一次的测试结果，避免误导 */
function pickMode(v) {
  form.provider = v
  showLlmForm.value = v === 'llm'
  ui.testMsg = ''
  ui.testTone = ''
}

const keyPlaceholder = computed(() =>
  hasSavedKey.value ? `已保存 ${savedKeyMasked.value}（留空则保持不变）` : 'sk-…',
)

async function testConnection() {
  ui.testing = true
  ui.testMsg = '连接中…'
  ui.testTone = ''
  try {
    const res = await api.testSettings({
      api_key: form.api_key,
      base_url: form.base_url,
      model: form.model,
    })
    if (res.ok) {
      ui.testTone = 'ok'
      ui.testMsg = `✓ 连接成功（${res.ms}ms）`
    } else {
      ui.testTone = 'err'
      ui.testMsg = `✗ ${res.error || '连接失败'}`
    }
  } catch (e) {
    ui.testTone = 'err'
    ui.testMsg = `✗ ${e.message}`
  } finally {
    ui.testing = false
  }
}

function isMissing(name) {
  return ui.missingFields.includes(name)
}
function dropMissing(name) {
  ui.missingFields = ui.missingFields.filter((x) => x !== name)
}
function validateLLM() {
  const missing = []
  const willHaveKey = !ui.wantClearKey && (!!form.api_key.trim() || hasSavedKey.value)
  if (!willHaveKey) missing.push('api_key')
  if (!form.base_url.trim()) missing.push('base_url')
  if (!form.model.trim()) missing.push('model')
  ui.missingFields = missing
  if (missing.includes('base_url')) ui.foldOpen.base = true
  if (missing.includes('api_key')) ui.foldOpen.key = true
  if (missing.includes('model')) ui.foldOpen.model = true
  return missing.length === 0
}

async function save() {
  if (isLLM.value && !validateLLM()) {
    ui.tone = 'err'
    ui.msg = `LLM 模式下 ${ui.missingFields.join(' / ')} 必填，已自动展开高亮`
    return
  }
  ui.busy = true
  ui.msg = ''
  try {
    const res = await api.saveSettings({
      provider: form.provider,
      api_key: form.api_key,
      clear_key: ui.wantClearKey,
      base_url: form.base_url,
      model: form.model,
    })
    hasSavedKey.value = !!res.mode?.has_key
    savedKeyMasked.value = res.mode?.api_key_masked || ''
    ui.wantClearKey = false
    form.api_key = ''
    ui.tone = 'ok'
    ui.msg = `✓ 已保存，当前模式：${res.mode?.label || ''}`
    emit('saved', res.mode)
  } catch (e) {
    ui.tone = 'err'
    ui.msg = `保存失败：${e.message}`
  } finally {
    ui.busy = false
  }
}

async function clearCache() {
  ui.busy = true
  try {
    const res = await api.clearCache(null)
    ui.tone = 'ok'
    ui.msg = `已清空结果缓存（${res.cleared} 条）`
  } catch (e) {
    ui.tone = 'err'
    ui.msg = `清空失败：${e.message}`
  } finally {
    ui.busy = false
  }
}
</script>

<template>
  <ModalDialog :open="open" :title="t('settingsDialog.1')" icon="🪄" width="640px" fullscreen-on-mobile @close="emit('close')">
    <!-- ============ 运行模式：两段等宽 ============ -->
    <section class="block">
      <div class="block-head">
        <h4>{{ t('settingsDialog.3') }}</h4>
        <span class="block-sub">{{ isLLM ? t('settingsDialog.4') : '内置模板，适合先体验' }}</span>
      </div>
      <div class="seg">
        <button
          class="seg-btn"
          :class="{ on: form.provider === 'mock' }"
          type="button"
          @click="pickMode('mock')"
        >{{ t('settingsDialog.5') }}</button>
        <button
          class="seg-btn"
          :class="{ on: form.provider === 'llm' }"
          type="button"
          @click="pickMode('llm')"
        >{{ t('settingsDialog.6') }}</button>
      </div>
      <p class="mode-note">{{ t('settingsDialog.38') }}</p>
    </section>

    <!-- ============ 模型配置：默认收起，在线模式才需要展开 ============ -->
    <section class="block" :class="{ 'llm-collapsed': !showLlmForm }">
      <button type="button" class="block-head llm-toggle" :aria-expanded="showLlmForm" @click="showLlmForm = !showLlmForm">
        <h4>{{ t('settingsDialog.7') }}</h4>
        <span class="block-sub">{{ showLlmForm ? '收起' : (isLLM ? '填写后才会调用在线模型' : '体验模式用不到，需要时再展开') }}</span>
      </button>

      <template v-if="showLlmForm">
      <div class="field">
        <label class="lbl">{{ t('settingsDialog.9') }}</label>
        <div class="ctl">
          <select v-model="form.platform" class="input" @change="pickPlatform">
            <option v-for="p in PLATFORMS" :key="p.name" :value="p.name">{{ t(p.labelKey) || p.name }}</option>
          </select>
        </div>
      </div>

      <details class="llm-fold" :class="{ 'llm-fold-missing': isMissing('base_url') }" :open="openBase">
        <summary @click.prevent="ui.foldOpen.base = !ui.foldOpen.base">
          API Base URL
          <span class="fold-meta">{{ form.base_url || '未填' }}</span>
        </summary>
        <div class="field fold-inner">
          <label class="lbl">API Base URL</label>
          <div class="ctl">
            <input
              v-model="form.base_url"
              class="input"
              :class="{ 'input-missing': isMissing('base_url') }"
              placeholder="https://api.deepseek.com"
              @input="dropMissing('base_url')"
            />
          </div>
        </div>
      </details>

      <details class="llm-fold" :class="{ 'llm-fold-missing': isMissing('api_key') }" :open="openKey">
        <summary @click.prevent="ui.foldOpen.key = !ui.foldOpen.key">
          API Key
          <span class="fold-meta">{{ hasSavedKey && !ui.wantClearKey ? '已保存密钥' : (form.api_key ? '已填' : '未填') }}</span>
        </summary>
        <div class="field fold-inner key-field">
          <label class="lbl">API Key</label>
          <div class="ctl key-row">
            <input
              v-model="form.api_key"
              class="input"
              :class="{ 'input-missing': isMissing('api_key') }"
              :type="ui.showKey ? 'text' : 'password'"
              :placeholder="ui.wantClearKey ? t('settingsDialogX.1') : keyPlaceholder"
              autocomplete="off"
              @input="ui.wantClearKey = false; dropMissing('api_key')"
            />
            <button class="btn btn-ghost tiny" type="button" @click="ui.showKey = !ui.showKey">
              {{ ui.showKey ? t('settingsDialogX.2') : t('settingsDialogX.3') }}
            </button>
            <button
              v-if="hasSavedKey && !ui.wantClearKey"
              class="btn btn-ghost tiny"
              type="button"
              :title="t('settingsDialog.2')"
              @click="markClearKey"
            >{{ t('settingsDialog.10') }}</button>
          </div>
        </div>
        <p class="req" :class="{ dim: !isLLM }">{{ t('settingsDialog.11') }}<span v-if="hasSavedKey && !ui.wantClearKey" class="req-note">
            · 留空则保持已保存的 {{ savedKeyMasked }}
          </span>
          <span v-if="ui.wantClearKey" class="req-warn">{{ t('settingsDialog.12') }}</span>
        </p>
      </details>

      <details class="llm-fold" :class="{ 'llm-fold-missing': isMissing('model') }" :open="openModel">
        <summary @click.prevent="ui.foldOpen.model = !ui.foldOpen.model">
          {{ t('settingsDialog.13') }}
          <span class="fold-meta">{{ form.model || '未填' }}</span>
        </summary>
        <div class="field fold-inner">
          <label class="lbl">{{ t('settingsDialog.13') }}</label>
          <div class="ctl">
            <input
              v-model="form.model"
              class="input"
              :class="{ 'input-missing': isMissing('model') }"
              placeholder="deepseek-chat"
              @input="dropMissing('model')"
            />
          </div>
        </div>
      </details>

      <div class="field">
        <label class="lbl"></label>
        <div class="ctl test-row">
          <button
            class="btn btn-accent"
            type="button"
            :disabled="ui.testing || !isLLM"
            @click="testConnection"
          >
            {{ ui.testing ? t('settingsDialogX.4') : t('settingsDialogX.5') }}
          </button>
          <span v-if="!isLLM" class="test-msg dim">{{ t('settingsDialog.14') }}</span>
          <span v-else-if="ui.testMsg" class="test-msg" :class="ui.testTone">{{ ui.testMsg }}</span>
        </div>
      </div>
      </template>
    </section>

    <!-- ============ 小提示 / 使用说明 ============ -->
    <section class="block tips">
      <div class="tips-head">{{ t('settingsDialog.15') }}</div>
      <ul>
        <li>{{ t('settingsDialog.16') }}</li>
        <li>
          <b>{{ t('settingsDialog.17') }}</b>{{ t('settingsDialog.18') }}<code>degraded</code>{{ t('settingsDialog.19') }}</li>
        <li>{{ t('settingsDialog.20') }}</li>
      </ul>
    </section>

    <div v-if="ui.showHelp" class="help">
      <div class="help-title">{{ t('settingsDialog.21') }}</div>
      <ol>
        <li>{{ t('settingsDialog.22') }}<b>{{ t('settingsDialog.23') }}</b>。</li>
        <li>{{ t('settingsDialog.24') }}<strong>{{ t('settingsDialog.25') }}</strong>{{ t('settingsDialog.26') }}</li>
        <li>{{ t('settingsDialog.27') }}</li>
        <li>{{ t('settingsDialog.28') }}</li>
        <li>{{ t('settingsDialog.29') }}</li>
      </ol>
      <div class="help-title">{{ t('settingsDialog.30') }}</div>
      <p>{{ t('settingsDialog.31') }}<code>settings.json</code>{{ t('settingsDialog.32') }}</p>
      <div class="help-title">{{ t('settingsDialog.33') }}</div>
      <p>{{ t('settingsDialog.34') }}</p>
    </div>

    <p class="cache-hint">{{ t('settingsDialog.39') }}</p>
    <div v-if="ui.msg" class="feedback" :class="ui.tone">{{ ui.msg }}</div>

    <template #footer>
      <button class="btn btn-ghost foot-left desk-only" type="button" @click="ui.showHelp = !ui.showHelp">
        {{ ui.showHelp ? t('settingsDialogX.6') : t('settingsDialogX.7') }}
      </button>
      <button class="btn btn-ghost desk-only" type="button" @click="emit('show-tour')">{{ t('settingsDialog.35') }}</button>
      <button
        class="btn btn-ghost desk-only"
        type="button"
        :disabled="ui.busy"
        :title="t('settingsDialog.39')"
        @click="clearCache"
      >{{ t('settingsDialog.36') }}</button>
      <button v-if="onboarding" class="btn btn-ghost" type="button" @click="emit('close')">{{ t('settingsDialog.tryFirst') }}</button>
      <button v-else class="btn btn-ghost" type="button" @click="emit('close')">{{ t('settingsDialog.37') }}</button>
      <button class="btn btn-primary" type="button" :disabled="ui.busy" @click="save">
        {{ ui.busy ? t('settingsDialogX.8') : t('settingsDialogX.9') }}
      </button>
    </template>
  </ModalDialog>
</template>

<style scoped>
.block {
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.block:last-of-type {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 4px;
}

.block-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}
.mode-note {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 12.5px;
  line-height: 1.6;
}
.cache-hint {
  margin: 0 0 10px;
  color: var(--text-muted);
  font-size: 12.5px;
  line-height: 1.6;
}
.llm-toggle {
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.llm-collapsed .llm-toggle {
  margin-bottom: 0;
}

.block-head h4 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 15px;
  font-weight: 400;
  color: var(--text-primary);
}

.block-sub {
  font-size: 12px;
  color: var(--text-muted);
}

/* ---- 两段等宽运行模式 ---- */
.seg {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.seg-btn {
  border: 1px solid var(--border);
  background: var(--bg-soft);
  border-radius: 1000px;
  padding: 14px 10px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.seg-btn:hover {
  border-color: var(--primary-light);
}

.seg-btn.on {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}

/* ---- 字段行：标签定宽 + 控件吃满 ---- */
.field {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.lbl {
  flex: none;
  width: 96px;
  font-size: 13px;
  color: var(--text-secondary);
  text-align: right;
}

.ctl {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.input {
  flex: 1;
  min-width: 0;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 11px;
  font-size: 13px;
  background: var(--bg-card);
  color: var(--text-primary);
}

.input:focus {
  outline: none;
  border-color: var(--primary);
}

select.input {
  appearance: auto;
}

.key-row .input {
  font-family: var(--font-mono);
}

.tiny {
  flex: none;
  padding: 7px 12px;
  font-size: 12.5px;
}

.req {
  margin: 0 0 10px 108px;
  font-size: 12px;
  color: #dc2626;
}

.req.dim {
  color: var(--text-muted);
}

.req-note {
  color: var(--text-muted);
}

.req-warn {
  color: #b45309;
  font-weight: 700;
}

/* 桌面端：details 只是结构，字段行保持原样（标签定宽 + 输入吃满）。 */
.llm-fold {
  border: none;
  padding: 0;
}
.llm-fold > summary {
  display: none;
}
.fold-inner {
  margin-top: 0;
}
.fold-inner .lbl {
  display: block;
}

.llm-fold-missing > summary,
.llm-fold-missing .input {
  border-color: #e51520;
}

.input-missing {
  border-color: #e51520 !important;
  box-shadow: 0 0 0 2px rgba(229, 21, 32, 0.12);
}

@media (max-width: 430px) {
  .llm-fold {
    border: 1px solid transparent;
    border-top: 1px dashed var(--border, #e4ded5);
    padding: 6px 8px 4px;
    border-radius: 8px;
    margin: 0 -4px 4px;
  }
  .llm-fold > summary {
    display: flex;
    list-style: none;
    cursor: pointer;
    font-size: 12.5px;
    color: var(--text-secondary, #4a4540);
    align-items: center;
    gap: 6px;
    padding: 4px 0;
  }
  .llm-fold > summary::-webkit-details-marker {
    display: none;
  }
  .llm-fold > summary::before {
    content: "▸";
    color: var(--text-muted, #808080);
    font-size: 10px;
    display: inline-block;
    width: 10px;
  }
  .llm-fold[open] > summary::before {
    content: "▾";
  }
  .fold-meta {
    margin-left: auto;
    font-size: 11.5px;
    color: var(--text-muted, #808080);
    font-family: var(--font-mono);
    max-width: 60%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .fold-inner {
    margin-top: 4px;
    flex-wrap: wrap;
  }
  .fold-inner .lbl {
    display: none;
  }
  .req {
    margin-left: 0;
  }
  .llm-fold-missing {
    border: 1px solid #e51520;
    box-shadow: 0 0 0 2px rgba(229, 21, 32, 0.12);
  }
}

.test-row {
  justify-content: flex-start;
  gap: 12px;
}

.test-msg {
  font-size: 12.5px;
}

.test-msg.ok {
  color: #047857;
}

.test-msg.err {
  color: #b91c1c;
  word-break: break-all;
}

.test-msg.dim {
  color: var(--text-muted);
}

/* ---- 小提示 / 使用说明 ---- */
.tips {
  background: var(--bg-soft);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 11px 14px;
  margin-bottom: 14px;
}

.tips-head {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 6px;
}

.tips ul,
.help ol {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.help {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  margin-bottom: 14px;
  background: var(--bg-card);
}

.help-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--primary-dark);
  margin: 8px 0 4px;
}

.help-title:first-child {
  margin-top: 0;
}

.help p {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.75;
}

.help code,
.tips code {
  font-family: var(--font-mono);
  background: var(--bg-disabled);
  padding: 1px 5px;
  border-radius: 4px;
}

.feedback {
  margin-top: 12px;
  font-size: 12.5px;
  border-radius: var(--radius-sm);
  padding: 8px 12px;
}

.feedback.ok {
  background: var(--success-soft);
  border: 1px solid #a7f3d0;
  color: #047857;
}

.feedback.err {
  background: var(--error-soft);
  border: 1px solid #fecaca;
  color: #b91c1c;
}

/* 让「使用说明」靠左，其余按钮靠右 */
.foot-left {
  margin-right: auto;
}

/* 窄屏底栏只留「跳过/取消 + 保存」，英文长按钮不再把设置内容顶出屏幕。 */
@media (max-width: 430px) {
  .desk-only {
    display: none;
  }
}
</style>
