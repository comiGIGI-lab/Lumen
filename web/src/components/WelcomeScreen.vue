<script setup>
/**
 * WelcomeScreen —— 首访欢迎层（全屏覆盖，关闭后进入工具界面）
 *
 * 结构：HERO → 三项功能卡 → CTA → 页脚（联系方式 + 隐私说明）
 * HERO：全幅书桌摄影（/hero-desk.jpg 本地文件）+ 遮罩 + LUMEN 刊名
 * 功能卡：CSS 3D 纵深叠卡（perspective / translateZ / rotateY），不引入 React
 * 视觉令牌：米底 #FBF9F6 / 衬线 / 强调色 #E51520 / 胶囊按钮
 *
 * 显示时机由 App.vue 控制：本组件不读写 zjxt.welcomed。
 */
import { ref } from 'vue'
import TopNav from './TopNav.vue'

defineProps({
  needsKey: { type: Boolean, default: false },
})

const emit = defineEmits([
  'start',
  'open-knowledge',
  'open-import',
  'open-record',
  'open-chat',
  'open-wrongbook',
  'open-mindmap',
  'open-study',
  'open-progress',
  'open-settings',
  'open-history',
  'open-trace',
])
const showPrivacy = ref(false)
const activeCard = ref(0)

const cards = [
  {
    num: '01',
    title: '图文素材智能解析',
    body: '课件 PDF、Markdown 讲义与板书照片统一导入，PDF 抽文本层、图片走多模态模型识图，切成可检索的内容块',
  },
  {
    num: '02',
    title: '知识点结构化抽取',
    body: '从解析结果中抽取知识点，整理为课程大纲与知识结构，并标注薄弱环节',
  },
  {
    num: '03',
    title: '交互式答疑辅导',
    body: '先在你的材料里做相关性检索，再把命中的片段交给模型作答，答案标注出处，可以继续追问与逐条核对',
  },
]

function onStart() {
  emit('start')
}

function cardStyle(i) {
  const offset = i - activeCard.value
  const abs = Math.abs(offset)
  return {
    transform: [
      'translate(-50%, -50%)',
      `translateX(${offset * 92}px)`,
      `translateZ(${-abs * 220}px)`,
      `rotateY(${offset * -22}deg)`,
    ].join(' '),
    opacity: abs > 1 ? 0.28 : 1 - abs * 0.18,
    filter: abs === 0 ? 'none' : `blur(${abs * 1.2}px) saturate(${1 - abs * 0.18})`,
    zIndex: String(10 - abs),
  }
}
</script>

<template>
  <div class="welcome" role="dialog" aria-label="欢迎页">
    <Teleport to="body">
      <div class="wl-nav">
        <TopNav
          current=""
          :needs-key="needsKey"
          @go-course="onStart"
          @open-knowledge="emit('open-knowledge')"
          @open-import="emit('open-import')"
          @open-record="emit('open-record')"
          @open-chat="emit('open-chat')"
          @open-wrongbook="emit('open-wrongbook')"
          @open-mindmap="emit('open-mindmap')"
          @open-study="emit('open-study')"
          @open-progress="emit('open-progress')"
          @open-settings="emit('open-settings')"
          @open-history="emit('open-history')"
          @open-trace="emit('open-trace')"
        />
      </div>
    </Teleport>
    <!-- ① HERO：全幅书桌摄影 + 遮罩 + LUMEN 刊名 -->
    <section class="wl-hero">
      <div class="wl-hero-photo" aria-hidden="true">
        <img src="/hero-desk.jpg" alt="" />
      </div>
      <div class="wl-hero-scrim" aria-hidden="true"></div>
      <div class="wl-hero-inner">
        <p class="wl-wordmark">LUMEN</p>
        <h1 class="wl-title">智识有方</h1>
        <p class="wl-sub">多模态教学智能体</p>
        <p class="wl-desc">
          把课件 PDF、Markdown 讲义和板书照片丢进来，随后输入课程名与学习画像，
          生成课程大纲、推荐资源与个性化学习计划。提问时先从你的材料里检索，答案可溯源回原文位置。
        </p>
        <div class="wl-actions">
          <button class="wl-btn wl-btn-light" type="button" @click="onStart">学习方案生成</button>
          <button class="wl-btn wl-btn-light" type="button" @click="emit('open-knowledge')">知识库</button>
          <button class="wl-btn wl-btn-light" type="button" @click="emit('open-import')">文档导入</button>
        </div>
      </div>
    </section>

    <!-- ② 三项功能：CSS 3D 纵深叠卡 -->
    <section class="wl-band">
      <div class="wl-inner">
        <p class="wl-eyebrow">Core capabilities</p>
        <h2 class="wl-h2">三项能力，覆盖一次完整的学习准备</h2>
        <p class="wl-lead">从素材解析到知识抽取，再到答疑核对，都建立在课程内容之上</p>
        <div
          class="wl-stage"
          @mouseleave="activeCard = 0"
        >
          <div class="wl-stack">
            <article
              v-for="(card, i) in cards"
              :key="card.num"
              class="wl-card"
              :class="{ 'is-front': activeCard === i }"
              :style="cardStyle(i)"
              @mouseenter="activeCard = i"
              @focus="activeCard = i"
              tabindex="0"
            >
              <div class="wl-num">{{ card.num }}</div>
              <h3>{{ card.title }}</h3>
              <p>{{ card.body }}</p>
            </article>
          </div>
        </div>
        <div class="wl-dots" role="tablist" aria-label="三项能力">
          <button
            v-for="(card, i) in cards"
            :key="'dot-' + card.num"
            type="button"
            class="wl-dot"
            :class="{ on: activeCard === i }"
            :aria-label="card.title"
            @click="activeCard = i"
          />
        </div>
      </div>
    </section>

    <!-- ③ CTA -->
    <section class="wl-cta">
      <div class="wl-inner">
        <h2 class="wl-h2">从一门课程开始</h2>
        <p class="wl-lead">不需要预先整理资料，进入后输入课程名即可生成</p>
        <div class="wl-actions">
          <button class="wl-btn" type="button" @click="onStart">学习方案生成</button>
          <button class="wl-btn" type="button" @click="emit('open-knowledge')">知识库</button>
          <button class="wl-btn" type="button" @click="emit('open-import')">文档导入</button>
        </div>
      </div>
    </section>

    <!-- ④ 页脚 -->
    <footer class="wl-foot">
      <div class="wl-inner">
        <div class="wl-foot-name">智识有方</div>
        <p class="wl-foot-lumen">LUMEN，拉丁语意为光。智识有方：光之所至，学有其方。</p>
        <p class="wl-foot-lumen en">LUMEN, Latin for light. ZhiShiYouFang: where the light reaches, learning finds its way.</p>
        <p class="wl-foot-links">
          <a href="https://gitee.com/zhang-binxiang666/ai-coding" target="_blank" rel="noopener">Gitee</a>
          <button class="wl-privacy-btn" type="button" @click="showPrivacy = true">隐私说明</button>
        </p>
      </div>
    </footer>

    <Teleport to="body">
    <div v-if="showPrivacy" class="wl-modal" @click.self="showPrivacy = false">
      <div class="wl-modal-card">
        <h3>隐私说明</h3>
        <p>本页面为参赛原型演示，不收集任何个人信息。</p>
        <p>演示所用的笔记、文档与学习记录均保存在你本机浏览器中，不会上传到服务器。</p>
        <p>页面上的解析状态、分块数量与统计数字均为演示用示例数据。</p>
        <div class="wl-modal-foot">
          <button class="wl-btn-ghost" type="button" @click="showPrivacy = false">知道了</button>
        </div>
      </div>
    </div>
    </Teleport>
  </div>
</template>

<style scoped>
.welcome {
  --bg: #fbf9f6;
  --surface: #ffffff;
  --band: #f8f3ec;
  --text: #191919;
  --border: #e4ded5;
  --primary: #191919;
  --primary-ink: #ffffff;
  --accent: #e51520;
  --muted: #808080;
  --chip: #f1ece4;
  --font-serif: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC",
    "Source Han Serif SC", serif;
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --shadow-btn: 0 5px 10px rgba(0, 0, 0, 0.15);

  position: fixed;
  inset: 0;
  z-index: 90;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  animation: fade-up 0.24s ease both;
}


.wl-inner {
  max-width: 720px;
  margin: 0 auto;
}

.wl-hero {
  position: relative;
  min-height: 92vh;
  min-height: 100svh;
  display: flex;
  align-items: flex-end;
  padding: 0 0 64px;
  color: #f7f2ea;
  overflow: hidden;
}

.wl-hero-photo {
  position: absolute;
  inset: 0;
}

.wl-hero-photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 58% 42%;
  display: block;
}

.wl-hero-scrim {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(18, 12, 8, 0.18) 0%, rgba(18, 12, 8, 0.28) 38%, rgba(18, 12, 8, 0.78) 100%),
    linear-gradient(90deg, rgba(18, 12, 8, 0.55) 0%, rgba(18, 12, 8, 0.12) 52%, rgba(18, 12, 8, 0.08) 100%);
}

.wl-hero-inner {
  position: relative;
  z-index: 1;
  max-width: 760px;
  padding: 72px 32px 64px;
}

.wl-wordmark {
  margin: 0;
  font-family: var(--font-serif);
  font-size: clamp(64px, 14vw, 132px);
  font-weight: 400;
  letter-spacing: 0.08em;
  line-height: 0.86;
  color: #fff;
  text-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
}

.wl-title {
  font-family: var(--font-serif);
  font-size: clamp(28px, 5vw, 40px);
  font-weight: 400;
  letter-spacing: 0.18em;
  line-height: 1.2;
  margin: 18px 0 0;
}

.wl-sub {
  margin: 10px 0 0;
  font-size: 14px;
  letter-spacing: 0.22em;
  color: rgba(247, 242, 234, 0.78);
}

.wl-desc {
  margin: 24px 0 0;
  font-size: 17px;
  line-height: 1.75;
  color: rgba(247, 242, 234, 0.82);
  max-width: 34em;
}

.wl-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 36px;
  max-width: 34em;
}

.wl-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 1 1 auto;
  min-width: 9.5em;
  height: 48px;
  padding: 0 22px;
  border: none;
  border-radius: 1000px;
  background: var(--primary);
  color: var(--primary-ink);
  font-size: 14px;
  letter-spacing: 0.06em;
  box-shadow: var(--shadow-btn);
  cursor: pointer;
  transition: transform 0.18s ease, opacity 0.18s ease;
}

.wl-btn-light {
  background: var(--bg-card);
  color: var(--text-primary);
}

.wl-btn:hover {
  transform: translateY(-1px);
  opacity: 0.92;
}

.wl-band {
  background: var(--band);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  padding: 72px 32px 48px;
  overflow: hidden;
}

.wl-h2 {
  font-family: var(--font-serif);
  font-size: 32px;
  font-weight: 400;
  line-height: 1.3;
  margin: 0 0 12px;
}

.wl-lead {
  font-size: 16px;
  line-height: 1.75;
  color: var(--muted);
  margin: 0;
  max-width: 34em;
}

.wl-eyebrow {
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 13px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 20px;
}

.wl-stage {
  margin: 36px auto 0;
  height: 300px;
  perspective: 1400px;
  perspective-origin: 50% 48%;
}

.wl-stack {
  position: relative;
  height: 100%;
  transform-style: preserve-3d;
}

.wl-card {
  position: absolute;
  left: 50%;
  top: 50%;
  width: min(280px, 78vw);
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 28px 24px;
  transform-style: preserve-3d;
  transform-origin: center center;
  transition: transform 0.55s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.45s ease, filter 0.45s ease;
  box-shadow: 0 18px 40px rgba(25, 25, 25, 0.12);
  cursor: pointer;
  outline: none;
}

.wl-card.is-front {
  box-shadow: 0 22px 48px rgba(25, 25, 25, 0.16);
}

.wl-card h3 {
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 400;
  margin: 0 0 10px;
}

.wl-card p {
  font-size: 15px;
  line-height: 1.7;
  color: var(--muted);
  margin: 0;
}

.wl-num {
  font-family: var(--font-serif);
  font-size: 13px;
  letter-spacing: 0.1em;
  color: var(--accent);
  margin-bottom: 14px;
}

.wl-dots {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-top: 8px;
}

.wl-dot {
  width: 8px;
  height: 8px;
  border: none;
  border-radius: 999px;
  background: var(--border);
  padding: 0;
  cursor: pointer;
}

.wl-dot.on {
  background: var(--accent);
  width: 22px;
}

.wl-cta {
  padding: 80px 32px;
  text-align: left;
}

.wl-cta .wl-actions {
  margin-top: 28px;
}

.wl-foot {
  background: #191919;
  color: #ffffff;
  padding: 48px 32px 40px;
}

.wl-foot-name {
  font-family: var(--font-serif);
  font-size: 20px;
  margin-bottom: 10px;
}

.wl-foot-lumen {
  font-family: var(--font-serif);
  font-size: 14px !important;
  line-height: 1.75 !important;
  opacity: 0.88 !important;
  margin: 0 0 4px !important;
  max-width: 34em;
}

.wl-foot-lumen.en {
  font-style: italic;
  opacity: 0.68 !important;
  margin-bottom: 14px !important;
}

.wl-foot p {
  font-size: 13px;
  line-height: 1.8;
  opacity: 0.7;
  margin: 0;
}

.wl-foot-links {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-top: 16px !important;
}

.wl-foot a,
.wl-privacy-btn {
  color: inherit;
  opacity: 0.85;
  font-size: 13px;
}

.wl-privacy-btn {
  border: none;
  background: none;
  padding: 0;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.wl-privacy-btn:hover,
.wl-foot a:hover {
  opacity: 1;
}

.wl-modal {
  --surface: #ffffff;
  --text: #191919;
  --border: #e4ded5;
  --muted: #808080;
  --font-serif: Georgia, "Times New Roman", "Songti SC", "Noto Serif CJK SC", serif;
  position: fixed;
  inset: 0;
  z-index: 170;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(0, 0, 0, 0.45);
}

.wl-modal-card {
  width: 520px;
  max-width: 100%;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 28px;
}

.wl-modal-card h3 {
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 400;
  margin: 0 0 14px;
}

.wl-modal-card p {
  font-size: 15px;
  line-height: 1.7;
  color: var(--muted);
  margin: 0 0 10px;
}

.wl-modal-foot {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
}

.wl-btn-ghost {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  padding: 0 16px;
  border-radius: 1000px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
  font-size: 12px;
  letter-spacing: 0.08em;
  cursor: pointer;
}

@keyframes fade-up {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@media (max-width: 860px) {
  .wl-hero-inner {
    padding: 56px 20px 48px;
  }

  .wl-wordmark {
    letter-spacing: 0.04em;
  }

  .wl-title {
    letter-spacing: 0.12em;
    font-size: 28px;
  }

  .wl-desc {
    font-size: 15px;
  }

  .wl-band,
  .wl-cta,
  .wl-foot {
    padding-left: 20px;
    padding-right: 20px;
  }

  .wl-h2 {
    font-size: 26px;
  }

  .wl-stage {
    height: 280px;
  }
}

@media (max-width: 430px) {
  .wl-hero {
    padding-bottom: 80px;
  }
  .wl-hero-inner {
    padding: 88px 16px 40px;
  }
  .wl-wordmark {
    font-size: 48px;
  }
  .wl-title {
    font-size: 22px;
    letter-spacing: 0.1em;
  }
  .wl-stage {
    height: 300px;
  }
  .wl-actions {
    gap: 8px;
    margin-top: 24px;
  }
  .wl-btn {
    min-width: calc(50% - 4px);
    padding: 0 14px;
    font-size: 13px;
  }
}
</style>

<style>
.wl-nav {
  position: fixed;
  top: 12px;
  right: 12px;
  left: auto;
  z-index: 132;
  display: flex;
  justify-content: flex-end;
  pointer-events: none;
  max-width: min(520px, calc(100vw - 24px));
}

.wl-nav .top-nav {
  pointer-events: auto;
}

.wl-nav .nav-link {
  background: rgba(var(--bg-card-rgb), 0.92);
}

@media (max-width: 430px) {
  .wl-nav {
    top: 8px;
    right: 8px;
    left: 8px;
    max-width: none;
  }
}
</style>
