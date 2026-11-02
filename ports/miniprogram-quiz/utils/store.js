var KEY = 'lumen.quiz.v1';

function blank() {
  return { wrong: [], solved: [], retryOk: [] };
}

function load() {
  try {
    var s = wx.getStorageSync(KEY);
    if (!s) return blank();
    if (typeof s === 'string') s = JSON.parse(s);
    if (!s.wrong) s.wrong = [];
    if (!s.solved) s.solved = [];
    if (!s.retryOk) s.retryOk = [];
    return s;
  } catch (e) {
    return blank();
  }
}

function save(data) {
  try {
    wx.setStorageSync(KEY, data);
    return true;
  } catch (e) {
    return false;
  }
}

function markSolved(itemId) {
  var d = load();
  if (d.solved.indexOf(itemId) < 0) d.solved.push(itemId);
  save(d);
  return d;
}

function addWrong(entry) {
  var d = load();
  var found = false;
  for (var i = 0; i < d.wrong.length; i++) {
    if (d.wrong[i].id === entry.id) {
      d.wrong[i].n = (d.wrong[i].n || 1) + 1;
      d.wrong[i].at = Date.now();
      found = true;
    }
  }
  if (!found) {
    d.wrong.unshift({
      id: entry.id,
      courseId: entry.courseId,
      pid: entry.pid,
      q: entry.q,
      n: 1,
      at: Date.now(),
      retriedOk: false
    });
  }
  save(d);
  return d;
}

function markRetryOk(itemId) {
  var d = load();
  if (d.retryOk.indexOf(itemId) < 0) d.retryOk.push(itemId);
  for (var i = 0; i < d.wrong.length; i++) {
    if (d.wrong[i].id === itemId) d.wrong[i].retriedOk = true;
  }
  save(d);
  return d;
}

function clearWrong() {
  var d = load();
  d.wrong = [];
  d.retryOk = [];
  save(d);
  return d;
}

module.exports = {
  load: load,
  markSolved: markSolved,
  addWrong: addWrong,
  markRetryOk: markRetryOk,
  clearWrong: clearWrong
};
