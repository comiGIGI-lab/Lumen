var store = require('../../utils/store.js');
var bank = require('../../utils/bank.js');

Page({
  data: { list: [] },
  onShow: function () {
    this.setData({ list: store.load().wrong || [] });
  },
  retry: function (e) {
    var id = e.currentTarget.dataset.id;
    var courseId = e.currentTarget.dataset.course;
    var v = bank.variantOf(courseId, id);
    var url = '/pages/quiz/quiz?courseId=' + courseId + '&mode=retry&fromId=' + id;
    if (v && v.id !== id) url += '&itemId=' + v.id;
    else url += '&itemId=' + id;
    wx.navigateTo({ url: url });
  }
});
