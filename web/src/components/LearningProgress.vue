<script setup>
/**
 * LearningProgress —— 学情总览
 *
 * 汇总本浏览器名下所有课程的勾选完成度（数据来自 /api/progress/overview，
 * 底层就是桌面版就有的 tools/progress_store.py）。
 * 勾选动作在「学习方案生成」页的结果区完成，这里只做汇总与回看。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/api/client'
import { useI18n } from '@/i18n'

const emit = defineEmits(['back', 'open-course', 'notify'])
const { t } = useI18n()

const loading = ref(false)
const courses = ref([])
const summary = ref({ courses: 0, done: 0, total: 0, ratio: 0 })
const expanded = ref('')

const percent = computed(() => Math.round((summary.value.ratio || 0) * 100))

/** 完成度环形图的描边偏移（r=34 → 周长 213.6） */
const ringDash = computed(() => {
  const C = 2 * Math.PI * 34
  const on = C * (summary.value.ratio || 0)
  return `${on.toFixed(1)} ${(C - on).toFixed(1)}`
})

function coursePercent(c) {
  return Math.round((c.ratio || 0) * 100)
}

function fmtTime(t) {
  const s = String(t || '').trim()
  if (!s) return '—'
  return s.length > 16 ? s.slice(5, 16) : s
}

async function load() {
  loading.value = true
  try {
    const data = await api.progressOverview()
    courses.value = (data.courses || []).filter((c) => c.total > 0)
    summary.value = data.summary || summary.value
  } catch (e) {
    emit('notify', { type: 'error', text: `加载失败：${e.message}` })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="lp">
    <header class="lp-head">
      <div>
        <p class="kicker">Study progress</p>
        <h1>{{ t('page.progressTitle') }}</h1>
        <p class="sub">
          勾选动作在方案结果区完成（大纲每一章、计划每一天都能打勾），
          这里汇总所有课程的完成情况。
        </p>
      </div>
      <div class="head-actions">
        <button type="button" class="btn btn-ghost" @click="load">刷新</button>
        <button type="button" class="btn btn-ghost" @click="emit('back')">返回</button>
      </div>
    </header>

    <!-- 总览 -->
    <div class="overview">
      <div class="ring">
        <svg viewBox="0 0 80 80" aria-hidden="true">
          <circle class="ring-bg" cx="40" cy="40" r="34" />
          <circle
            class="ring-fg"
            cx="40"
            cy="40"
            r="34"
            :stroke-dasharray="ringDash"
          />
        </svg>
        <div class="ring-num">
          <b>{{ percent }}<i>%</i></b>
          <span>总体完成</span>
        </div>
      </div>
      <div class="ov-stats">
        <div class="ov">
          <span class="n">{{ summary.courses }}</span>
          <span class="l">在学课程</span>
        </div>
        <div class="ov">
          <span class="n">{{ summary.done }}</span>
          <span class="l">已完成项</span>
        </div>
        <div class="ov">
          <span class="n">{{ summary.total }}</span>
          <span class="l">总项数</span>
        </div>
      </div>
    </div>

    <!-- 列表 -->
    <div v-if="loading" class="empty">加载中…</div>

    <div v-else-if="!courses.length" class="empty">
      <p class="e-ico">📈</p>
      <p class="e-title">还没有可统计的课程</p>
      <p class="e-sub">
        先去生成一份学习方案，然后在结果区把学完的章节和当天任务勾上，
        这里就会出现进度。
      </p>
      <button type="button" class="btn btn-primary" @click="emit('open-course')">
        去生成学习方案
      </button>
    </div>

    <ul v-else class="list">
      <li v-for="c in courses" :key="c.course" class="row">
        <button
          type="button"
          class="row-main"
          @click="expanded = expanded === c.course ? '' : c.course"
        >
          <span class="c-name">{{ c.course }}</span>
          <span class="c-bar">
            <i :style="{ width: coursePercent(c) + '%' }" />
          </span>
          <span class="c-num">{{ c.done }} / {{ c.total }}</span>
          <span class="c-pct" :class="{ full: coursePercent(c) === 100 }">
            {{ coursePercent(c) }}%
          </span>
        </button>

        <div v-if="expanded === c.course" class="row-detail">
          <p class="d-line">
            <b>创建时间</b><span>{{ fmtTime(c.created_at) }}</span>
          </p>
          <p class="d-line">
            <b>最近学习</b><span>{{ fmtTime(c.last_seen_at) }}</span>
          </p>
          <div class="d-actions">
            <button type="button" class="btn btn-ghost sm" @click="emit('open-course', c.course)">
              打开这门课
            </button>
          </div>
        </div>
      </li>
    </ul>

    <p class="foot">
      进度数据存在后端的 <code>progress.json</code> 里，按浏览器隔离，换设备不会串。
    </p>
  </section>
</template>

<style scoped>
.lp {
  max-width: 940px;
  margin: 0 auto;
  padding: 4px 0 40px;
}

.lp-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.kicker {
  font-family: var(--font-serif);
  font-size: 11px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--primary);
}

.lp-head h1 {
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
  max-width: 560px;
  line-height: 1.7;
}

.head-actions {
  display: flex;
  gap: 8px;
}

/* ---------- 总览 ---------- */
.overview {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 28px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 22px;
  margin-bottom: 16px;
}

.ring {
  position: relative;
  width: 92px;
  height: 92px;
  flex: none;
}

.ring svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.ring-bg {
  fill: none;
  stroke: var(--bg-soft);
  stroke-width: 7;
}

.ring-fg {
  fill: none;
  stroke: var(--primary);
  stroke-width: 7;
  stroke-linecap: round;
  transition: stroke-dasharray 0.4s ease;
}

.ring-num {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
}

.ring-num b {
  font-family: var(--font-serif);
  font-size: 22px;
  font-weight: 400;
  color: var(--text-primary);
  line-height: 1;
}

.ring-num b i {
  font-style: normal;
  font-size: 12px;
  color: var(--text-muted);
}

.ring-num span {
  font-size: 10.5px;
  color: var(--text-faint);
}

.ov-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 30px;
}

.ov {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ov .n {
  font-family: var(--font-serif);
  font-size: 26px;
  color: var(--text-primary);
  line-height: 1.1;
}

.ov .l {
  font-size: 11.5px;
  color: var(--text-muted);
}

/* ---------- 列表 ---------- */
.empty {
  text-align: center;
  padding: 44px 20px;
  background: var(--bg-card);
  border: 1px dashed var(--border-strong);
  border-radius: 12px;
  color: var(--text-muted);
}

.e-ico {
  font-size: 30px;
  margin: 0 0 8px;
}

.e-title {
  margin: 0 0 6px;
  font-size: 15px;
  color: var(--text-primary);
}

.e-sub {
  margin: 0 auto 16px;
  font-size: 13px;
  line-height: 1.75;
  max-width: 460px;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

.row-main {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 13px 16px;
  background: transparent;
  border: none;
  text-align: left;
}

.row-main:hover {
  background: var(--bg-soft);
}

.c-name {
  flex: 0 1 220px;
  min-width: 0;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.c-bar {
  flex: 1 1 auto;
  height: 7px;
  min-width: 60px;
  border-radius: 999px;
  background: var(--bg-soft);
  border: 1px solid var(--border);
  overflow: hidden;
}

.c-bar i {
  display: block;
  height: 100%;
  background: var(--primary);
  transition: width 0.3s ease;
}

.c-num {
  flex: none;
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.c-pct {
  flex: none;
  width: 48px;
  text-align: right;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.c-pct.full {
  color: #15803d;
}

.row-detail {
  padding: 4px 16px 14px;
  border-top: 1px solid var(--border);
  background: var(--bg-soft);
}

.d-line {
  display: flex;
  gap: 10px;
  margin: 8px 0 0;
  font-size: 12.5px;
  color: var(--text-secondary);
}

.d-line b {
  flex: none;
  width: 68px;
  font-weight: 600;
  font-size: 11.5px;
  color: var(--text-muted);
  padding-top: 1px;
}

.d-actions {
  margin-top: 10px;
}

.btn.sm {
  padding: 5px 11px;
  font-size: 12px;
}

.foot {
  margin: 18px 0 0;
  font-size: 11.5px;
  color: var(--text-faint);
  text-align: center;
}

.foot code {
  font-family: var(--font-mono);
  background: var(--bg-soft);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 11px;
}

@media (max-width: 620px) {
  .c-name {
    flex-basis: 110px;
  }
  .c-num {
    display: none;
  }
}
</style>
