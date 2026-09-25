<script setup>
import { useI18n } from '@/i18n'
/**
 * PipelineStepper —— Agent 流水线可视化
 *
 * 展示「课程名 → 生成方案」这条链路里四个 Agent 的真实执行状态：
 *   Planner → Searcher → Writer → Reviewer（不达标会回环重跑）
 *
 * 每个节点的状态与产出数量都来自后端 trace.log，不是前端假动画。
 */
import { STAGES } from '@/composables/usePlanStream'

const props = defineProps({
  steps: { type: Object, required: true },
  status: { type: String, default: 'idle' },
  activeIndex: { type: Number, default: -1 },
  progress: { type: Object, default: () => ({ done: 0, total: 4, percent: 0 }) },
  meta: { type: Object, default: null },
})
const { t } = useI18n()

/** 把节点产出的计数翻译成人话 */
function summary(key, data) {
  if (!data) return ''
  if (key === 'planner' && data.outline_count != null) return `${data.outline_count} 章`
  if (key === 'searcher' && data.resource_count != null) return `${data.resource_count} 条`
  if (key === 'writer' && data.plan_count != null) return `${data.plan_count} 天`
  if (key === 'reviewer' && data.ok != null) {
    return data.ok ? '质检通过' : (data.comments || []).join('；') || '未通过'
  }
  return ''
}

function nodeClass(key, index) {
  const st = props.steps[key]?.status
  if (st === 'done') return 'is-done'
  if (st === 'running') return 'is-running'
  if (props.status === 'done') return 'is-done'
  return 'is-idle'
}

/** 节点描述文案：运行中显示动作，完成后显示真实产出，空闲显示职责 */
function desc(key, stage) {
  const st = props.steps[key]
  if (!st) return t(stage.descKey)
  if (st.status === 'running') return st.hint || t('stage.running', { title: t(stage.titleKey) })
  if (st.status === 'done') {
    const sum = summary(key, st.data)
    return sum
      ? t('stage.generated', { title: t(stage.titleKey), n: sum })
      : t('stage.done', { title: t(stage.titleKey) })
  }
  return t(stage.descKey)
}
</script>

<template>
  <section class="pipeline card">
    <div class="pipe-head">
      <div class="pipe-title">
        <span class="dot"></span>{{ t('pipelineStepper.1') }}<span class="stage-count">
          {{ progress.done }} / {{ progress.total }}
        </span>
      </div>

      <div class="pipe-meta">
        <template v-if="meta">
          <span class="chip chip-brand">{{ meta.course }}</span>
          <span v-if="meta.profile_text" class="pipe-profile">{{ meta.profile_text }}</span>
        </template>
        <template v-else>
          <span class="pipe-hint">{{ t('pipelineStepper.2') }}</span>
        </template>
      </div>
    </div>

    <div class="pipe-track">
      <div class="pipe-progress">
        <div
          class="pipe-progress-bar"
          :class="{ flowing: status === 'running' }"
          :style="{ width: progress.percent + '%' }"
        ></div>
      </div>

      <div class="nodes">
        <div
          v-for="(stage, i) in STAGES"
          :key="stage.key"
          class="node"
          :class="nodeClass(stage.key, i)"
        >
          <div class="node-icon">
            <span v-if="steps[stage.key]?.status === 'running'" class="spinner"></span>
            <span v-else-if="steps[stage.key]?.status === 'done'">✓</span>
            <span v-else>{{ stage.icon }}</span>
          </div>

          <div class="node-body">
            <div class="node-name">
              {{ stage.name }}
              <span class="tag" v-if="summary(stage.key, steps[stage.key]?.data)">
                {{ summary(stage.key, steps[stage.key]?.data) }}
              </span>
            </div>
            <div class="node-desc">
              {{ desc(stage.key, stage) }}
            </div>
          </div>

          <div v-if="i < STAGES.length - 1" class="arrow" :class="{ active: steps[stage.key]?.status === 'done' }">
            →
          </div>
        </div>
      </div>
    </div>

    <div v-if="status === 'running'" class="pipe-foot running">
      <span class="pulse"></span>{{ t('pipelineStepper.3') }}<code>run_plan_pipeline()</code>{{ t('pipelineStepper.4') }}</div>
    <div v-else-if="status === 'done'" class="pipe-foot ok">{{ t('pipelineStepper.5') }}</div>
    <div v-else-if="status === 'error'" class="pipe-foot err">{{ t('pipelineStepper.6') }}</div>
  </section>
</template>

<style scoped>
.pipeline {
  padding: 14px 18px 12px;
}

.pipe-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.pipe-title {
  font-family: var(--font-serif);
  font-size: 15px;
  font-weight: 400;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: 0 0 0 4px rgba(229, 21, 32, 0.14);
}

.stage-count {
  font-size: 11px;
  font-weight: 700;
  color: var(--primary-dark);
  background: var(--primary-soft);
  border: 1px solid #f3c4c7;
  border-radius: 999px;
  padding: 1px 9px;
}

.pipe-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.pipe-profile,
.pipe-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.pipe-track {
  position: relative;
}

/* 顶部进度条 */
.pipe-progress {
  height: 3px;
  border-radius: 3px;
  background: var(--bg-disabled);
  overflow: hidden;
  margin-bottom: 14px;
}

.pipe-progress-bar {
  height: 100%;
  border-radius: 3px;
  background: var(--primary);
  transition: width 0.4s ease;
}

.pipe-progress-bar.flowing {
  background-image: linear-gradient(
    90deg,
    var(--grad-from) 0 6px,
    rgba(var(--bg-card-rgb), 0.85) 6px 12px,
    var(--grad-from) 12px 18px
  );
  background-size: 24px 100%;
  animation: flow 0.7s linear infinite;
}

.nodes {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.node {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 13px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-soft);
  transition: all 0.25s ease;
}

.node.is-idle {
  opacity: 0.72;
}

.node.is-running {
  border-color: var(--primary-light);
  background: var(--primary-soft);
  box-shadow: 0 0 0 3px rgba(229, 21, 32, 0.12);
}

.node.is-done {
  border-color: #a7f3d0;
  background: var(--success-soft);
}

.node-icon {
  flex: 0 0 26px;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-size: 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
}

.node.is-running .node-icon {
  border-color: var(--primary-light);
  color: var(--primary-dark);
  font-weight: 700;
}

.node.is-done .node-icon {
  border-color: #6ee7b7;
  background: var(--success);
  color: #fff;
  font-weight: 800;
}

.spinner {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid rgba(229, 21, 32, 0.28);
  border-top-color: var(--primary);
  animation: spin 0.7s linear infinite;
}

.node-body {
  min-width: 0;
}

.node-name {
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.tag {
  font-size: 10.5px;
  font-weight: 700;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-muted);
}

.node.is-done .tag {
  border-color: #a7f3d0;
  color: #047857;
}

.node-desc {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 2px;
  line-height: 1.5;
  word-break: break-word;
}

.arrow {
  position: absolute;
  right: -12px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 13px;
  color: var(--border-strong);
  z-index: 2;
}

.arrow.active {
  color: var(--success);
  font-weight: 700;
}

.pipe-foot {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.pipe-foot code {
  font-family: var(--font-mono);
  font-size: 11.5px;
  background: rgba(15, 23, 42, 0.06);
  padding: 1px 5px;
  border-radius: 4px;
}

.pipe-foot.running {
  background: var(--warning-soft);
  border: 1px solid #fde68a;
  color: #b45309;
}

.pipe-foot.ok {
  background: var(--success-soft);
  border: 1px solid #a7f3d0;
  color: #047857;
  font-weight: 600;
}

.pipe-foot.err {
  background: var(--error-soft);
  border: 1px solid #fecaca;
  color: #b91c1c;
  font-weight: 600;
}

.pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--warning);
  animation: pulse-soft 1s ease-in-out infinite;
}

@media (max-width: 900px) {
  .nodes {
    grid-template-columns: 1fr 1fr;
  }
  .arrow {
    display: none;
  }
}
</style>
