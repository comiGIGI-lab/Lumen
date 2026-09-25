<script setup>
/**
 * ResultsGrid —— 三栏结果区：课程大纲 / 推荐资源 / 学习计划
 * 数据结构完全对齐后端 run_plan_pipeline() 的返回（outline / resources / plan）。
 */
import { computed } from 'vue'
import ResultPanel from './ResultPanel.vue'

const props = defineProps({
  result: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  /** 学习进度：{outline:[{title,done}], plan:[{title,done}]}，索引与 result 一一对应 */
  progress: { type: Object, default: () => ({ outline: [], plan: [] }) },
})

const emit = defineEmits(['copy-outline', 'copy-plan', 'toggle-progress'])

const outline = computed(() => props.result?.outline || [])
const resources = computed(() => props.result?.resources || [])
const planItems = computed(() => props.result?.plan_items || [])

/** 该项是否已勾选 */
function isDone(kind, index) {
  const list = props.progress?.[kind] || []
  return !!list[index]?.done
}

/**
 * 计划项在**原始 plan** 里的下标。
 * 归一层会跳过 None / 空白项，所以渲染序号可能和进度索引错位 ——
 * 后端在 plan_items 上挂了 `_idx`，优先用它。
 */
function planIndex(item, i) {
  return typeof item?._idx === 'number' ? item._idx : i
}

function onToggle(kind, index, e) {
  emit('toggle-progress', { kind, index, done: e.target.checked })
}

// ---- B30 危机干预：后端返回 type=crisis 时不渲染三栏结果，改展示热线卡片 ----
const isCrisis = computed(() => props.result?.type === 'crisis')
const hotlines = computed(() => props.result?.hotlines || [])
const crisisLines = computed(() =>
  (props.result?.answer || '')
    .split('\n')
    .map((s) => s.trim())
    // 以「【」开头的是热线那两行，由下面的热线卡片单独渲染，正文里去掉避免重复
    .filter((s) => s && !s.startsWith('【')),
)

/** 资源类型 → 颜色 */
const typeChip = (t) => {
  const map = {
    视频: 'chip-cyan',
    书籍: 'chip-brand',
    教程: 'chip-success',
    社区: 'chip-slate',
    平台: 'chip-warn',
    网站: 'chip-slate',
  }
  return map[t] || 'chip-slate'
}

/** 计划天号 */
const dayNo = (item, i) => item?.day ?? i + 1
</script>

<template>
  <!-- B30 危机干预：后端判定为危机时，不展示三栏结果，只给热线 ——
       话术由后端固定下发，前端不做任何改写，也不上送大模型。 -->
  <section v-if="isCrisis" class="crisis">
    <div class="crisis-head">
      <div class="crisis-mark">♡</div>
      <div>
        <h3 class="crisis-title">先不着急做学习计划</h3>
        <p class="crisis-sub">我们检测到你可能正在经历很困难的时刻，这件事比课程更重要</p>
      </div>
    </div>

    <div class="crisis-body">
      <p v-for="(line, i) in crisisLines" :key="i" class="crisis-line">{{ line }}</p>
    </div>

    <div v-if="hotlines.length" class="crisis-hotlines">
      <a
        v-for="h in hotlines"
        :key="h.tel"
        class="crisis-hotline"
        :href="`tel:${h.tel.replace(/-/g, '')}`"
      >
        <span class="ch-name">{{ h.name }}</span>
        <span class="ch-tel">{{ h.tel }}</span>
        <span class="ch-note">{{ h.note }}</span>
      </a>
    </div>
  </section>

  <section v-else class="grid">
    <!-- ① 课程大纲 -->
    <ResultPanel
      title="课程大纲"
      icon="📑"
      unit="章"
      :count="outline.length"
      :loading="loading"
      empty-text="输入课程名并点击「生成方案」，Planner 会输出章节结构"
      accent="#e51520"
    >
      <div
        v-for="(ch, i) in outline"
        :key="i"
        class="outline-item"
        :class="{ done: isDone('outline', i) }"
      >
        <label class="pick" title="标记这一章已学完">
          <input
            type="checkbox"
            :checked="isDone('outline', i)"
            @change="onToggle('outline', i, $event)"
          />
        </label>
        <span class="outline-no">{{ String(i + 1).padStart(2, '0') }}</span>
        <span class="outline-text">{{ ch }}</span>
      </div>

      <template #footer>
        <button class="btn-link" @click="emit('copy-outline')">📋 复制大纲</button>
      </template>
    </ResultPanel>

    <!-- ② 推荐资源 -->
    <ResultPanel
      title="推荐资源"
      icon="🔗"
      unit="项"
      :count="resources.length"
      :loading="loading"
      empty-text="Searcher 会为课程检索书籍 / 视频 / 网站等学习资源"
      accent="#191919"
    >
      <div v-for="(r, i) in resources" :key="i" class="res-item">
        <div class="res-top">
          <span class="chip" :class="typeChip(r.type)">{{ r.type || '资源' }}</span>
          <span class="res-title">{{ r.title }}</span>
        </div>
        <a v-if="r.url" class="res-url" :href="r.url" target="_blank" rel="noopener noreferrer">
          {{ r.url }}
        </a>
        <span v-else class="res-url muted">（无直接链接）</span>
      </div>

      <template #footer>
        来源：{{ result?.degraded ? '内置资源库（LLM 不可用时兜底）' : 'Searcher Agent' }}
        <span class="res-disclaimer">· AI 推荐可能存在偏差，链接请自行核实</span>
      </template>
    </ResultPanel>

    <!-- ③ 学习计划 -->
    <ResultPanel
      title="学习计划"
      icon="📅"
      unit="天"
      :count="planItems.length"
      :loading="loading"
      empty-text="Writer 会结合大纲与用户画像编排每日学习任务"
      accent="#c4101a"
    >
      <div
        v-for="(item, i) in planItems"
        :key="i"
        class="plan-item"
        :class="{ done: isDone('plan', planIndex(item, i)) }"
      >
        <label class="pick" title="标记这一天已完成">
          <input
            type="checkbox"
            :checked="isDone('plan', planIndex(item, i))"
            @change="onToggle('plan', planIndex(item, i), $event)"
          />
        </label>
        <div class="plan-day">Day {{ dayNo(item, i) }}</div>
        <div class="plan-body">
          <p class="plan-task">{{ item.title }}</p>
          <div v-if="item.chapters?.length" class="plan-chapters">
            <span v-for="(c, ci) in item.chapters" :key="ci" class="chapter-tag">
              {{ c }}
            </span>
          </div>
          <ul v-if="item.tasks?.length" class="plan-tasks">
            <li v-for="(t, ti) in item.tasks" :key="ti">{{ t }}</li>
          </ul>
        </div>
      </div>

      <template #footer>
        <button class="btn-link" @click="emit('copy-plan')">📋 复制计划</button>
      </template>
    </ResultPanel>
  </section>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

/* ---------- 勾选框（学习进度） ---------- */
.pick {
  flex: none;
  display: flex;
  align-items: center;
  min-height: 22px;
  cursor: pointer;
}

.pick input {
  width: 15px;
  height: 15px;
  margin: 0;
  cursor: pointer;
  accent-color: var(--primary);
}

/* 已完成项压暗 + 划线，一眼看出还剩多少 */
.outline-item.done,
.plan-item.done {
  opacity: 0.6;
}

.outline-item.done .outline-text,
.plan-item.done .plan-task,
.plan-item.done .plan-tasks {
  text-decoration: line-through;
  text-decoration-color: var(--text-faint);
}

/* ---------- 大纲 ---------- */
.outline-item {
  display: flex;
  gap: 10px;
  padding: 9px 11px;
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary-light);
  transition: all 0.15s;
}

.outline-item:hover {
  background: var(--primary-soft);
  border-left-color: var(--primary);
}

.outline-no {
  flex: none;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--primary);
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 6px;
  width: 26px;
  height: 22px;
  display: grid;
  place-items: center;
}

.outline-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.55;
  word-break: break-word;
}

/* ---------- 资源 ---------- */
.res-item {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
  border: 1px solid var(--border);
  border-left: 3px solid var(--border-strong);
}

.res-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.res-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-word;
}

.res-url {
  display: block;
  margin-top: 5px;
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.res-url.muted {
  color: var(--text-faint);
}

.res-disclaimer {
  font-size: 11px;
  color: var(--text-faint);
}

/* ---------- 计划 ---------- */
.plan-item {
  display: flex;
  gap: 10px;
  padding: 10px 11px;
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary-light);
}

.plan-day {
  flex: none;
  font-size: 11px;
  font-weight: 800;
  color: var(--primary-dark);
  background: #fff;
  border: 1px solid #f3c4c7;
  border-radius: 6px;
  padding: 2px 7px;
  height: fit-content;
  white-space: nowrap;
}

.plan-body {
  min-width: 0;
}

.plan-task {
  font-size: 12.8px;
  color: var(--text-secondary);
  line-height: 1.6;
  word-break: break-word;
}

.plan-chapters {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 6px;
}

.chapter-tag {
  font-size: 10.5px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #fff;
  border: 1px dashed var(--border-strong);
  color: var(--text-muted);
}

.plan-tasks {
  margin: 6px 0 0;
  padding-left: 16px;
  font-size: 12px;
  color: var(--text-muted);
}

/* ---------- B30 危机干预 ---------- */
.crisis {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 4px solid #dc2626;
  border-radius: 12px;
  padding: 22px 24px;
}

.crisis-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.crisis-mark {
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: #fee2e2;
  color: #dc2626;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  line-height: 1;
}

.crisis-title {
  margin: 0 0 4px;
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 400;
  color: var(--text-primary);
}

.crisis-sub {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-muted);
}

.crisis-body {
  margin-bottom: 18px;
}

.crisis-line {
  margin: 0 0 8px;
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--text-secondary);
}

.crisis-line:last-child {
  margin-bottom: 0;
}

.crisis-hotlines {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.crisis-hotline {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  text-decoration: none;
  transition: background 0.15s;
}

.crisis-hotline:hover {
  background: #fee2e2;
}

.ch-name {
  font-size: 13px;
  font-weight: 600;
  color: #991b1b;
}

.ch-tel {
  font-size: 16px;
  font-weight: 700;
  color: #dc2626;
  font-variant-numeric: tabular-nums;
}

.ch-note {
  font-size: 11.5px;
  color: #b91c1c;
  opacity: 0.85;
}

@media (max-width: 1080px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
