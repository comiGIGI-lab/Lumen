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
import { computed, reactive, ref, watch } from 'vue'
import ModalDialog from './ModalDialog.vue'
import { api } from '@/api/client'

const props = defineProps({
  open: { type: Boolean, default: false },
  mode: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['close', 'saved'])

/** 平台预设 —— 与桌面版 ui/settings_dialog.py 的 PLATFORMS 一一对应 */
const PLATFORMS = [
  { name: 'DeepSeek', base_url: 'https://api.deepseek.com', model: 'deepseek-chat' },
  { name: 'OpenAI', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  {
    name: '通义千问 (Qwen)',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-plus',
  },
  { name: '智谱 GLM', base_url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
  { name: '月之暗面 (Kimi)', base_url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  { name: '自定义', base_url: '', model: '' },
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
})

const hasSavedKey = ref(false)
const savedKeyMasked = ref('')

const isLLM = computed(() => form.provider === 'llm')

/** 打开时把当前配置灌进来（Key 永不回填，只提示「已保存」） */
watch(
  () => props.open,
  (v) => {
    if (!v) return
    const m = props.mode || {}
    // 只有明确是 llm 才选中 LLM，其余（含 mode 尚未加载）一律落到 Mock，
    // 避免后端还没就绪时误显示成 LLM 模式
    form.provider = m.mode === 'llm' ? 'llm' : 'mock'
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

async function save() {
  // 保存后到底有没有 Key：本次填了 / 磁盘上已有且没标记清空
  const willHaveKey = !ui.wantClearKey && (!!form.api_key.trim() || hasSavedKey.value)
  if (isLLM.value && !willHaveKey) {
    ui.tone = 'err'
    ui.msg = 'LLM 模式必须填 API Key（或先切回 Mock 模式）'
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
  <ModalDialog :open="open" title="AI 模型设置" icon="🪄" width="640px" @close="emit('close')">
    <!-- ============ 运行模式：两段等宽 ============ -->
    <section class="block">
      <div class="block-head">
        <h4>运行模式</h4>
        <span class="block-sub">调用在线大模型 API</span>
      </div>
      <div class="seg">
        <button
          class="seg-btn"
          :class="{ on: form.provider === 'mock' }"
          type="button"
          @click="pickMode('mock')"
        >
          离线 Mock 模式
        </button>
        <button
          class="seg-btn"
          :class="{ on: form.provider === 'llm' }"
          type="button"
          @click="pickMode('llm')"
        >
          在线 LLM 模式
        </button>
      </div>
    </section>

    <!-- ============ 模型配置 ============ -->
    <section class="block">
      <div class="block-head">
        <h4>模型配置</h4>
        <span class="block-sub">（可提前配置；切到 LLM 模式后生效）</span>
      </div>

      <div class="field">
        <label class="lbl">平台</label>
        <div class="ctl">
          <select v-model="form.platform" class="input" @change="pickPlatform">
            <option v-for="p in PLATFORMS" :key="p.name" :value="p.name">{{ p.name }}</option>
          </select>
        </div>
      </div>

      <div class="field">
        <label class="lbl">API Key</label>
        <div class="ctl key-row">
          <input
            v-model="form.api_key"
            class="input"
            :type="ui.showKey ? 'text' : 'password'"
            :placeholder="ui.wantClearKey ? '（保存后将清空已存密钥）' : keyPlaceholder"
            autocomplete="off"
            @input="ui.wantClearKey = false"
          />
          <button class="btn btn-ghost tiny" type="button" @click="ui.showKey = !ui.showKey">
            {{ ui.showKey ? '隐藏' : '显示' }}
          </button>
          <button
            v-if="hasSavedKey && !ui.wantClearKey"
            class="btn btn-ghost tiny"
            type="button"
            title="清空本机已保存的 API Key"
            @click="markClearKey"
          >
            清空
          </button>
        </div>
      </div>
      <p class="req" :class="{ dim: !isLLM }">
        * 必填（LLM 模式下需要）
        <span v-if="hasSavedKey && !ui.wantClearKey" class="req-note">
          · 留空则保持已保存的 {{ savedKeyMasked }}
        </span>
        <span v-if="ui.wantClearKey" class="req-warn">· 已标记清空</span>
      </p>

      <div class="field">
        <label class="lbl">API Base URL</label>
        <div class="ctl">
          <input v-model="form.base_url" class="input" placeholder="https://api.deepseek.com" />
        </div>
      </div>

      <div class="field">
        <label class="lbl">模型名称</label>
        <div class="ctl">
          <input v-model="form.model" class="input" placeholder="deepseek-chat" />
        </div>
      </div>

      <div class="field">
        <label class="lbl"></label>
        <div class="ctl test-row">
          <button
            class="btn btn-accent"
            type="button"
            :disabled="ui.testing || !isLLM"
            @click="testConnection"
          >
            {{ ui.testing ? '测试中…' : '测试连接' }}
          </button>
          <span v-if="!isLLM" class="test-msg dim">Mock 模式下无需测试连接</span>
          <span v-else-if="ui.testMsg" class="test-msg" :class="ui.testTone">{{ ui.testMsg }}</span>
        </div>
      </div>
    </section>

    <!-- ============ 小提示 / 使用说明 ============ -->
    <section class="block tips">
      <div class="tips-head">💡 小提示</div>
      <ul>
        <li>DeepSeek / OpenAI / 通义千问 / 智谱 GLM / 月之暗面都兼容 OpenAI 格式。</li>
        <li>
          <b>没填 Key 也能用</b>：会自动回落到内置模板，结果里会标注
          <code>degraded</code>，不会报错中断。
        </li>
        <li>API Key 只保存在本机，不会上传到任何地方。</li>
      </ul>
    </section>

    <div v-if="ui.showHelp" class="help">
      <div class="help-title">📖 使用说明</div>
      <ol>
        <li>在「运行模式」里选择 <b>在线 LLM 模式</b>。</li>
        <li>「平台」下拉选服务商，Base URL 与模型名会<strong>自动填好</strong>（选「自定义」则手动填）。</li>
        <li>把你的 API Key 粘进「API Key」，点「显示」可以核对是否粘错。</li>
        <li>点「测试连接」验证 Key 是否可用（可选）。</li>
        <li>点「保存设置」完成 —— 立即生效，无需重启。</li>
      </ol>
      <div class="help-title">🔐 关于 API Key</div>
      <p>
        只保存在本机配置文件 <code>settings.json</code>，不会上传到任何地方。
        DeepSeek 注册送额度，新用户够用一段时间。
      </p>
      <div class="help-title">📚 关于学习计划</div>
      <p>
        根据你输入的目标（学什么、花多久、每天几小时）生成大纲 + 日历。
        可以多次生成对比，挑一个最合适的保存。
      </p>
    </div>

    <div v-if="ui.msg" class="feedback" :class="ui.tone">{{ ui.msg }}</div>

    <template #footer>
      <button class="btn btn-ghost foot-left" type="button" @click="ui.showHelp = !ui.showHelp">
        {{ ui.showHelp ? '收起说明' : '? 使用说明' }}
      </button>
      <button class="btn btn-ghost" type="button" :disabled="ui.busy" @click="clearCache">
        清空缓存
      </button>
      <button class="btn btn-ghost" type="button" @click="emit('close')">取消</button>
      <button class="btn btn-primary" type="button" :disabled="ui.busy" @click="save">
        {{ ui.busy ? '保存中…' : '保存设置' }}
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
  background: #fff;
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
  background: #fff;
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
</style>
