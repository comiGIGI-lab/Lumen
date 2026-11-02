var bank = require('../../utils/bank.js');
var store = require('../../utils/store.js');

Page({
  data: {
    courseId: 'math',
    courseName: '',
    item: null,
    chosen: -1,
    revealed: false,
    correct: false,
    isVariant: false,
    variantId: '',
    nextLabel: '下一题'
  },
  onLoad: function (q) {
    this.courseId = q.courseId || 'math';
    this.mode = q.mode || 'new';
    this.fromId = q.fromId || '';
    this.forceId = q.itemId || '';
    this.boot();
  },
  boot: function () {
    var c = bank.courseOf(this.courseId);
    var item;
    var isVariant = false;
    if (this.forceId) {
      item = bank.itemOf(this.courseId, this.forceId);
    } else if (this.mode === 'variant' && this.fromId) {
      item = bank.variantOf(this.courseId, this.fromId) || bank.itemOf(this.courseId, this.fromId);
      isVariant = true;
    } else {
      var st = store.load();
      item = bank.firstUnsolved(this.courseId, st.solved);
    }
    var v = bank.variantOf(this.courseId, item.id);
    // 进入的题本身若是变式（含从错题本「再练」进变式），标题也要显示「这是变式」
    isVariant = isVariant || !!item.variantOf;
    this.setData({
      courseId: this.courseId,
      courseName: c.name,
      item: item,
      chosen: -1,
      revealed: false,
      correct: false,
      isVariant: isVariant,
      variantId: v ? v.id : '',
      nextLabel: '下一题'
    });
  },
  choose: function (e) {
    if (this.data.revealed) return;
    this.setData({ chosen: Number(e.currentTarget.dataset.i) });
  },
  submit: function () {
    if (this.data.chosen < 0) {
      wx.showToast({ title: '先选一个选项', icon: 'none' });
      return;
    }
    var item = this.data.item;
    var ok = this.data.chosen === item.a;
    if (ok) {
      store.markSolved(item.id);
      if (this.mode === 'variant' || this.mode === 'retry') store.markRetryOk(this.fromId || item.id);
    } else {
      store.addWrong({
        id: item.id,
        courseId: this.courseId,
        pid: item.pid,
        q: item.q
      });
    }
    // 仅当「当前这题是原题」且确实有变式时，才把主按钮写成「做变式」；
    // 变式题本身答错不误导用户说「做变式」。
    var isOriginal = !item.variantOf;
    this.setData({
      revealed: true,
      correct: ok,
      nextLabel: (!ok && isOriginal && this.data.variantId) ? '做变式（不重复原题）' : '下一题'
    });
  },
  next: function () {
    var item = this.data.item;
    var isOriginal = !item.variantOf;
    // 只有「答错的是原题」且存在变式，才跳到变式；否则进入下一题。
    if (!this.data.correct && isOriginal && this.data.variantId) {
      wx.redirectTo({
        url: '/pages/quiz/quiz?courseId=' + this.courseId + '&mode=variant&fromId=' + item.id + '&itemId=' + this.data.variantId
      });
      return;
    }
    this.mode = 'new';
    this.forceId = '';
    this.fromId = '';
    this.boot();
  },
  goWrong: function () {
    wx.switchTab({ url: '/pages/wrong/wrong' });
  }
});
