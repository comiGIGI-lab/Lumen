# Tasks

- [x] `server/doc_parse.py`：探测 mineru-kit、稀疏 PDF 才升级、失败回退 pypdf
- [x] `kb_ingest.ingest` PDF 走 doc_parse；capabilities 暴露 mineru
- [x] `server/whisper_cpp.py`：PCM→WAV、拒绝 *.en、CLI `-l zh -otxt`
- [x] `asr.status` / `asr.transcribe` 路由：whisper 优先，可强制 vosk
- [x] `tests/run_sidecar_regression.py` 假 CLI 回归
- [x] 导入页 / 转写页展示实际引擎；DEPLOY.md 补侧车安装说明
- [x] OpenSpec 只写本切片，不回填全库
- [x] `doc_parse.available`：MemAvailable < 2GiB 不拉 MinerU；DEPLOY 口径改为 ggml-small、禁止 medium
- [x] Day3：`server/office_parse.py` 只接 docx/pptx；`docling convert --to md --no-ocr --output`；缺 CLI 回退 OOXML；kb_ingest / 导入页白名单；DEPLOY 第 14 节
