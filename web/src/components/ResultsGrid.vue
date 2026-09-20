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
})

const emit = defineEmits(['copy-outline', 'copy-plan'])

const outline = computed(() => props.result?.outline || [])
const resources = computed(() => props.result?.resources || [])
const planItems = computed(() => props.result?.plan_items || [])

/** 资源类型 → 颜色 */
const typeChip = (t) => {
  const map = {
    视频: 'chip-cyan',
    书籍: 'chip-indigo',
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
  <section class="grid">
    <!-- ① 课程大纲 -->
    <ResultPanel
      title="课程大纲"
      icon="📑"
      unit="章"
      :count="outline.length"
      :loading="loading"
      empty-text="输入课程名并点击「生成方案」，Planner 会输出章节结构"
      accent="#6366f1"
    >
      <div v-for="(ch, i) in outline" :key="i" class="outline-item">
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
      accent="#06b6d4"
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
      accent="#8b5cf6"
    >
      <div v-for="(item, i) in planItems" :key="i" class="plan-item">
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
  border-left: 3px solid #67e8f9;
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
  border-left: 3px solid #c4b5fd;
}

.plan-day {
  flex: none;
  font-size: 11px;
  font-weight: 800;
  color: var(--primary-dark);
  background: #fff;
  border: 1px solid #ddd6fe;
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

@media (max-width: 1080px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
