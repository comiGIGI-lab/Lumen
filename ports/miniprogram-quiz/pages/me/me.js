var store = require('../../utils/store.js');

Page({
  data: { wrongN: 0, solvedN: 0 },
  onShow: function () {
    var d = store.load();
    this.setData({
      wrongN: (d.wrong || []).length,
      solvedN: (d.solved || []).length
    });
  },
  clearWrong: function () {
    var that = this;
    wx.showModal({
      title: '清空错题本？',
      content: '只清错题，不清已判对的记录。不可恢复。',
      success: function (res) {
        if (!res.confirm) return;
        var d = store.clearWrong();
        that.setData({ wrongN: 0, solvedN: (d.solved || []).length });
      }
    });
  }
});
