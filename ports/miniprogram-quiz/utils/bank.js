/** 预置演示题库。不是此刻 AI 出题。每组含原题 + 变式。 */
var BANK = {
  math: {
    id: 'math',
    name: '高等数学',
    blurb: '今晚卡在极限、中值定理、洛必达？先判这一题。',
    items: [
      { id: 'm1a', pid: '极限的定义', q: 'lim(x→0) sin(3x)/x 的值为？', o: ['0', '1', '3', '不存在'], a: 2, e: '由 lim(sin u)/u=1，令 u=3x，原式 = 3。', variantOf: null },
      { id: 'm1b', pid: '极限的定义', q: 'lim(x→0) sin(5x)/x 的值为？', o: ['1', '5', '0', '不存在'], a: 1, e: '同样用第一个重要极限，系数提出去得 5。', variantOf: 'm1a' },
      { id: 'm4a', pid: '拉格朗日中值定理', q: '拉格朗日中值定理成立的全部条件是？', o: ['闭区间连续', '开区间可导', '闭区间连续且开区间可导', '函数在端点取等'], a: 2, e: '在 [a,b] 上连续、在 (a,b) 内可导，缺一不可。', variantOf: null },
      { id: 'm4b', pid: '拉格朗日中值定理', q: '中值定理结论里的 ξ 指的是？', o: ['区间内任意一点', '区间内至少存在一点', '两个端点', '导数为零的点'], a: 1, e: '只保证存在性，不是任意一点都成立。', variantOf: 'm4a' },
      { id: 'm3a', pid: '洛必达法则', q: 'lim(x→0) (e^x-1-x)/x² 用洛必达，正确做法是？', o: ['用一次就出结果', '需要连用两次', '不能用洛必达', '结果是 0'], a: 1, e: '第一次仍是 0/0，第二次得 1/2。', variantOf: null },
      { id: 'm3b', pid: '洛必达法则', q: '下列哪一种情况，洛必达一定会失败？', o: ['0/0 型', '∞/∞ 型', '分子分母导数之比的极限不存在且不是∞', '0·∞ 型（已化为 0/0）'], a: 2, e: '导数之比振荡不存在时法则失效。', variantOf: 'm3a' }
    ]
  },
  ds: {
    id: 'ds',
    name: '数据结构',
    blurb: '链表、树、哈希卡住了？先做一道带知识点的题。',
    items: [
      { id: 'd1a', pid: '线性表', q: '在单链表中删除已知结点 p 的后继，时间复杂度是？', o: ['O(1)', 'O(n)', 'O(log n)', 'O(n²)'], a: 0, e: '已有 p，改 p.next 即可 O(1)。', variantOf: null },
      { id: 'd1b', pid: '线性表', q: '不知道前驱时删除单链表结点 p 本身，复杂度是？', o: ['O(1)', 'O(n)', 'O(log n)', 'O(n²)'], a: 1, e: '要先找到前驱，最坏扫一遍 O(n)。', variantOf: 'd1a' },
      { id: 'd9a', pid: '快速排序', q: '快速排序最坏时间复杂度与触发条件是？', o: ['O(n log n)，随机数据', 'O(n²)，每次划分极度不平衡', 'O(n)，已有序', 'O(n log n)，已有序'], a: 1, e: '枢轴总是最大/最小时退化为 O(n²)。', variantOf: null },
      { id: 'd9b', pid: '快速排序', q: '已有序序列且总取首元素为枢轴，快排复杂度是？', o: ['O(n)', 'O(n log n)', 'O(n²)', 'O(log n)'], a: 2, e: '每次划分极度不平衡，递归深度 n。', variantOf: 'd9a' },
      { id: 'd8a', pid: '哈希表', q: '哈希表中「装填因子」指的是？', o: ['表长 / 元素个数', '元素个数 / 表长', '冲突次数 / 元素个数', '桶数 / 冲突次数'], a: 1, e: 'α = 记录数 / 表长。', variantOf: null },
      { id: 'd8b', pid: '哈希表', q: '工程上常在装填因子大于多少时考虑扩容？', o: ['0.2', '0.5', '0.7', '1.5'], a: 2, e: '通常 α>0.7 时扩容并重哈希。', variantOf: 'd8a' }
    ]
  },
  en: {
    id: 'en',
    name: '大学英语',
    blurb: '时态、从句、虚拟语气今晚卡壳？先判一题。',
    items: [
      { id: 'e1a', pid: '现在完成时', q: 'I ____ in this city since 2019.', o: ['lived', 'have lived', 'had lived', 'was living'], a: 1, e: 'since + 过去时间点，用现在完成时。', variantOf: null },
      { id: 'e1b', pid: '现在完成时', q: 'She ____ here for three years.', o: ['works', 'worked', 'has worked', 'had worked'], a: 2, e: 'for + 一段时间，持续到现在，用现在完成时。', variantOf: 'e1a' },
      { id: 'e2a', pid: '定语从句', q: 'The book ____ cover is red is mine.', o: ['which', 'whose', 'that', 'what'], a: 1, e: '所属关系用 whose。', variantOf: null },
      { id: 'e2b', pid: '定语从句', q: 'This is the only thing ____ I can do now.', o: ['which', 'that', 'what', 'who'], a: 1, e: 'the only 修饰先行词，关系词用 that。', variantOf: 'e2a' },
      { id: 'e4a', pid: '虚拟语气', q: 'If I ____ you, I would take the job.', o: ['am', 'was', 'were', 'be'], a: 2, e: '与现在相反，be 一律 were。', variantOf: null },
      { id: 'e4b', pid: '虚拟语气', q: 'I wish I ____ harder last semester.', o: ['studied', 'had studied', 'would study', 'study'], a: 1, e: 'wish 与过去相反，用 had done。', variantOf: 'e4a' }
    ]
  }
};

function listCourses() {
  return [BANK.math, BANK.ds, BANK.en].map(function (c) {
    var total = c.items.length;
    var variants = c.items.filter(function (it) { return !!it.variantOf; }).length;
    return { id: c.id, name: c.name, blurb: c.blurb, n: total, variants: variants };
  });
}

function courseOf(id) {
  return BANK[id] || BANK.math;
}

function itemOf(courseId, itemId) {
  var items = courseOf(courseId).items;
  for (var i = 0; i < items.length; i++) {
    if (items[i].id === itemId) return items[i];
  }
  return items[0];
}

function firstUnsolved(courseId, solvedIds) {
  var items = courseOf(courseId).items;
  var map = {};
  (solvedIds || []).forEach(function (id) { map[id] = true; });
  for (var i = 0; i < items.length; i++) {
    if (!map[items[i].id] && !items[i].variantOf) return items[i];
  }
  for (var j = 0; j < items.length; j++) {
    if (!map[items[j].id]) return items[j];
  }
  return items[0];
}

function variantOf(courseId, itemId) {
  var items = courseOf(courseId).items;
  var src = itemOf(courseId, itemId);
  for (var i = 0; i < items.length; i++) {
    if (items[i].variantOf === src.id) return items[i];
    if (src.variantOf && items[i].id === src.variantOf) {
      for (var k = 0; k < items.length; k++) {
        if (items[k].variantOf === src.variantOf && items[k].id !== src.id) return items[k];
      }
    }
  }
  return null;
}

module.exports = {
  listCourses: listCourses,
  courseOf: courseOf,
  itemOf: itemOf,
  firstUnsolved: firstUnsolved,
  variantOf: variantOf
};
