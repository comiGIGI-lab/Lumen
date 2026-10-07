# Tasks

- [x] `server/doc_parse.py`：探测 mineru-kit、稀疏 PDF 才升级、失败回退 pypdf
- [x] `kb_ingest.ingest` PDF 走 doc_parse；capabilities 暴露 mineru
- [x] `server/whisper_cpp.py`：PCM→WAV、拒绝 *.en、CLI `-l zh -otxt`
- [x] `asr.status` / `asr.transcribe` 路由：whisper 优先，可强制 vosk
- [x] `tests/run_sidecar_regression.py` 假 CLI 回归
- [x] 导入页 / 转写页展示实际引擎；DEPLOY.md 补侧车安装说明
- [x] OpenSpec 只写本切片，不回填全库
