# 决赛冲刺切片：文档解析 + 语音转写侧车

只覆盖即将改的两条垂直切片，不回填全库。`api_server` 继续纯标准库：上传、配额、SSE、写入知识库。解析和转写放到可缺省的侧车进程。

## 能力图

- `document-parse`：PDF → 正文。数字文本走 pypdf；扫描件 / 复杂版式可选 `mineru-kit parse --tier basic`。Docling 不当中文 PDF 主引擎。
- `speech-transcribe`：16 kHz PCM → 文字。现网 Vosk 保留；可选 ggml-org/whisper.cpp（拒绝 `*.en`）。不走 Docling ASR / openai-whisper。
- 上游 `ingest-http` 已在 master（`POST /api/knowledge/import`、`POST /api/asr`），本切片不重做上传。

## 为什么现在做

决赛演示的课件大量是扫描 PDF 和课堂录音。现网 pypdf 抽扫描件几乎是空的；Vosk small-cn 对口音和术语偏差大。把 MinerU 4.0 或 openai-whisper 塞进零依赖后端会拆掉 1.6G 机器上还能演示的优势。

## 不做

- 不改 Agent 四段链路、学伴、安全层词表。
- 不提交模型文件、`dist/`、`.env`、`data/`。
- 不 force push，不换 `.git`。
