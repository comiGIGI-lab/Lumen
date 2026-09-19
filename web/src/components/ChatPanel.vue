<script setup>
/**
 * ChatPanel —— 课程问答（链路的下游能力）
 * 复用后端 run_chat_pipeline：先查知识库，未命中再调大模型。
 */
import { nextTick, ref } from 'vue'
import { api } from '@/api/client'

const props = defineProps({
  courseContext: { type: String, default: '' },
  mode: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['notify'])

const question = ref('')
const busy = ref(false)
const messages = ref([])
const listRef = ref(null)

async function scrollBottom() {
  await nextTick()
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
}

async function ask() {
  const q = (question.value || '').trim()
  if (!q || busy.value) return

  messages.value.push({ role: 'user', text: q })
  question.value = ''
  busy.value = true
  await scrollBottom()

  try {
    const history = messages.value
      .filter((m) => m.role === 'user' || m.role === 'ai')
      .slice(-8)
      .map((m) => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.text }))

    const res = await api.chat(q, history.slice(0, -1), props.courseContext)

    if (res.type === 'generate') {
      messages.value.push({
        role: 'ai',
        text: '这句话看起来是「生成方案」请求，请在上方输入课程名后点击「生成方案」。',
        source: 'intent',
      })
      emit('notify', { type: 'warn', text: '已识别为生成方案意图，请在顶部输入课程名' })
    } else {
      messages.value.push({
        role: 'ai',
        text: res.answer,
        source: res.source,
      })
    }
  } catch (e) {
    messages.value.push({ role: 'ai', text: `请求失败：${e.message}`, source: 'error' })
  } finally {
    busy.value = false
    await scrollBottom()
  }
}

function clear() {
  messages.value = []
}
</script>

<template>
  <section class="card card-pad chat">
    <div class="chat-head">
      <div class="lead">💬 课程问答</div>
      <span v-if="courseContext" class="chip chip-indigo">当前课程：{{ courseContext }}</span>
      <span v-else class="muted">先「生成方案」，AI 会围绕该课程作答</span>
      <button class="btn-link right" @click="clear">🗑 清空对话</button>
    </div>

    <div class="chat-input-row">
      <input
        v-model="question"
        class="input"
        placeholder="例如：零基础能学会吗？推荐什么参考书？第 3 章讲什么？"
        :disabled="busy"
        @keyup.enter="ask"
      />
      <button class="btn btn-accent" :disabled="busy" @click="ask">
        {{ busy ? '思考中…' : '提问' }}
      </button>
    </div>

    <div ref="listRef" class="chat-list">
      <div v-if="!messages.length" class="chat-empty">
        <span>🤖</span>
        <p>先查知识库，命中就直接回答；未命中再调用大模型。</p>
      </div>

      <div
        v-for="(m, i) in messages"
        :key="i"
        class="msg"
        :class="m.role === 'user' ? 'is-user' : 'is-ai'"
      >
        <div class="avatar">{{ m.role === 'user' ? '你' : '🤖' }}</div>
        <div class="bubble">
          <p class="text">{{ m.text }}</p>
          <span v-if="m.role === 'ai' && m.source" class="src">
            来源：{{
              m.source === 'knowledge'
                ? '知识库'
                : m.source === 'llm'
                  ? '大模型'
                  : m.source === 'intent'
                    ? '意图识别'
                    : '错误'
            }}
          </span>
        </div>
      </div>

      <div v-if="busy" class="msg is-ai">
        <div class="avatar">🤖</div>
        <div class="bubble thinking"><i></i><i></i><i></i></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.chat {
  padding: 14px 18px 16px;
}

.chat-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.lead {
  font-size: 13.5px;
  font-weight: 700;
}

.muted {
  font-size: 12px;
  color: var(--text-muted);
}

.right {
  margin-left: auto;
}

.chat-input-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
}

.chat-list {
  margin-top: 12px;
  max-height: 320px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
}

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--text-faint);
  font-size: 12px;
  padding: 26px 0;
}

.chat-empty span {
  font-size: 26px;
  opacity: 0.5;
}

.msg {
  display: flex;
  gap: 9px;
  align-items: flex-start;
}

.msg.is-user {
  flex-direction: row-reverse;
}

.avatar {
  flex: none;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 700;
  background: #fff;
  border: 1px solid var(--border);
}

.msg.is-user .avatar {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}

.bubble {
  max-width: 78%;
  padding: 9px 12px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--border);
}

.msg.is-user .bubble {
  background: var(--primary-soft);
  border-color: #c7d2fe;
}

.text {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.65;
}

.src {
  display: inline-block;
  margin-top: 5px;
  font-size: 10.5px;
  color: var(--text-faint);
}

.thinking {
  display: flex;
  gap: 5px;
  align-items: center;
  padding: 13px 14px;
}

.thinking i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary-light);
  animation: pulse-soft 1.1s ease-in-out infinite;
}

.thinking i:nth-child(2) {
  animation-delay: 0.18s;
}

.thinking i:nth-child(3) {
  animation-delay: 0.36s;
}
</style>
