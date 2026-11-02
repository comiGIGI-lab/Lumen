# LUMEN 多端口交付（1024 + 吐司）

本目录是 **赛事精简端口**，与仓库根目录的完整版（`web/` + `server/`）分开。

| 目录 | 端口 | 说明 |
|---|---|---|
| （仓库根 `web/`） | **原网页** | 完整智识有方 Web（Python 后端 + 前端），历史提交已在 `main` |
| `web-1024/` | **轻量网页** | 1024 造物挑战单文件版「今天做一件事」，双击 / 静态托管即可 |
| `web-lite/` | 轻量网页 UI 原型 | 杂志风线框与核心环演示（非参赛单文件） |
| `miniprogram-quiz/` | **小程序** | 「卡在这题」：诊断闯关 + 错题变式，微信原生 |
| `apk-jiangyibian/` | **APK** | 吐司「讲一遍」V5 release（约 5.3MB，低于 GitHub 100MB 限制） |

## 打开方式

- 轻量网页：用浏览器打开 `web-1024/index.html`，或托管后加 sharecode。
- 小程序：微信开发者工具导入 `miniprogram-quiz/`。
- APK：真机安装 `apk-jiangyibian/jiangyibian-v5-release.apk`。
- 原网页：按仓库根 `README.md` 启动 `server` + `web`。

不要把三个赛事端口做成同一套功能换皮：网页领「今天一件事 / 计划被改写」，小程序领「判题 / 错题」，App 领「讲一遍 / 语音」。
