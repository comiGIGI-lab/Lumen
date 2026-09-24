/**
 * 知识库前端演示状态：笔记 / 文档 / 分块挂在同一份单例上。
 * 不接写入接口。分块只来自当前笔记自己的关联文档。
 */
import { computed, ref } from 'vue'

export const TAG_LABEL = {
  'high-math': '高数',
  english: '英语',
  mistakes: '错题',
  others: '其他',
}

const SEED_NOTES = [
  { id: 'n1', title: '高等数学 · 极限与连续', tag: 'high-math', updated: '09-19 14:32', created: '09-12 09:10', remark: '本周重点：ε-N 定义 + 两个重要极限，配套 3 道错题重做。' },
  { id: 'n2', title: '考研英语 · 长难句拆解 01', tag: 'english', updated: '09-19 10:05', created: '09-10 20:41', remark: '每天 5 句长难句，先自己拆再对照解析。' },
  { id: 'n3', title: '线性代数 · 矩阵秩的判定', tag: 'high-math', updated: '09-18 21:47', created: '09-09 15:22', remark: '重点记：初等变换不改变秩。' },
  { id: 'n4', title: '错题本 · 不定积分常错点', tag: 'mistakes', updated: '09-18 19:03', created: '09-08 22:15', remark: '错因分类：符号错误 6 次、公式记混 4 次。' },
  { id: 'n5', title: '数据结构 · 红黑树笔记', tag: 'others', updated: '09-17 16:20', created: '09-07 11:30', remark: '旋转变色部分要能手绘，面试高频。' },
  { id: 'n6', title: '机器学习 · 损失函数汇总', tag: 'others', updated: '09-17 08:55', created: '09-06 13:08', remark: '交叉熵 vs MSE 的适用边界要讲清楚。' },
  { id: 'n7', title: '英语听力真题精听 Week3', tag: 'english', updated: '09-16 23:12', created: '09-05 19:44', remark: '精听流程：盲听 → 看稿 → 复述。' },
  { id: 'n8', title: '概率论 · 大数定律与中心极限定理', tag: 'others', updated: '09-15 20:30', created: '09-04 10:02', remark: '中心极限定理三个条件别记漏。' },
]

const SEED_DOCS = {
  n1: [
    { id: 'd101', name: '第2章 极限与连续.pdf', type: 'pdf', status: 'ready', chunks: 2 },
    { id: 'd102', name: '课堂板书_0912.jpg', type: 'image', status: 'parsing', chunks: 0, progress: 62 },
    { id: 'd103', name: '习题课录音.mp3', type: 'audio', status: 'queue', chunks: 0 },
  ],
  n2: [
    { id: 'd201', name: '长难句精讲.pdf', type: 'pdf', status: 'ready', chunks: 2 },
    { id: 'd202', name: '真题阅读扫描件.jpg', type: 'image', status: 'failed', chunks: 0, error: 'OCR_FAILED' },
  ],
  n3: [{ id: 'd301', name: '矩阵秩判定方法.pdf', type: 'pdf', status: 'ready', chunks: 2 }],
  n4: [
    { id: 'd401', name: '不定积分错题集.pdf', type: 'pdf', status: 'ready', chunks: 2 },
    { id: 'd402', name: '错题照片_01.jpg', type: 'image', status: 'ready', chunks: 1 },
    { id: 'd403', name: '错题照片_02.jpg', type: 'image', status: 'parsing', chunks: 0, progress: 28 },
    { id: 'd404', name: '老师讲解录音.mp3', type: 'audio', status: 'queue', chunks: 0 },
  ],
  n5: [
    { id: 'd501', name: '红黑树讲义.pdf', type: 'pdf', status: 'ready', chunks: 2 },
    { id: 'd502', name: '插入删除演示.jpg', type: 'image', status: 'ready', chunks: 1 },
  ],
  n6: [
    { id: 'd601', name: '损失函数综述.pdf', type: 'pdf', status: 'ready', chunks: 2 },
    { id: 'd602', name: '课件截图.png', type: 'image', status: 'parsing', chunks: 0, progress: 45 },
    { id: 'd603', name: '课程录音_第4讲.mp3', type: 'audio', status: 'ready', chunks: 1 },
  ],
  n7: [{ id: 'd701', name: '听力真题_Week3.mp3', type: 'audio', status: 'ready', chunks: 1 }],
  n8: [
    { id: 'd801', name: '大数定律.pdf', type: 'pdf', status: 'ready', chunks: 2 },
    { id: 'd802', name: '公式推导手写稿.jpg', type: 'image', status: 'failed', chunks: 0, error: 'IMAGE_TOO_BLURRY' },
  ],
}

const SEED_CHUNKS = {
  d101: [
    { id: '#01', src: '第2章 极限与连续.pdf · P12', text: '数列极限的 ε-N 定义：对任意 ε>0，存在 N，当 n>N 时 |a_n - A| < ε…' },
    { id: '#02', src: '第2章 极限与连续.pdf · P14', text: '夹逼准则：若 b_n ≤ a_n ≤ c_n 且 lim b_n = lim c_n = A，则 lim a_n = A…' },
  ],
  d201: [
    { id: '#01', src: '长难句精讲.pdf · P3', text: '先标出主谓，再把从句、插入语剥开，剩下的才是主干。' },
    { id: '#02', src: '长难句精讲.pdf · P7', text: '定语从句过长时，先用括号把修饰成分括起来再翻译。' },
  ],
  d301: [
    { id: '#01', src: '矩阵秩判定方法.pdf · P2', text: '初等行变换不改变矩阵的秩。' },
    { id: '#02', src: '矩阵秩判定方法.pdf · P5', text: '化成行阶梯形后，非零行的行数就是秩。' },
  ],
  d401: [
    { id: '#01', src: '不定积分错题集.pdf · P1', text: '常见错因：漏掉常数 C、复合函数忘了除以内层导数。' },
    { id: '#02', src: '不定积分错题集.pdf · P4', text: '有理函数优先拆成部分分式，再逐项积分。' },
  ],
  d402: [
    { id: '#01', src: '错题照片_01.jpg · OCR', text: '这道题把积分上下限代反了，符号整页跟着错。' },
  ],
  d501: [
    { id: '#01', src: '红黑树讲义.pdf · P6', text: '红黑树五条性质：根黑、叶黑、红节点子必黑、任意路径黑高相同。' },
    { id: '#02', src: '红黑树讲义.pdf · P11', text: '插入后按叔节点颜色决定变色或旋转。' },
  ],
  d502: [
    { id: '#01', src: '插入删除演示.jpg · OCR', text: '左旋右旋只改三组指针，黑高保持不变。' },
  ],
  d601: [
    { id: '#01', src: '损失函数综述.pdf · P3', text: '回归任务常用 MSE；分类更常用交叉熵。' },
    { id: '#02', src: '损失函数综述.pdf · P8', text: '交叉熵对概率校准更敏感，梯度不易过早消失。' },
  ],
  d603: [
    { id: '#01', src: '课程录音_第4讲.mp3 · 转写', text: '老师强调：别把 MSE 直接用在 Sigmoid 输出上。' },
  ],
  d701: [
    { id: '#01', src: '听力真题_Week3.mp3 · 转写', text: '精听三遍：盲听抓大意，看稿补细节，合上稿复述。' },
  ],
  d801: [
    { id: '#01', src: '大数定律.pdf · P4', text: '样本均值依概率收敛到期望，要求独立同分布且期望存在。' },
    { id: '#02', src: '大数定律.pdf · P9', text: '中心极限定理给出的是标准化后的分布逼近，不是大数定律本身。' },
  ],
}

export const DEMO_FILES = [
  {
    name: '第3章 导数与微分.pdf',
    size: '2.4 MB',
    type: 'pdf',
    chunks: [
      { src: '第3章 导数与微分.pdf · P2', text: '导数是增量比的极限。这是演示分块，写入接口还没接。' },
      { src: '第3章 导数与微分.pdf · P6', text: '可导一定连续，连续不一定可导。' },
    ],
  },
  {
    name: '课堂板书_0920.jpg',
    size: '1.1 MB',
    type: 'image',
    chunks: [
      { src: '课堂板书_0920.jpg · OCR', text: '板书演示分块：链式法则先内后外。' },
    ],
  },
  {
    name: '习题课录音_0920.mp3',
    size: '8.7 MB',
    type: 'audio',
    chunks: [
      { src: '习题课录音_0920.mp3 · 转写', text: '录音演示分块：易错点是忘记定义域。' },
    ],
  },
]

function clone(data) {
  return JSON.parse(JSON.stringify(data))
}

const notes = ref(SEED_NOTES.map((n) => ({ ...n })))
const docsByNote = ref(clone(SEED_DOCS))
const chunksByDoc = ref(clone(SEED_CHUNKS))
const currentId = ref('n1')
let seq = 1

function stamp() {
  return '刚刚'
}

function ensureNoteDocs(noteId) {
  if (!docsByNote.value[noteId]) {
    docsByNote.value = { ...docsByNote.value, [noteId]: [] }
  }
  return docsByNote.value[noteId]
}

export function useKnowledge() {
  const current = computed(() => notes.value.find((n) => n.id === currentId.value) || notes.value[0] || null)
  const currentDocs = computed(() => (current.value ? docsByNote.value[current.value.id] || [] : []))
  const currentChunks = computed(() => {
    const list = []
    currentDocs.value.forEach((doc) => {
      if (doc.status !== 'ready') return
      const pieces = chunksByDoc.value[doc.id] || []
      pieces.forEach((c, i) => {
        list.push({
          id: `${doc.id}-${c.id || i}`,
          src: c.src,
          text: c.text,
          docId: doc.id,
        })
      })
    })
    return list
  })

  function pickNote(id) {
    if (notes.value.some((n) => n.id === id)) currentId.value = id
  }

  function createNote(title = '未命名笔记') {
    const id = 'n' + Date.now() + String(seq++)
    notes.value = [
      {
        id,
        title,
        tag: 'others',
        updated: stamp(),
        created: stamp(),
        remark: '',
      },
      ...notes.value,
    ]
    docsByNote.value = { ...docsByNote.value, [id]: [] }
    currentId.value = id
    return id
  }

  function removeDoc(noteId, docId) {
    const list = docsByNote.value[noteId]
    if (!list) return
    docsByNote.value = {
      ...docsByNote.value,
      [noteId]: list.filter((d) => d.id !== docId),
    }
    const next = { ...chunksByDoc.value }
    delete next[docId]
    chunksByDoc.value = next
  }

  function retryDoc(doc) {
    if (!doc || doc.status !== 'failed') return
    doc.status = 'ready'
    doc.progress = 100
    delete doc.error
    if (!chunksByDoc.value[doc.id]) {
      chunksByDoc.value = {
        ...chunksByDoc.value,
        [doc.id]: [
          { id: '#01', src: `${doc.name} · 演示`, text: '重试后的演示分块。写入接口还没接。' },
        ],
      }
    }
    doc.chunks = chunksByDoc.value[doc.id].length
  }

  function attachDemoDocs(noteId) {
    const id = noteId || currentId.value
    if (!id) return []
    const list = ensureNoteDocs(id)
    const added = []
    const nextChunks = { ...chunksByDoc.value }
    DEMO_FILES.forEach((file, i) => {
      const docId = 'demo' + Date.now() + i + seq++
      const pieces = (file.chunks || []).map((c, ci) => ({
        id: '#' + String(ci + 1).padStart(2, '0'),
        src: c.src,
        text: c.text,
      }))
      list.push({
        id: docId,
        name: file.name,
        type: file.type,
        status: 'ready',
        chunks: pieces.length,
        demo: true,
      })
      nextChunks[docId] = pieces
      added.push(docId)
    })
    chunksByDoc.value = nextChunks
    docsByNote.value = { ...docsByNote.value, [id]: list.slice() }
    const note = notes.value.find((n) => n.id === id)
    if (note) note.updated = stamp()
    pickNote(id)
    return added
  }

  function loadDemo() {
    notes.value = SEED_NOTES.map((n) => ({ ...n }))
    docsByNote.value = clone(SEED_DOCS)
    chunksByDoc.value = clone(SEED_CHUNKS)
    currentId.value = 'n1'
  }

  return {
    notes,
    docsByNote,
    chunksByDoc,
    currentId,
    current,
    currentDocs,
    currentChunks,
    pickNote,
    createNote,
    removeDoc,
    retryDoc,
    attachDemoDocs,
    loadDemo,
  }
}
