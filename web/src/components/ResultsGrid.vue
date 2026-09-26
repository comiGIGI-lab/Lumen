<script setup>
/**
 * ResultsGrid —— 三栏结果区：课程大纲 / 推荐资源 / 学习计划
 * 数据结构完全对齐后端 run_plan_pipeline() 的返回（outline / resources / plan）。
 */
import { computed } from 'vue'
import { useI18n } from '@/i18n'
import ResultPanel from './ResultPanel.vue'

const props = defineProps({
  result: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  /** 学习进度：{outline:[{title,done}], plan:[{title,done}]}，索引与 result 一一对应 */
  progress: { type: Object, default: () => ({ outline: [], plan: [] }) },
})
const { t } = useI18n()

const emit = defineEmits(['copy-outline', 'copy-plan', 'toggle-progress', 'export'])

const outline = computed(() => props.result?.outline || [])
const resources = computed(() => props.result?.resources || [])
const planItems = computed(() => props.result?.plan_items || [])
const canExport = computed(
  () => !props.loading && !!(outline.value.length || planItems.value.length || props.result?.plan?.length),
)

/**
 * 大纲归一化：每章 → {title, points}。
 * 后端从 v20 起返回章节对象 {"title", "points"}；旧的纯字符串项也兼容，
 * 否则直接 {{ ch }} 会渲染成 "object Object"。
 */
const outlineItems = computed(() =>
  outline.value.map((ch, i) => {
    if (ch && typeof ch === 'object' && !Array.isArray(ch)) {
      const title = String(ch.title || ch.name || `第 ${i + 1} 章`).trim()
      const points = (ch.points || ch.items || [])
        .map((p) => String(p).trim())
        .filter(Boolean)
      return { title, points }
    }
    return { title: String(ch || '').trim() || `第 ${i + 1} 章`, points: [] }
  }),
)

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
        <h3 class="crisis-title">{{ t('resultsGrid.6') }}</h3>
        <p class="crisis-sub">{{ t('resultsGrid.7') }}</p>
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

  <section v-else class="results-layout">
    <div class="outline-scroll-col">
    <!-- ① 课程大纲 -->
    <ResultPanel
      :title="t('resultsGrid.1')"
      icon="📑"
      unit="章"
      :count="outline.length"
      :loading="loading"
      :empty-text="t('stage.plannerEmpty')"
      accent="#e51520"
    >
      <div
        v-for="(ch, i) in outlineItems"
        :key="i"
        class="outline-item"
        :class="{ done: isDone('outline', i) }"
      >
        <label class="pick" :title="t('resultsGrid.2')">
          <input
            type="checkbox"
            :checked="isDone('outline', i)"
            @change="onToggle('outline', i, $event)"
          />
        </label>
        <span class="outline-no">{{ String(i + 1).padStart(2, '0') }}</span>
        <div class="outline-body">
          <span class="outline-text">{{ ch.title }}</span>
          <ul v-if="ch.points.length" class="outline-points">
            <li v-for="(p, pi) in ch.points" :key="pi">{{ p }}</li>
          </ul>
        </div>
      </div>

      <template #footer>
        <button class="btn-link" @click="emit('copy-outline')">{{ t('resultsGrid.8') }}</button>
      </template>
    </ResultPanel>
    </div>

    <div class="content-scroll-col">
    <!-- ② 推荐资源 -->
    <ResultPanel
      :title="t('resultsGrid.3')"
      icon="🔗"
      unit="项"
      :count="resources.length"
      :loading="loading"
      :empty-text="t('stage.searcherEmpty')"
      accent="#191919"
    >
      <div v-for="(r, i) in resources" :key="i" class="res-item">
        <div class="res-top">
          <span class="chip" :class="typeChip(r.type)">{{ r.type || t('resultsGridX.1') }}</span>
          <span class="res-title">{{ r.title }}</span>
        </div>
        <a v-if="r.url" class="res-url" :href="r.url" target="_blank" rel="noopener noreferrer">
          {{ r.url }}
        </a>
        <span v-else class="res-url muted">{{ t('resultsGrid.9') }}</span>
      </div>

      <template #footer>
        {{ t('src.label') }}{{ result?.degraded ? t('resultsGridX.2') : 'Searcher Agent' }}
        <span class="res-disclaimer">{{ t('resultsGrid.10') }}</span>
      </template>
    </ResultPanel>

    </div>

    <div class="content-scroll-col">
    <!-- ③ 学习计划 -->
    <ResultPanel
      :title="t('resultsGrid.4')"
      icon="📅"
      unit="天"
      :count="planItems.length"
      :loading="loading"
      :empty-text="t('stage.writerEmpty')"
      accent="#c4101a"
    >
      <div
        v-for="(item, i) in planItems"
        :key="i"
        class="plan-item"
        :class="{ done: isDone('plan', planIndex(item, i)) }"
      >
        <label class="pick" :title="t('resultsGrid.5')">
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
        <button class="btn-link" @click="emit('copy-plan')">{{ t('resultsGrid.11') }}</button>
      </template>
    </ResultPanel>
    </div>

    <div v-if="canExport" class="export-action-card card">
        <div class="eac-left">
          <div class="eac-icon">📑</div>
          <div>
            <h4 class="eac-title">{{ t('app.4') }}</h4>
            <p class="eac-desc">{{ t('app.5') }}</p>
          </div>
        </div>
        <button type="button" class="btn btn-primary eac-btn" @click="emit('export')">
          {{ t('app.6') }}
        </button>
      </div>
  </section>
</template>

<style scoped>
.results-layout {
  display: grid;
  /* 三栏并排：课程大纲 | 推荐资源 | 学习计划 */
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}

.outline-scroll-col {
  max-height: 60vh;
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  padding-right: 4px;
}

.outline-scroll-col::-webkit-scrollbar {
  width: 6px;
}
.outline-scroll-col::-webkit-scrollbar-thumb {
  background: var(--border, #e4ded5);
  border-radius: 3px;
}
.outline-scroll-col::-webkit-scrollbar-thumb:hover {
  background: var(--border-strong, #c8c0b5);
}

.outline-scroll-col :deep(.panel) {
  min-height: 0;
}
.outline-scroll-col :deep(.panel-body) {
  max-height: none;
  overflow-y: visible;
}

.content-scroll-col {
  max-height: 60vh;
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-right: 4px;
}

.content-scroll-col::-webkit-scrollbar {
  width: 6px;
}
.content-scroll-col::-webkit-scrollbar-thumb {
  background: var(--border, #e4ded5);
  border-radius: 3px;
}
.content-scroll-col::-webkit-scrollbar-thumb:hover {
  background: var(--border-strong, #c8c0b5);
}

.content-scroll-col :deep(.panel) {
  min-height: 0;
}
.content-scroll-col :deep(.panel-body) {
  max-height: none;
  overflow-y: visible;
}

.export-action-card {
  grid-column: 1 / -1;  /* 三栏下方横跨整行 */
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-top: 3px solid var(--primary);
  border-radius: var(--radius-md, 8px);
}

.eac-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.eac-icon {
  font-size: 20px;
}

.eac-title {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 15px;
  font-weight: 500;
  color: var(--text-primary);
}

.eac-desc {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.eac-btn {
  flex: none;
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
.outline-item.done .outline-points,
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
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  width: 26px;
  height: 22px;
  display: grid;
  place-items: center;
}

.outline-body {
  min-width: 0;
}

.outline-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.55;
  word-break: break-word;
}

.outline-points {
  margin: 5px 0 0;
  padding-left: 16px;
  list-style: disc;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.6;
  word-break: break-word;
}

.outline-points li {
  margin-top: 2px;
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
  background: var(--bg-card);
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
  background: var(--bg-card);
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
  background: var(--error-soft);
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
  background: var(--error-soft);
  border: 1px solid #fecaca;
  text-decoration: none;
  transition: background 0.15s;
}

.crisis-hotline:hover {
  background: var(--error-soft);
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
  .results-layout {
    grid-template-columns: 1fr;
    gap: 14px;
  }
  .outline-scroll-col {
    max-height: 50vh;
  }
  .content-scroll-col {
    max-height: 55vh;
  }
}
</style>
