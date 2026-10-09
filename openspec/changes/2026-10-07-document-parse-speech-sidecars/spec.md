# Spec: document-parse / speech-transcribe 侧车

## Objective

上传 PDF 后知识库能检索到正文（扫描件在装了 MinerU 时不再空入库）。上传 .docx / .pptx 后走 Docling CLI 抽字，缺 CLI 回退 OOXML。上传音频后 `/api/asr` 返回中文转写；有 whisper.cpp 用它，没有则 Vosk。侧车缺失时服务仍能启动。

## Commands

```
python tests/run_sidecar_regression.py
python tests/run_safety_regression.py
curl -s http://127.0.0.1:8000/api/knowledge/capabilities
curl -s http://127.0.0.1:8000/api/asr
```

## Boundaries

- Always：侧车用 subprocess；假 CLI 可测；缺引擎回退；中文 ASR 拒绝 `*.en`。
- Ask first：给 api_server 加 pip 依赖、改线上 nginx、登生产。
- Never：import mineru / docling / openai-whisper；把模型提交进 git；force push。

## Success Criteria

1. 未装 mineru-kit 时，文本 PDF 仍走 pypdf，capabilities 标明 mineru.available=false。
2. 假 mineru-kit 下，稀疏 PDF 走 mineru，文本层够长仍走 pypdf。
3. 未装 whisper.cpp 时 `/api/asr` 行为与现网 Vosk 一致（模型缺失则 available=false）。
4. 假 whisper-cli 下 PCM 被包成 WAV 后转写出中文；`*.en` 模型被拒绝。
5. `run_safety_regression.py` 仍全过。
6. 可用内存 < 2GiB 时 mineru.available=false，扫描件走 pypdf；连 `STUDY_LIU_PDF_ENGINE=mineru` 也不拉侧车。Windows 读不到 `/proc/meminfo` 时放行。
7. `.docx` / `.pptx` 可导入；有假 `docling convert` 时 engine=docling；缺 CLI 时 OOXML 抽字；PDF 不走进 office_parse。不 import docling，不用 `--pipeline vlm`。
