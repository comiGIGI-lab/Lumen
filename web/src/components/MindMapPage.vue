<script setup>
/**
 * MindMapPage —— 可编辑思维导图
 *
 * 纯 SVG 连线 + DOM 节点，不引任何图库（与项目「零依赖」原则一致）。
 * 节点用「扁平数组 + parent 引用」存储，布局时递归还原成树；
 * 后端只做结构校验（唯一根、无环、parent 存在），坐标全由前端算。
 *
 * 入口：更多 → 思维导图；也可以从已有方案一键生成初始结构。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/api/client'
import { useI18n } from '@/i18n'

const props = defineProps({
  embedded: { type: Boolean, default: false },
})
const emit = defineEmits(['back', 'notify'])
const { t } = useI18n()

// ---------- 布局常量 ----------
const NODE_W = 170
const NODE_H = 36
const GAP_X = 46
const GAP_Y = 14
const PAD = 28

const course = ref('')
const nodes = ref([])
const courses = ref([])
const selected = ref('')
const editing = ref('')
const editText = ref('')
const scale = ref(1)
const busy = ref(false)
const dirty = ref(false)

let seq = 0
function makeId() {
  seq += 1
  return `n${seq}_${Math.random().toString(36).slice(2, 6)}`
}

function mark() {
  dirty.value = true
}

// ---------- 树构建与布局 ----------
const tree = computed(() => {
  const map = new Map()
  nodes.value.forEach((n) => map.set(n.id, { ...n, children: [] }))
  let root = null
  map.forEach((n) => {
    if (n.parent && map.has(n.parent)) map.get(n.parent).children.push(n)
    else if (!n.parent) root = n
  })
  return { root, map }
})

/** 后序遍历分配坐标：叶子按顺序占行，父节点取子节点垂直中位 */
const laid = computed(() => {
  const { root } = tree.value
  if (!root) return { list: [], width: 200, height: 120 }

  const list = []
  let cursor = 0

  function walk(node, depth) {
    if (node.children.length) {
      node.children.forEach((c) => walk(c, depth + 1))
      const ys = node.children.map((c) => c._y)
      node._y = (Math.min(...ys) + Math.max(...ys)) / 2
    } else {
      node._y = cursor
      cursor += NODE_H + GAP_Y
    }
    node._x = depth * (NODE_W + GAP_X)
    list.push(node)
  }
  walk(root, 0)

  const depthMax = Math.max(...list.map((n) => n._x))
  return {
    list,
    width: depthMax + NODE_W + PAD * 2,
    height: cursor + PAD * 2,
  }
})

/** 连线：父节点右中 → 子节点左中，用贝塞尔画 */
const links = computed(() => {
  const { list } = laid.value
  const byId = new Map(list.map((n) => [n.id, n]))
  const out = []
  list.forEach((n) => {
    if (!n.parent) return
    const p = byId.get(n.parent)
    if (!p) return
    const x1 = p._x + PAD + NODE_W
    const y1 = p._y + PAD + NODE_H / 2
    const x2 = n._x + PAD
    const y2 = n._y + PAD + NODE_H / 2
    const mx = (x1 + x2) / 2
    out.push({ id: `${p.id}-${n.id}`, d: `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}` })
  })
  return out
})

const stats = computed(() => ({
  total: nodes.value.length,
  depth: nodes.value.length ? Math.max(...nodes.value.map((n) => depthOf(n.id))) + 1 : 0,
}))

function depthOf(id, guard = 0) {
  if (guard > 50) return 0
  const n = nodes.value.find((x) => x.id === id)
  if (!n || !n.parent) return 0
  return 1 + depthOf(n.parent, guard + 1)
}

// ---------- 操作 ----------
function selectNode(id) {
  selected.value = id
  editing.value = ''
}

function startEdit(node) {
  if (busy.value) return
  selected.value = node.id
  editing.value = node.id
  editText.value = node.text
}

function commitEdit() {
  const n = nodes.value.find((x) => x.id === editing.value)
  if (n) {
    const t = editText.value.trim()
    if (t !== n.text) {
      n.text = t || (n.parent ? '未命名' : n.text)
      mark()
    }
  }
  editing.value = ''
}

function addChild(parentId) {
  const id = makeId()
  nodes.value.push({ id, parent: parentId, text: '新节点' })
  selected.value = id
  mark()
  // 新增后直接进入编辑态，少点一次
  setTimeout(() => startEdit(nodes.value.find((n) => n.id === id)), 0)
}

function removeNode(id) {
  const n = nodes.value.find((x) => x.id === id)
  if (!n) return
  if (!n.parent) {
    emit('notify', { type: 'error', text: '根节点不能删除' })
    return
  }
  // 连同子孙一起删，避免留下游离节点（后端会拒）
  const doomed = new Set([id])
  let grew = true
  while (grew) {
    grew = false
    nodes.value.forEach((x) => {
      if (x.parent && doomed.has(x.parent) && !doomed.has(x.id)) {
        doomed.add(x.id)
        grew = true
      }
    })
  }
  nodes.value = nodes.value.filter((x) => !doomed.has(x.id))
  if (doomed.has(selected.value)) selected.value = ''
  mark()
  emit('notify', { type: 'info', text: `已删除 ${doomed.size} 个节点` })
}

function zoom(delta) {
  scale.value = Math.min(1.6, Math.max(0.5, +(scale.value + delta).toFixed(2)))
}

function resetZoom() {
  scale.value = 1
}

// ---------- 载入 / 保存 ----------
function buildFromOutline(courseName, outline) {
  const list = []
  const rootId = makeId()
  list.push({ id: rootId, parent: null, text: courseName || '学习主题' })

  ;(outline || []).forEach((ch, i) => {
    const chId = makeId()
    const title = (ch && typeof ch === 'object')
      ? (ch.title || ch.name || `第 ${i + 1} 章`)
      : String(ch || `第 ${i + 1} 章`)
    list.push({ id: chId, parent: rootId, text: title })

    const points = (ch && typeof ch === 'object')
      ? (ch.points || ch.items || [])
      : []
    ;(Array.isArray(points) ? points : []).forEach((p) => {
      const t = String(p || '').trim()
      if (t) list.push({ id: makeId(), parent: chId, text: t })
    })
  })

  nodes.value = list
  selected.value = rootId
  mark()
}

async function loadCourses() {
  try {
    const data = await api.history()
    courses.value = (data.courses || []).map((c) => c.course)
  } catch (_) {
    courses.value = []
  }
}

async function openFromPlan() {
  if (!course.value) {
    emit('notify', { type: 'error', text: '先选一门课程' })
    return
  }
  busy.value = true
  try {
    const data = await api.historyDetail(course.value)
    buildFromOutline(course.value, data.outline || [])
    emit('notify', { type: 'success', text: `已按《${course.value}》的大纲生成导图，可自由编辑` })
  } catch (e) {
    emit('notify', { type: 'error', text: `读取方案失败：${e.message}` })
  } finally {
    busy.value = false
  }
}

async function loadExisting() {
  if (!course.value) return
  busy.value = true
  try {
    const data = await api.mindmapGet(course.value)
    nodes.value = (data.map?.nodes || []).map((n) => ({ ...n }))
    selected.value = nodes.value.find((n) => !n.parent)?.id || ''
    dirty.value = false
    emit('notify', { type: 'success', text: `已载入《${course.value}》的思维导图` })
  } catch (e) {
    emit('notify', { type: 'error', text: `载入失败：${e.message}` })
  } finally {
    busy.value = false
  }
}

async function save() {
  if (!course.value) {
    emit('notify', { type: 'error', text: '先选一门课程' })
    return
  }
  if (!nodes.value.length) {
    emit('notify', { type: 'error', text: '导图是空的' })
    return
  }
  busy.value = true
  try {
    await api.mindmapSave(course.value, nodes.value)
    dirty.value = false
    emit('notify', { type: 'success', text: '思维导图已保存' })
  } catch (e) {
    emit('notify', { type: 'error', text: `保存失败：${e.message}` })
  } finally {
    busy.value = false
  }
}

function startBlank() {
  const rootId = makeId()
  nodes.value = [{ id: rootId, parent: null, text: course.value || '学习主题' }]
  selected.value = rootId
  mark()
}

onMounted(loadCourses)

const selectedNode = computed(() => nodes.value.find((n) => n.id === selected.value) || null)
</script>

<template>
  <section class="mm" :class="{ embedded }">
    <header v-if="!embedded" class="mm-head">
      <div>
        <p class="kicker">Mind map</p>
        <h1>{{ t('page.mindmapTitle') }}</h1>
        <p class="sub">{{ t('mindMapPage.3') }}</p>
      </div>
      <div class="head-actions">
        <button type="button" class="btn btn-ghost" @click="emit('back')">{{ t('mindMapPage.4') }}</button>
      </div>
    </header>

    <!-- 工具条 -->
    <div class="bar">
      <select v-model="course" class="sel">
        <option value="">{{ t('mindMapPage.5') }}</option>
        <option v-for="c in courses" :key="c" :value="c">{{ c }}</option>
      </select>
      <button type="button" class="btn btn-ghost sm" :disabled="busy || !course" @click="openFromPlan">{{ t('mindMapPage.6') }}</button>
      <button type="button" class="btn btn-ghost sm" :disabled="busy || !course" @click="loadExisting">{{ t('mindMapPage.7') }}</button>
      <button type="button" class="btn btn-ghost sm" :disabled="busy" @click="startBlank">{{ t('mindMapPage.8') }}</button>

      <span class="spacer" />

      <span class="cnt">
        {{ t('stat.mindmap', { n: stats.total, d: stats.depth }) }}
        <em v-if="dirty">{{ t('mindMapPage.9') }}</em>
      </span>
      <button type="button" class="btn btn-primary sm" :disabled="busy || !nodes.length" @click="save">
        {{ busy ? t('mindMapPageX.1') : t('mindMapPageX.2') }}
      </button>
    </div>

    <!-- 画布 -->
    <div v-if="!nodes.length" class="empty">
      <p class="e-ico">🗺</p>
      <p class="e-title">{{ t('mindMapPage.10') }}</p>
      <p class="e-sub">{{ t('mindMapPage.11') }}</p>
    </div>

    <template v-else>
      <div class="canvas-wrap">
        <div class="canvas-tools">
          <button type="button" class="ico-btn" :title="t('mindMapPage.1')" @click="zoom(-0.1)">−</button>
          <span class="zoom">{{ Math.round(scale * 100) }}%</span>
          <button type="button" class="ico-btn" :title="t('mindMapPage.2')" @click="zoom(0.1)">＋</button>
          <button type="button" class="btn btn-ghost sm" @click="resetZoom">{{ t('mindMapPage.12') }}</button>
        </div>

        <div class="canvas-scroll">
          <div
            class="canvas"
            :style="{
              width: laid.width * scale + 'px',
              height: laid.height * scale + 'px',
            }"
          >
            <div
              class="inner"
              :style="{
                transform: `scale(${scale})`,
                width: laid.width + 'px',
                height: laid.height + 'px',
              }"
            >
              <svg class="lines" :width="laid.width" :height="laid.height">
                <path v-for="l in links" :key="l.id" :d="l.d" />
              </svg>

              <div
                v-for="n in laid.list"
                :key="n.id"
                class="node"
                :class="{
                  root: !n.parent,
                  on: selected === n.id,
                }"
                :style="{ left: n._x + PAD + 'px', top: n._y + PAD + 'px', width: NODE_W + 'px', height: NODE_H + 'px' }"
                @click="selectNode(n.id)"
                @dblclick="startEdit(n)"
              >
                <input
                  v-if="editing === n.id"
                  v-model="editText"
                  class="node-input"
                  @keyup.enter="commitEdit"
                  @blur="commitEdit"
                  @click.stop
                  v-focus
                />
                <span v-else class="node-text">{{ n.text || t('mindMapPageX.3') }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 选中节点的操作 -->
        <div class="node-ops">
          <template v-if="selectedNode">
            <span class="ops-label">{{ t('mindMapPage.13') }}<b>{{ selectedNode.text || t('mindMapPageX.3') }}</b>
            </span>
            <button type="button" class="btn btn-ghost sm" @click="addChild(selectedNode.id)">{{ t('mindMapPage.14') }}</button>
            <button type="button" class="btn btn-ghost sm" @click="startEdit(selectedNode)">{{ t('mindMapPage.15') }}</button>
            <button
              type="button"
              class="btn btn-ghost sm danger"
              :disabled="!selectedNode.parent"
              @click="removeNode(selectedNode.id)"
            >{{ t('mindMapPage.16') }}</button>
          </template>
          <span v-else class="ops-label muted">{{ t('mindMapPage.17') }}</span>
        </div>
      </div>
    </template>
  </section>
</template>

<script>
// 自动聚焦正在编辑的输入框
export default {
  directives: {
    focus: {
      mounted(el) {
        el.focus()
        el.select()
      },
    },
  },
}
</script>

<style scoped>
.mm {
  max-width: 1180px;
  margin: 0 auto;
  padding: 4px 0 40px;
}

.mm-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.kicker {
  font-family: var(--font-serif);
  font-size: 11px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--primary);
}

.mm-head h1 {
  margin: 4px 0 6px;
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 400;
  color: var(--text-primary);
}

.sub {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 620px;
  line-height: 1.7;
}

/* ---------- 工具条 ---------- */
.bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 11px 14px;
  margin-bottom: 12px;
}

.spacer { flex: 1; }

.sel {
  border: 1px solid var(--border);
  background: var(--bg-card);
  border-radius: 8px;
  padding: 7px 11px;
  font-size: 13px;
  color: var(--text-primary);
  min-width: 180px;
}

.cnt {
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.cnt em {
  font-style: normal;
  color: var(--primary);
  font-weight: 600;
}

.btn.sm { padding: 6px 12px; font-size: 12.5px; }

.btn.danger { color: #b91c1c; border-color: #f3c4c7; }
.btn.danger:hover:not(:disabled) { background: var(--error-soft); }

/* ---------- 空态 ---------- */
.empty {
  text-align: center;
  padding: 52px 20px;
  background: var(--bg-card);
  border: 1px dashed var(--border-strong);
  border-radius: 12px;
  color: var(--text-muted);
}

.e-ico { font-size: 30px; margin: 0 0 8px; }
.e-title { margin: 0 0 6px; font-size: 15px; color: var(--text-primary); }
.e-sub { margin: 0 auto; font-size: 13px; line-height: 1.75; max-width: 440px; }

/* ---------- 画布 ---------- */
.canvas-wrap {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.canvas-tools {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 13px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-soft);
}

.ico-btn {
  width: 26px;
  height: 26px;
  border: 1px solid var(--border-strong);
  background: var(--bg-card);
  border-radius: 7px;
  font-size: 14px;
  line-height: 1;
  color: var(--text-primary);
  cursor: pointer;
}

.ico-btn:hover { border-color: var(--primary-light); }

.zoom {
  font-size: 12px;
  color: var(--text-muted);
  min-width: 42px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.canvas-scroll {
  overflow: auto;
  max-height: 62vh;
  background:
    radial-gradient(circle, var(--border) 1px, transparent 1px) 0 0 / 22px 22px;
}

.canvas {
  position: relative;
}

.inner {
  position: relative;
  transform-origin: 0 0;
}

.lines {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.lines path {
  fill: none;
  stroke: var(--border-strong);
  stroke-width: 1.5;
}

.node {
  position: absolute;
  display: flex;
  align-items: center;
  padding: 0 12px;
  border-radius: 9px;
  border: 1px solid var(--border-strong);
  background: var(--bg-card);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
  overflow: hidden;
}

.node:hover { border-color: var(--primary-light); }

.node.root {
  background: var(--primary);
  border-color: var(--primary);
}

.node.root .node-text { color: #fff; font-weight: 600; }

.node.on {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(229, 21, 32, 0.14);
}

.node-text {
  font-size: 12.5px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.node-input {
  width: 100%;
  border: none;
  outline: none;
  background: transparent;
  font-size: 12.5px;
  font-family: inherit;
  color: var(--text-primary);
}

.node.root .node-input { color: #fff; }

/* ---------- 节点操作 ---------- */
.node-ops {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 11px 14px;
  border-top: 1px solid var(--border);
}

.ops-label {
  font-size: 12.5px;
  color: var(--text-muted);
  margin-right: auto;
}

.ops-label b { color: var(--text-primary); font-weight: 600; }
.ops-label.muted { color: var(--text-faint); }

@media (max-width: 720px) {
  .bar { gap: 6px; }
  .cnt { display: none; }
  .ops-label { width: 100%; margin-bottom: 4px; }
}
</style>
