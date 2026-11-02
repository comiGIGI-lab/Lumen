var bank = require('../../utils/bank.js');

Page({
  data: { courses: [] },
  onShow: function () {
    this.setData({ courses: bank.listCourses() });
  },
  startCourse: function (e) {
    var id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: '/pages/quiz/quiz?courseId=' + id + '&mode=new' });
  }
});
