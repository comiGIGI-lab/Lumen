<script setup>
/**
 * HandbookPage —— 使用手册
 * 从「更多」进入。功能说明以本手册为准，学伴不再另弹模块提醒。
 */
import { useI18n } from '@/i18n'

const emit = defineEmits(['back'])
const { t, isEn } = useI18n()

const zh = [
  {
    title: '从这里开始',
    body: '第一次打开会先选一位学伴，再进入欢迎层。欢迎层关掉之后，顶部是首页、学习方案、知识库、课程问答、自习空间和更多。文档导入、语音转写、思维导图和错题本不在顶部，都在知识库里切换。右上角可在中文和 English 之间切换。各功能怎么用以本手册为准。第一次进入学习方案、知识库、课程问答、自习空间、个人空间或模型设置时，学伴会在自己身上用一句话带过，不再另外弹出提示卡片，也不会在空闲时轮流提醒去自习、闯关或导入资料。',
  },
  {
    title: '学习方案生成',
    body: '在首页输入课程名，并选择水平、每日时长和学习目标。点「生成方案」后，系统按 Planner、Searcher、Writer、Reviewer 四段推进，产出课程大纲、推荐资源和每日计划。入门、进阶、熟练三档画像会一起影响章节深度、推荐资源和计划天数。同一课程和同一画像在 24 小时内可命中缓存，避免重复调用模型。大纲每一章、计划每一天都可以勾选，勾选结果记入学习进度。',
  },
  {
    title: '知识库',
    body: '打开知识库后，标题下有四个分区：笔记、语音转写、思维导图、错题本。再点顶部的「知识库」会回到笔记。错题本不再单独占顶部导航。笔记可按全部、我的私有、公共资料筛选，也可按分类筛选；筛过之后始终有「返回全部笔记」。团队共享已去掉。自己的笔记可以生成 8 位口令，对方兑换后复制进自己的私有笔记；也可以下载文本。口令分享和兑换需要先登录。',
  },
  {
    title: '笔记与文档导入',
    body: '导入只在「笔记」分区里。把课件、板书、笔记或录音转写拖进来之后，课程问答才能检索到对应段落，不会脱离这些材料另编出处。支持 PDF、Word、PPT、Markdown、txt 和图片，单个不超过 16 MB，一次最多 10 个。解析完成后材料按来源聚合成笔记，并可查看分块。数字 PDF 抽取文本层；扫描件在服务器具备对应侧车时自动升级解析。新建时可指定私有或公共，以及分类。导入成功一次，学伴获得 15 点经验。删除知识库内容需要管理员账号。',
  },
  {
    title: '语音转写',
    body: '这是知识库的第二个分区，不是顶部的独立页面。讲课录音或手机录制的音频可转成文字。支持 mp3、m4a、wav、ogg、webm，单次最长 8 分钟。识别在服务器上离线完成，音频不发给外部模型接口。转写结果可直接修改，再存入笔记，之后即可在课程问答中引用。欢迎页上的转写入口也会打开这个分区。',
  },
  {
    title: '思维导图',
    body: '这是知识库的第三个分区，不再放在「更多」里。可以把已有学习方案的大纲转成导图，也可以从空白开始。单击选中，双击改字。导图按课程保存；还没有方案时，先在学习方案里生成，再回到这个分区载入。',
  },
  {
    title: '课程问答与闯关',
    body: '课程问答先从当前课程的知识库检索片段，再据此作答，并标出参考资料。可以对刚生成的方案追问，也可以新开一轮，点参考资料能回到对应片段。还没有生成方案、也没有选定课程时，无法围绕课程出题。闯关仍按当前课程的知识库出题，可选择难度、题数和题型（单选、多选、判断或混合）。如果题干对上这门课尚未掌握的旧错题，题目前会标「曾经的错题」。逐题判分，新的错答进入知识库里的错题本。通关后按题数结算经验，每题 2 点。',
  },
  {
    title: '错题本与学习进度',
    body: '错题本是知识库的第四个分区，不在顶部导航。它按课程记录题干、错答、正解和错因，复习一次记一笔，也可以手动补一条。标记掌握之后，闯关再遇到同一题干就不再标「曾经的错题」。学习进度在「更多」里，汇总本机各课程的勾选完成度，并可从这里打开对应课程的历史方案。',
  },
  {
    title: '自习空间与个人空间',
    body: '自习空间以计时为主体，可选场景和声音。先选定 5、10、15、25、50 分钟或自定义时长，再开始；计时完整跑完才计入经验，每分钟 1 点，每天第一次完成另加 10 点。时长始终排在倒计时下面。在这一页的电脑宽屏上，场景和声音左右并列且可同时展开，名称各自放在对应面板上方。其它页面的自习坞仍是上下排列，场景和声音一次只打开一块。窄屏同样保持上下排列。自习坞、待办和日期是三块悬浮窗，按住标题栏空白处可拖动。标题栏右侧有减号和加号：加号把窗口放大一档，最多三档；减号缩小一档。已经是最小档时再按减号，窗口收到屏幕侧边，变成竖着的边签。窗口中心在屏幕左半边，签贴左缘；在右半边，签贴右缘。点边签展开，回到收起前的大小。拖到屏幕边缘不会自动收起。左下「空间」可以分别开关这三块，也能恢复默认位置，并查看当前化身、性格、学习类型和升级进度。更换学伴走下方入口。',
  },
  {
    title: '学伴怎么互动',
    body: '学伴停在右下角。单击打开档案。双击弹出互动：摸摸加 2 点、喂食加 5 点、玩耍加 8 点，同一动作冷却 30 秒。长按约 1 秒会撒娇。这些互动、经验、冷却，以及第一次进入某功能时的那一句说明，都显示成贴在立绘上的气泡：字号保持 14px，气泡边缘尽量贴字。宠物收到左右侧边栏或停在屏幕其它位置时，气泡翻到画面内侧。不再因为空闲而轮流提醒去自习、闯关、导入或玩耍。按住立绘可拖动；松手时靠近左右边缘即收成探头，点探头滑回。拖到边缘后的提示只出现一次。',
  },
  {
    title: '学伴怎么升级',
    body: '经验来自四类行为：生成一份学习方案加 40 点，同一天最多计入两次；自习按分钟累加，另有每日首练加成；导入资料加 15 点；闯关每题加 2 点，再加上互动经验。经验攒满后等级提高。升到可进化的等级时，可以选择保持当前外形或换成进阶外形。进阶只改变外观，等级和经验都保留。',
  },
  {
    title: '模型、历史与账号',
    body: 'AI 模型设置在「更多」里。离线 Mock 使用内置模板，适合先体验，不消耗额度，保存后才切换。在线模式需要填写平台、接口地址、模型名和 API Key；Key 只保存在本机。没填 Key 时，系统会回退到模板并标明这次不是模型生成的结果。手机上不会一进门就弹出设置，可稍后从导航打开。历史保存已生成的方案，可再次打开。日志记录最近一次链路。账号用于登录后管理知识库；普通账号可以查看、导入和提问。',
  },
]

const en = [
  {
    title: 'Start here',
    body: 'The first visit asks you to pick a study buddy, then shows the welcome layer. After you close it, the top bar is Home, Study plan, Knowledge base, Course Q&A, Study space, and More. Import, transcription, the mind map, and the wrong-answer book are not on the top bar; they are sections inside the knowledge base. Use the language control at the upper right to switch between 中文 and English. How each part works is written here. The first time you open Study plan, Knowledge base, Course Q&A, Study space, Personal space, or Model settings, the buddy says one short line in the bubble on its body. There is no separate tip card, and it no longer rotates idle reminders to study, quiz, or import.',
  },
  {
    title: 'Study plan',
    body: 'On the home view, enter a course name and choose level, daily time, and goal. Generate runs four stages — Planner, Searcher, Writer, Reviewer — and returns an outline, recommended resources, and a day-by-day plan. Beginner, intermediate, and advanced change the chapter depth, the resources, and the number of days together. The same course and profile can reuse a cached result for 24 hours. Check off each chapter and each day; those checks feed Learning Progress.',
  },
  {
    title: 'Knowledge base',
    body: 'The knowledge base has four sections under the title: Notes, Transcription, Mind map, and Wrong answers. Choosing Knowledge base in the top bar returns to Notes. The wrong-answer book is no longer its own top-bar item. Notes can be filtered as All, Private, or Public, and by category. After any filter, Back to all notes stays available. Team sharing is gone. A note you own can issue an 8-character code; redeeming it copies the note into the other person’s private notes. A text download is also available. Issuing or redeeming a code requires a signed-in account.',
  },
  {
    title: 'Notes and import',
    body: 'Import stays in the Notes section. Once slides, notes, or a transcript are in, Course Q&A can retrieve the matching passages instead of inventing a source. It accepts PDF, Word, PPT, Markdown, txt, and images. Each file is at most 16 MB, and one batch holds at most 10 files. Parsed material becomes notes grouped by source, with chunks you can preview. A text-layer PDF is extracted directly; scans use a heavier parser when that sidecar is installed. A new note can be private or public, and can take a category. One successful import grants the buddy 15 exp. Deleting knowledge-base content requires an admin account.',
  },
  {
    title: 'Transcription',
    body: 'This is the second section of the knowledge base, not a separate top-level page. A lecture recording or a clip from your phone can be turned into text. Formats are mp3, m4a, wav, ogg, and webm, up to 8 minutes each. Recognition runs offline on this server; audio is not sent to an external model API. Edit the transcript, save it as a note, and later questions can cite it. The transcription button on the welcome layer opens this section.',
  },
  {
    title: 'Mind map',
    body: 'This is the third section of the knowledge base. It is no longer under More. Build a map from an existing study-plan outline, or start from a blank canvas. Click to select a node, double-click to edit it. Maps are saved by course. If there is no plan yet, generate one first, then come back and load it.',
  },
  {
    title: 'Course Q&A and quiz',
    body: 'Course Q&A retrieves passages from the current course knowledge base before answering, and lists the sources. You can follow up on the plan you just generated or start another turn; a source link jumps back to that passage. A quiz needs a course from a generated plan, and the questions still come from that course’s knowledge base. Choose difficulty, number of questions, and type: single choice, multiple choice, true or false, or mixed. If the stem matches an unmastered old miss for this course, the item is marked as a former wrong answer. Each item is graded immediately. A new miss goes to the wrong-answer section inside the knowledge base. Finishing a round grants 2 exp per question.',
  },
  {
    title: 'Wrong answers and progress',
    body: 'The wrong-answer book is the fourth section of the knowledge base, not a top-bar item. It stores the prompt, your answer, the correct answer, and the reason, grouped by course. One review is one count, and you can add a miss by hand. Once you mark it mastered, a later quiz no longer tags the same stem as a former wrong answer. Learning Progress is under More. It totals the checked items on this browser and can reopen a course from history.',
  },
  {
    title: 'Study space and personal space',
    body: 'Study space is a timer with scenes and sound. Choose 5, 10, 15, 25, or 50 minutes, or a custom length, then start. Exp is granted only when a session finishes: 1 point per minute, plus 10 points the first time you finish on a given day. Duration stays under the countdown. On a wide computer screen this page puts Scene and Sound side by side, both open, each name sitting above its own panel. On every other page the study dock stays stacked, and Scene and Sound open one at a time. A narrow screen stays stacked too. Study dock, to-do, and the date window are three floating panels. Drag one by the empty part of its title bar. The minus and plus on the right change its size: plus grows one step, up to three; minus shrinks one step. Press minus again at the smallest size and the panel tucks into a vertical tab. A panel whose center is on the left half of the screen tabs to the left edge; otherwise it tabs to the right. Click the tab to open it at the size it had before. Dragging a panel to the screen edge does not collapse it. Space at the lower left switches each panel on or off, resets positions, and shows the current form, temperament, learning type, and level. Change the buddy from the button below.',
  },
  {
    title: 'How the buddy responds',
    body: 'The buddy sits at the lower right. A click opens its profile. A double-click opens actions: Pet +2, Feed +5, Play +8. The same action waits 30 seconds before it can run again. A press of about one second makes it nuzzle. Interaction, exp, cooldown, and the one-line note the first time you open a feature all appear in the bubble attached to the sprite. The type stays 14px and the bubble hugs the text. If the buddy is tucked into either edge, or parked anywhere else, the bubble turns inward. It no longer cycles idle reminders to study, quiz, import, or play. Drag the sprite; release it near the left or right edge and it tucks into a peek. Click the peek to bring it back. The drag hint shows once.',
  },
  {
    title: 'How the buddy levels up',
    body: 'Exp comes from four kinds of use. Generating a plan grants 40 points, at most twice on the same day. A finished study session grants 1 point per minute, with a daily first-session bonus. Importing materials grants 15. A quiz grants 2 per question. Interaction exp is added on top. When the bar fills, the level rises. At an evolution level you may keep the current look or switch to the advanced form. The form change is visual only; level and exp stay.',
  },
  {
    title: 'Model, history, account',
    body: 'AI settings live under More. Offline Mock uses built-in templates, is meant for a first look, spends no quota, and switches only after you save. Online mode needs a platform, base URL, model name, and API key. The key stays on this machine. Without a key, the system falls back to a template and marks the result as not model-generated. On a phone, settings do not open automatically on entry; open them later from the menu. History reopens plans you already generated. Logs show the latest pipeline run. An account is for managing the knowledge base after sign-in. A regular account can view, import, and ask.',
  },
]
</script>

<template>
  <section class="hb">
    <header class="hb-head">
      <div>
        <p class="kicker">Handbook</p>
        <h1>{{ isEn ? 'Handbook' : '使用手册' }}</h1>
        <p class="sub">{{ isEn ? 'What each part does, and how the study buddy grows. Feature notes live here, not in a separate tip card.' : '各功能做什么，学伴如何成长。功能说明在本手册，不再另弹提示卡片。' }}</p>
      </div>
      <button type="button" class="btn btn-ghost" @click="emit('back')">{{ t('common.back') }}</button>
    </header>
    <ol class="hb-list">
      <li v-for="(sec, i) in (isEn ? en : zh)" :key="sec.title">
        <span class="num">{{ String(i + 1).padStart(2, '0') }}</span>
        <div>
          <h2>{{ sec.title }}</h2>
          <p>{{ sec.body }}</p>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.hb {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.hb-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin: 0 0 4px;
}
h1 {
  font-size: 28px;
  color: var(--text-primary);
}
.sub {
  margin-top: 6px;
  color: var(--text-secondary);
  max-width: 46em;
}
.hb-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.hb-list li {
  display: flex;
  gap: 14px;
  /* 底栏固定高 32px。滚到某一节时，底边留在栏上方。 */
  scroll-margin-bottom: 48px;
  padding: 16px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.num {
  flex: none;
  font-family: var(--font-serif);
  color: var(--primary);
  font-size: 16px;
  line-height: 1.4;
}
h2 {
  font-size: 16px;
  color: var(--text-primary);
  margin-bottom: 6px;
}
p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13.5px;
  line-height: 1.75;
}
@media (max-width: 430px) {
  .hb-head {
    flex-direction: column;
  }
  h1 {
    font-size: 22px;
  }
  .hb-list li {
    padding: 14px;
  }
}
</style>
