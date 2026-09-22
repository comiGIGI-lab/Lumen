<script setup>
/**
 * WelcomeScreen —— 首访欢迎层（全屏覆盖，关闭后进入工具界面）
 *
 * 定位：项目语言内的「产品入口页」，五段结构
 *   HERO（渐变头图）→ 三项功能卡 → 三步流程 → CTA → 页脚（联系方式 + 隐私说明）
 *
 * 视觉完全复用 global.css 现有令牌（indigo→紫渐变 / slate 文字 / 8-12-18 圆角 / 柔和阴影）
 * 与 .card / .chip / .btn 通用类，保证与主应用无缝。
 *
 * 显示时机由 App.vue 控制：首访（localStorage 无 zjxt.welcomed）时出现；
 * 深链（?course= / ?auto=1）不弹，避免打断可分享的演示链接。
 */
import { ref } from 'vue'

const emit = defineEmits(['start'])

const showPrivacy = ref(false)

function onStart() {
  emit('start')
}
</script>

<template>
  <div class="welcome" role="dialog" aria-label="欢迎页">
    <!-- 右上角：直接跳过 -->
    <button class="skip" type="button" @click="onStart">直接进入 →</button>

    <!-- ① HERO -->
    <section class="wl-hero">
      <div class="wl-hero-bg" aria-hidden="true"></div>
      <div class="wl-hero-in">
        <div class="wl-logo">📘</div>
        <h1 class="wl-title">智识有方</h1>
        <p class="wl-sub">多模态教学智能体</p>
        <p class="wl-desc">
          输入课程名与学习画像，Agent 链路生成课程大纲、推荐资源与个性化学习计划
        </p>
        <div class="wl-hero-actions">
          <button class="wl-btn-solid" type="button" @click="onStart">开始使用</button>
          <a class="wl-btn-ghost" href="/prototypes/" target="_blank" rel="noopener">
            界面原型
          </a>
        </div>
      </div>
    </section>

    <!-- ② 三项功能（对齐赛题原文） -->
    <section class="wl-sec">
      <h2 class="wl-sec-title">三项能力，覆盖一次完整的学习准备</h2>
      <p class="wl-sec-sub">从素材解析到知识抽取，再到答疑核对，都建立在课程内容之上</p>
      <div class="wl-grid">
        <div class="card card-pad wl-feat">
          <div class="wl-feat-ico ico-indigo">🖼️</div>
          <h3>图文素材智能解析</h3>
          <p>课件 PDF、板书照片与课堂录音统一导入，自动识别文字与语音，切成可检索的内容块</p>
        </div>
        <div class="card card-pad wl-feat">
          <div class="wl-feat-ico ico-cyan">🧩</div>
          <h3>知识点结构化抽取</h3>
          <p>从解析结果中抽取知识点，整理为课程大纲与知识结构，并标注薄弱环节</p>
        </div>
        <div class="card card-pad wl-feat">
          <div class="wl-feat-ico ico-slate">💬</div>
          <h3>交互式答疑辅导</h3>
          <p>基于你自己的课程内容作答，答案标注出处，可以继续追问与逐条核对</p>
        </div>
      </div>
    </section>

    <!-- ③ 三步流程 -->
    <section class="wl-sec">
      <h2 class="wl-sec-title">三步拿到一份可执行的学习方案</h2>
      <div class="wl-grid">
        <div class="card card-pad wl-step">
          <span class="chip chip-indigo">第 1 步</span>
          <h3>输入课程名与画像</h3>
          <p>课程名，加上水平、每日时长与目标，几项选择即可完成设定</p>
        </div>
        <div class="card card-pad wl-step">
          <span class="chip chip-cyan">第 2 步</span>
          <h3>Agent 链路执行</h3>
          <p>Planner → Searcher → Writer → Reviewer 依次规划、检索、成稿与校验</p>
        </div>
        <div class="card card-pad wl-step">
          <span class="chip chip-slate">第 3 步</span>
          <h3>三栏结果与答疑</h3>
          <p>大纲、推荐资源、学习计划一次呈现，支持导出，也可继续提问</p>
        </div>
      </div>
    </section>

    <!-- ④ CTA -->
    <section class="wl-sec">
      <div class="card card-pad wl-cta">
        <h2>从一门课程开始</h2>
        <p>不需要预先整理资料，进入后输入课程名即可生成</p>
        <button class="btn btn-primary wl-cta-btn" type="button" @click="onStart">
          开始使用
        </button>
      </div>
    </section>

    <!-- ⑤ 页脚 -->
    <footer class="wl-foot">
      <p>粤港澳大湾区 AI Coding 创新大赛 · 方向一 多模态教学智能体</p>
      <p class="wl-foot-links">
        <a href="mailto:team@zhishiyoufang.example">team@zhishiyoufang.example</a>
        <button class="wl-privacy-btn" type="button" @click="showPrivacy = true">
          隐私说明
        </button>
      </p>
    </footer>

    <!-- 隐私说明弹层（文案沿用原型页既定版本） -->
    <div v-if="showPrivacy" class="wl-modal" @click.self="showPrivacy = false">
      <div class="card card-pad wl-modal-card">
        <h3>隐私说明</h3>
        <p>本页面为参赛原型演示，不收集任何个人信息。</p>
        <p>演示所用的笔记、文档与学习记录均保存在你本机浏览器中，不会上传到服务器。</p>
        <p>页面上的解析状态、分块数量与统计数字均为演示用示例数据。</p>
        <div class="wl-modal-foot">
          <button class="btn btn-ghost" type="button" @click="showPrivacy = false">
            知道了
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ---------- 覆盖层 ---------- */
.welcome {
  position: fixed;
  inset: 0;
  z-index: 90; /* Toast(100) 之下，其余界面之上 */
  overflow-y: auto;
  background: var(--bg-app);
  animation: fade-up 0.24s ease both;
}

.skip {
  position: fixed;
  top: 14px;
  right: 16px;
  z-index: 95;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-muted);
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.skip:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* ---------- ① HERO：与 AppHeader 同一条渐变 ---------- */
.wl-hero {
  position: relative;
  overflow: hidden;
  background: linear-gradient(120deg, #6366f1 0%, #7c5cf6 50%, #8b5cf6 100%);
  color: #fff;
  text-align: center;
  padding: 72px 24px 64px;
}

.wl-hero-bg {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(
      circle at 12% 20%,
      rgba(255, 255, 255, 0.24),
      transparent 42%
    ),
    radial-gradient(circle at 88% 90%, rgba(6, 182, 212, 0.34), transparent 46%);
}

.wl-hero-in {
  position: relative;
  max-width: 720px;
  margin: 0 auto;
}

.wl-logo {
  width: 64px;
  height: 64px;
  margin: 0 auto 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.3);
  display: grid;
  place-items: center;
  font-size: 32px;
  backdrop-filter: blur(6px);
}

.wl-title {
  font-size: 40px;
  font-weight: 800;
  letter-spacing: 0.5px;
  line-height: 1.2;
}

.wl-sub {
  margin-top: 6px;
  font-size: 16px;
  font-weight: 600;
  opacity: 0.92;
}

.wl-desc {
  margin-top: 14px;
  font-size: 14px;
  line-height: 1.8;
  opacity: 0.88;
  max-width: 34em;
  margin-left: auto;
  margin-right: auto;
}

.wl-hero-actions {
  margin-top: 26px;
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.wl-btn-solid {
  border: 1px solid #fff;
  background: #fff;
  color: var(--primary-dark);
  border-radius: var(--radius-sm);
  padding: 10px 26px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
}

.wl-btn-solid:hover {
  filter: brightness(0.96);
  transform: translateY(-1px);
}

.wl-btn-ghost {
  border: 1px solid rgba(255, 255, 255, 0.32);
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border-radius: var(--radius-sm);
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s;
}

.wl-btn-ghost:hover {
  background: rgba(255, 255, 255, 0.24);
}

/* ---------- 通用区块 ---------- */
.wl-sec {
  max-width: 1080px;
  margin: 0 auto;
  padding: 44px 26px 8px;
}

.wl-sec-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  text-align: center;
}

.wl-sec-sub {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
}

.wl-grid {
  margin-top: 22px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--gap-lg);
}

.wl-feat h3,
.wl-step h3 {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 10px 0 6px;
}

.wl-feat p,
.wl-step p {
  font-size: 13px;
  line-height: 1.75;
  color: var(--text-muted);
}

/* 功能卡图标：沿用 chip 的三组柔和底色 */
.wl-feat-ico {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  font-size: 20px;
}

.ico-indigo {
  background: var(--primary-soft);
  border: 1px solid #c7d2fe;
}

.ico-cyan {
  background: var(--accent-soft);
  border: 1px solid #a5f3fc;
}

.ico-slate {
  background: var(--bg-disabled);
  border: 1px solid var(--border);
}

/* ---------- ④ CTA ---------- */
.wl-cta {
  text-align: center;
  padding: 34px 24px;
}

.wl-cta h2 {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.wl-cta p {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-muted);
}

.wl-cta-btn {
  margin-top: 18px;
}

/* ---------- ⑤ 页脚 ---------- */
.wl-foot {
  max-width: 1080px;
  margin: 0 auto;
  padding: 36px 26px 40px;
  text-align: center;
  font-size: 12px;
  color: var(--text-faint);
  line-height: 2;
}

.wl-foot-links {
  display: flex;
  justify-content: center;
  gap: 18px;
  flex-wrap: wrap;
}

.wl-foot a {
  color: var(--text-muted);
}

.wl-privacy-btn {
  border: none;
  background: none;
  padding: 0;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  text-decoration: underline;
}

.wl-privacy-btn:hover {
  color: var(--primary);
}

/* ---------- 隐私弹层 ---------- */
.wl-modal {
  position: fixed;
  inset: 0;
  z-index: 96;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.45);
}

.wl-modal-card {
  width: 480px;
  max-width: 100%;
  box-shadow: var(--shadow-lg);
}

.wl-modal-card h3 {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.wl-modal-card p {
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.wl-modal-foot {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

/* ---------- 响应式（与主应用同断点 860px） ---------- */
@media (max-width: 860px) {
  .wl-hero {
    padding: 56px 18px 48px;
  }

  .wl-title {
    font-size: 30px;
  }

  .wl-sec {
    padding: 34px 16px 6px;
  }

  .wl-grid {
    grid-template-columns: 1fr;
    gap: var(--gap);
  }

  .wl-btn-solid,
  .wl-btn-ghost {
    width: 100%;
  }

  .wl-hero-actions {
    flex-direction: column;
    max-width: 320px;
    margin-left: auto;
    margin-right: auto;
  }
}
</style>
